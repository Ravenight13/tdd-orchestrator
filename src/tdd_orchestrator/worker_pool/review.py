"""Static review helpers for TDD pipeline.

Provides functions for running AST-based static review and
pytest collection verification on test files.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

from ..code_verifier import CodeVerifier

from ..ast_checker import ASTCheckResult, ASTQualityChecker, ASTViolation
from ..database import OrchestratorDB
from .circuit_breakers import StaticReviewCircuitBreaker

logger = logging.getLogger(__name__)


async def run_static_review(
    task: dict[str, Any],
    base_dir: Path,
    circuit_breaker: StaticReviewCircuitBreaker,
    db: OrchestratorDB,
    run_id: int,
) -> ASTCheckResult:
    """Run static review on RED stage test file.

    Implements PLAN12 Static RED Review gate using:
    - AST-based checks (missing assertions, empty assertions)
    - Subprocess pytest collection verification
    - Circuit breaker to auto-disable after consecutive failures

    Graceful degradation: parse failures, timeouts, or exceptions
    don't block pipeline - they pass through with warning.

    Args:
        task: Task dict with test_file path.
        base_dir: Root directory for file path resolution.
        circuit_breaker: Static review circuit breaker instance.
        db: Database instance for logging metrics.
        run_id: Current execution run ID.

    Returns:
        ASTCheckResult with violations found.
    """
    test_file = task.get("test_file", "")
    task_key = task.get("task_key", "UNKNOWN")

    # Guard: skip review entirely if test_file is empty
    if not test_file:
        logger.warning("[%s] No test_file specified - skipping static review", task_key)
        return ASTCheckResult(violations=[], file_path="")

    # Guard: skip review if test file doesn't exist on disk
    test_path = base_dir / test_file
    if not test_path.exists():
        logger.warning(
            "[%s] Test file not found at %s - skipping static review", task_key, test_path
        )
        return ASTCheckResult(violations=[], file_path=test_file)

    # Check circuit breaker - skip static review if disabled
    if not circuit_breaker.is_enabled():
        remaining = 0.0
        if circuit_breaker.disabled_until is not None:
            remaining = circuit_breaker.disabled_until - time.time()
        logger.warning(
            "[%s] Static review circuit breaker OPEN - skipping (re-enables in %.0fs)",
            task_key,
            max(0.0, remaining),
        )
        return ASTCheckResult(violations=[], file_path=test_file)

    # Check if circuit breaker just re-enabled after cooldown
    if circuit_breaker.consecutive_failures == 0:
        # May have just reset - log if we had failures before
        pass  # Normal operation, no special logging needed

    try:
        # Timeout wrapper (500ms max for all checks)
        async with asyncio.timeout(0.5):
            # AST checks
            checker = ASTQualityChecker()
            test_path = base_dir / test_file
            result = await checker.check_file(test_path)

            # Subprocess verification: pytest --collect-only
            collection_ok, stderr = await verify_pytest_collection(test_file, base_dir)
            if not collection_ok:
                result.violations.append(
                    ASTViolation(
                        pattern="pytest_collection",
                        line_number=0,
                        message="Pytest collection failed",
                        severity="warning",
                        code_snippet=stderr[:200] if stderr else "",
                    )
                )
                # Recalculate is_blocking since we added a violation
                result.is_blocking = any(v.severity == "error" for v in result.violations)

            # Log Phase 1B shadow mode metrics (warnings only)
            for violation in result.violations:
                if violation.severity == "warning":
                    try:
                        await db.log_static_review_metric(
                            task_id=task.get("id", 0),
                            task_key=task_key,
                            check_name=violation.pattern,
                            severity=violation.severity,
                            line_number=violation.line_number,
                            message=violation.message,
                            code_snippet=violation.code_snippet or None,
                            fix_guidance=None,  # ASTViolation doesn't have fix_guidance
                            run_id=run_id,
                        )
                    except Exception as e:
                        logger.warning(
                            "[%s] Failed to log shadow mode metric: %s",
                            task_key,
                            e,
                        )

            logger.info(
                "[%s] Static review: %d violations, blocking=%s",
                task_key,
                len(result.violations),
                result.is_blocking,
            )

            # Record success - reset circuit breaker
            circuit_breaker.record_success()
            return result

    except asyncio.TimeoutError:
        logger.warning("[%s] Static review timeout - passing through", task_key)
        return ASTCheckResult(violations=[], file_path=test_file)

    except Exception as e:
        # Record failure in circuit breaker
        circuit_opened = circuit_breaker.record_failure()
        if circuit_opened:
            logger.error(
                "[%s] Static review circuit breaker OPEN - disabled for %.0fs after %d failures",
                task_key,
                circuit_breaker.cooldown_seconds,
                circuit_breaker.max_consecutive_failures,
            )
        else:
            logger.error(
                "[%s] Static review exception: %s - passing through (failure %d/%d)",
                task_key,
                e,
                circuit_breaker.consecutive_failures,
                circuit_breaker.max_consecutive_failures,
            )
        return ASTCheckResult(violations=[], file_path=test_file)


async def verify_pytest_collection(test_file: str, base_dir: Path) -> tuple[bool, str]:
    """Run pytest --collect-only to catch import/fixture errors.

    Args:
        test_file: Path to test file.
        base_dir: Root directory for running pytest.

    Returns:
        Tuple of (success, stderr).
    """
    try:
        pytest_path = CodeVerifier._resolve_tool("pytest")
        proc = await asyncio.create_subprocess_exec(
            pytest_path,
            "--collect-only",
            "-q",
            test_file,
            cwd=str(base_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5.0)
            return proc.returncode == 0, stderr.decode()
        except asyncio.TimeoutError:
            proc.kill()
            return False, "Pytest collection timed out (5s)"
    except Exception as e:
        logger.warning("Pytest collection error: %s", e)
        return True, ""  # Graceful degradation
