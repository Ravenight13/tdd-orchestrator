"""Unit tests for refactor_checker module."""

from __future__ import annotations

from pathlib import Path

from tdd_orchestrator.refactor_checker import (
    RefactorCheck,
    RefactorCheckConfig,
    check_needs_refactor,
)


async def test_short_file_no_refactor(tmp_path: Path) -> None:
    """File under 400 lines returns needs_refactor=False."""
    content = "\n".join(f"x_{i} = {i}" for i in range(100))
    (tmp_path / "short.py").write_text(content)

    result = await check_needs_refactor("short.py", tmp_path)

    assert result.needs_refactor is False
    assert result.reasons == []
    assert result.file_lines == 100


async def test_file_over_split_threshold(tmp_path: Path) -> None:
    """401+ line file triggers with reason containing '400'."""
    content = "\n".join(f"x_{i} = {i}" for i in range(410))
    (tmp_path / "big.py").write_text(content)

    result = await check_needs_refactor("big.py", tmp_path)

    assert result.needs_refactor is True
    assert any("400" in r for r in result.reasons)
    assert result.file_lines == 410


async def test_file_over_hard_limit(tmp_path: Path) -> None:
    """801+ line file triggers with reason containing '800' and 'MUST'."""
    content = "\n".join(f"x_{i} = {i}" for i in range(810))
    (tmp_path / "huge.py").write_text(content)

    result = await check_needs_refactor("huge.py", tmp_path)

    assert result.needs_refactor is True
    assert any("800" in r and "MUST" in r for r in result.reasons)
    assert result.file_lines == 810


async def test_long_function_triggers_refactor(tmp_path: Path) -> None:
    """Function >50 lines triggers with reason containing function name."""
    lines = ["def very_long_func():"]
    for i in range(55):
        lines.append(f"    x_{i} = {i}")
    content = "\n".join(lines)
    (tmp_path / "longfunc.py").write_text(content)

    result = await check_needs_refactor("longfunc.py", tmp_path)

    assert result.needs_refactor is True
    assert any("very_long_func" in r for r in result.reasons)


async def test_many_methods_triggers_refactor(tmp_path: Path) -> None:
    """Class with 16+ methods triggers with reason containing class name."""
    lines = ["class BigClass:"]
    for i in range(16):
        lines.append(f"    def method_{i}(self):")
        lines.append(f"        return {i}")
        lines.append("")
    content = "\n".join(lines)
    (tmp_path / "bigclass.py").write_text(content)

    result = await check_needs_refactor("bigclass.py", tmp_path)

    assert result.needs_refactor is True
    assert any("BigClass" in r for r in result.reasons)


async def test_clean_file_no_refactor(tmp_path: Path) -> None:
    """Well-structured 100-line file passes all checks."""
    lines = ['"""A clean module."""', "", ""]
    for i in range(5):
        lines.append(f"def func_{i}(x: int) -> int:")
        lines.append(f"    return x + {i}")
        lines.append("")
    # Pad to ~100 lines with assignments
    while len(lines) < 100:
        lines.append(f"VAR_{len(lines)} = {len(lines)}")
    content = "\n".join(lines)
    (tmp_path / "clean.py").write_text(content)

    result = await check_needs_refactor("clean.py", tmp_path)

    assert result.needs_refactor is False
    assert result.reasons == []
    assert result.file_lines == 100


async def test_custom_config_thresholds(tmp_path: Path) -> None:
    """Custom RefactorCheckConfig(split_threshold=200) is respected."""
    content = "\n".join(f"x_{i} = {i}" for i in range(250))
    (tmp_path / "medium.py").write_text(content)

    # Default config: 400 threshold, should pass
    result_default = await check_needs_refactor("medium.py", tmp_path)
    assert result_default.needs_refactor is False

    # Custom config: 200 threshold, should trigger
    custom = RefactorCheckConfig(split_threshold=200)
    result_custom = await check_needs_refactor("medium.py", tmp_path, config=custom)
    assert result_custom.needs_refactor is True
    assert any("200" in r for r in result_custom.reasons)


async def test_nonexistent_file(tmp_path: Path) -> None:
    """Returns needs_refactor=False for nonexistent files (graceful degradation)."""
    result = await check_needs_refactor("does_not_exist.py", tmp_path)

    assert result.needs_refactor is False
    assert result.reasons == []
    assert result.file_lines == 0


async def test_syntax_error_file(tmp_path: Path) -> None:
    """Returns needs_refactor=False for files with syntax errors."""
    content = "def broken(\n    # missing closing paren and body\n"
    (tmp_path / "bad.py").write_text(content)

    result = await check_needs_refactor("bad.py", tmp_path)

    assert result.needs_refactor is False
    assert result.file_lines > 0


async def test_multiple_reasons_accumulated(tmp_path: Path) -> None:
    """File with both long functions AND high line count reports all reasons."""
    lines = ["def enormous_func():"]
    for i in range(55):
        lines.append(f"    x_{i} = {i}")
    lines.append("")
    # Pad to exceed split threshold
    while len(lines) < 410:
        lines.append(f"VAR_{len(lines)} = {len(lines)}")
    content = "\n".join(lines)
    (tmp_path / "multi.py").write_text(content)

    result = await check_needs_refactor("multi.py", tmp_path)

    assert result.needs_refactor is True
    assert len(result.reasons) >= 2
    assert any("enormous_func" in r for r in result.reasons)
    assert any("400" in r for r in result.reasons)
