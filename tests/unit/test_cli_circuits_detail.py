"""Tests for circuit breaker CLI command behavior.

Covers output formatting, health thresholds, reset operations, and error
paths.  Companion test_cli_circuits.py covers auto-discovery.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from tdd_orchestrator.cli import cli
from tdd_orchestrator.cli_circuits import (
    _determine_health_status,
    _print_circuit_status,
    _print_health_output,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row(mapping: dict[str, Any]) -> MagicMock:
    """Create a sqlite3.Row-like mock supporting dict() and [] access."""
    mock = MagicMock()
    mock.__getitem__ = MagicMock(side_effect=lambda key: mapping[key])
    mock.__iter__ = MagicMock(side_effect=lambda: iter(mapping))
    mock.keys = MagicMock(return_value=list(mapping.keys()))
    return mock


def _patch_resolve(tmp_path: Path) -> Any:
    return patch(
        "tdd_orchestrator.cli_circuits.resolve_db_for_cli",
        return_value=(tmp_path / "test.db", None),
    )


def _invoke_print_status(rows: list[Any]) -> Any:
    async def _se(*_a: Any, **_k: Any) -> None:
        _print_circuit_status(rows)
    return _se


def _invoke_print_health(data: dict[str, Any], as_json: bool) -> Any:
    async def _se(*_a: Any, **_k: Any) -> None:
        _print_health_output(data, as_json)
    return _se


_ASYNC = "tdd_orchestrator.cli_circuits._circuits_{}_async"


# ---------------------------------------------------------------------------
# TestDetermineHealthStatus
# ---------------------------------------------------------------------------


class TestDetermineHealthStatus:
    """Direct unit tests of _determine_health_status thresholds."""

    @pytest.mark.parametrize(
        ("total", "opened", "half_open", "expected"),
        [
            (0, 0, 0, "UNKNOWN"),
            (10, 0, 0, "HEALTHY"),
            (10, 0, 2, "DEGRADED"),
            (10, 2, 0, "DEGRADED"),
            (10, 5, 0, "UNHEALTHY"),
            (10, 8, 0, "UNHEALTHY"),
            (4, 4, 0, "UNHEALTHY"),
            (10, 4, 1, "DEGRADED"),
            (1, 1, 0, "UNHEALTHY"),
            (1, 0, 1, "DEGRADED"),
        ],
        ids=[
            "no-circuits-unknown",
            "all-closed-healthy",
            "half-open-only-degraded",
            "open-below-half-degraded",
            "open-exactly-half-unhealthy",
            "open-above-half-unhealthy",
            "all-open-unhealthy",
            "open-boundary-with-half-open",
            "single-open-single-total",
            "single-half-open",
        ],
    )
    def test_thresholds(
        self, total: int, opened: int, half_open: int, expected: str
    ) -> None:
        assert _determine_health_status(total, opened, half_open) == expected


# ---------------------------------------------------------------------------
# TestCircuitsStatusOutput
# ---------------------------------------------------------------------------


class TestCircuitsStatusOutput:
    """Output formatting of _print_circuit_status."""

    def test_no_rows_message(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with (
            _patch_resolve(tmp_path),
            patch(_ASYNC.format("status"), new_callable=AsyncMock,
                  side_effect=_invoke_print_status([])),
        ):
            result = runner.invoke(cli, ["circuits", "status"])
        assert result.exit_code == 0
        assert "No circuits found." in result.output

    def test_level_headers_and_state_icons(self, tmp_path: Path) -> None:
        rows = [
            _row({"level": "stage", "identifier": "TDD-1:red",
                  "state": "closed", "failure_count": 0,
                  "success_count": 3, "opened_at": None}),
            _row({"level": "stage", "identifier": "TDD-2:green",
                  "state": "open", "failure_count": 5,
                  "success_count": 0, "opened_at": "2026-01-15 10:30:00"}),
            _row({"level": "worker", "identifier": "worker_1",
                  "state": "half_open", "failure_count": 2,
                  "success_count": 1, "opened_at": None}),
        ]
        runner = CliRunner()
        with (
            _patch_resolve(tmp_path),
            patch(_ASYNC.format("status"), new_callable=AsyncMock,
                  side_effect=_invoke_print_status(rows)),
        ):
            result = runner.invoke(cli, ["circuits", "status"])
        assert result.exit_code == 0
        assert "STAGE CIRCUITS:" in result.output
        assert "WORKER CIRCUITS:" in result.output
        assert "[OK] TDD-1:red" in result.output
        assert "[X] TDD-2:green" in result.output
        assert "[~] worker_1" in result.output
        assert "Opened at: 2026-01-15 10:30:00" in result.output

    def test_unknown_state_shows_question_mark(self, tmp_path: Path) -> None:
        rows = [
            _row({"level": "system", "identifier": "global",
                  "state": "unknown_state", "failure_count": 0,
                  "success_count": 0, "opened_at": None}),
        ]
        runner = CliRunner()
        with (
            _patch_resolve(tmp_path),
            patch(_ASYNC.format("status"), new_callable=AsyncMock,
                  side_effect=_invoke_print_status(rows)),
        ):
            result = runner.invoke(cli, ["circuits", "status"])
        assert "?" in result.output

    def test_filter_flags_passed_through(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with (
            _patch_resolve(tmp_path),
            patch(_ASYNC.format("status"), new_callable=AsyncMock) as mock_fn,
        ):
            result = runner.invoke(
                cli, ["circuits", "status", "--level", "worker", "--state", "open"]
            )
        assert result.exit_code == 0
        mock_fn.assert_awaited_once()
        assert mock_fn.call_args[0][1] == "worker"
        assert mock_fn.call_args[0][2] == "open"


# ---------------------------------------------------------------------------
# TestCircuitsHealthOutput
# ---------------------------------------------------------------------------

_HEALTH_DATA: dict[str, Any] = {
    "status": "DEGRADED",
    "total_circuits": 10,
    "circuits_closed": 7,
    "circuits_open": 2,
    "circuits_half_open": 1,
    "flapping_circuits": 0,
    "details": {
        "open_circuits": [
            {"level": "stage", "identifier": "TDD-1:green",
             "opened_at": "2026-01-15 10:30:00", "minutes_open": 45},
        ]
    },
}


class TestCircuitsHealthOutput:
    """Health command output formatting."""

    def test_health_text_output(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with (
            _patch_resolve(tmp_path),
            patch(_ASYNC.format("health"), new_callable=AsyncMock,
                  side_effect=_invoke_print_health(_HEALTH_DATA, False)),
        ):
            result = runner.invoke(cli, ["circuits", "health"])
        assert result.exit_code == 0
        for fragment in [
            "Circuit Breaker Health", "DEGRADED", "Total circuits: 10",
            "Closed: 7", "Open: 2", "Half-open: 1", "Flapping: 0",
            "stage:TDD-1:green", "45 min",
        ]:
            assert fragment in result.output

    def test_health_json_output(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with (
            _patch_resolve(tmp_path),
            patch(_ASYNC.format("health"), new_callable=AsyncMock,
                  side_effect=_invoke_print_health(_HEALTH_DATA, True)),
        ):
            result = runner.invoke(cli, ["circuits", "health", "--json"])
        assert result.exit_code == 0
        parsed = json.loads(result.output)
        assert parsed["status"] == "DEGRADED"
        assert parsed["total_circuits"] == 10
        assert len(parsed["details"]["open_circuits"]) == 1

    def test_health_no_open_circuits(self, tmp_path: Path) -> None:
        data: dict[str, Any] = {
            "status": "HEALTHY", "total_circuits": 5,
            "circuits_closed": 5, "circuits_open": 0,
            "circuits_half_open": 0, "flapping_circuits": 0,
            "details": {"open_circuits": []},
        }
        runner = CliRunner()
        with (
            _patch_resolve(tmp_path),
            patch(_ASYNC.format("health"), new_callable=AsyncMock,
                  side_effect=_invoke_print_health(data, False)),
        ):
            result = runner.invoke(cli, ["circuits", "health"])
        assert result.exit_code == 0
        assert "HEALTHY" in result.output
        assert "Open Circuits:" not in result.output


# ---------------------------------------------------------------------------
# TestCircuitsResetOutput
# ---------------------------------------------------------------------------


def _mock_reset_echo(msg: str, err: bool = False) -> Any:
    """Return side_effect that echoes a fixed message."""
    async def _se(*_a: Any, **_k: Any) -> None:
        import click
        click.echo(msg, err=err)
    return _se


class TestCircuitsResetOutput:
    """Reset command output messages."""

    def test_reset_all_force(self, tmp_path: Path) -> None:
        runner = CliRunner()
        with (
            _patch_resolve(tmp_path),
            patch(_ASYNC.format("reset"), new_callable=AsyncMock,
                  side_effect=_mock_reset_echo("Reset 3 circuit(s).")),
        ):
            result = runner.invoke(cli, ["circuits", "reset", "all", "--force"])
        assert result.exit_code == 0
        assert "Reset 3 circuit(s)." in result.output

    def test_reset_single_circuit_force(self, tmp_path: Path) -> None:
        async def _se(cid: str, _db: Path, _f: bool) -> None:
            import click
            click.echo(f"Reset circuit: {cid}")

        runner = CliRunner()
        with (
            _patch_resolve(tmp_path),
            patch(_ASYNC.format("reset"), new_callable=AsyncMock,
                  side_effect=_se),
        ):
            result = runner.invoke(
                cli, ["circuits", "reset", "worker:worker_1", "--force"])
        assert result.exit_code == 0
        assert "Reset circuit: worker:worker_1" in result.output

    def test_reset_invalid_format_no_colon(self, tmp_path: Path) -> None:
        async def _se(cid: str, _db: Path, _f: bool) -> None:
            import click
            if ":" not in cid:
                click.echo(
                    "Error: Invalid circuit ID format. Use level:identifier",
                    err=True)

        runner = CliRunner()
        with (
            _patch_resolve(tmp_path),
            patch(_ASYNC.format("reset"), new_callable=AsyncMock,
                  side_effect=_se),
        ):
            result = runner.invoke(
                cli, ["circuits", "reset", "badformat", "--force"])
        assert result.exit_code == 0
        assert "Invalid circuit ID format" in result.output

    def test_reset_circuit_not_found(self, tmp_path: Path) -> None:
        async def _se(cid: str, _db: Path, _f: bool) -> None:
            import click
            click.echo(f"Error: Circuit not found: {cid}", err=True)

        runner = CliRunner()
        with (
            _patch_resolve(tmp_path),
            patch(_ASYNC.format("reset"), new_callable=AsyncMock,
                  side_effect=_se),
        ):
            result = runner.invoke(
                cli, ["circuits", "reset", "stage:nonexistent", "--force"])
        assert result.exit_code == 0
        assert "Circuit not found: stage:nonexistent" in result.output

    def test_resolve_failure_shows_error(self) -> None:
        runner = CliRunner()
        with patch(
            "tdd_orchestrator.cli_circuits.resolve_db_for_cli",
            side_effect=FileNotFoundError("No .tdd/ directory found."),
        ):
            result = runner.invoke(
                cli, ["circuits", "reset", "all", "--force"])
        assert result.exit_code != 0
        assert "No .tdd/" in result.output
