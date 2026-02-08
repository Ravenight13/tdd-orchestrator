"""Tests for Pass 2 (cycle breakdown) of the LLM decomposer.

Separated from test_decomposer.py to keep files under 800-line limit.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from tdd_orchestrator.database import reset_db
from tdd_orchestrator.decomposition import (
    DecompositionConfig,
    LLMDecomposer,
    MockLLMClient,
)
from tdd_orchestrator.decomposition.parser import ParsedSpec


@pytest.fixture(autouse=True)
async def _reset_db() -> None:
    """Reset DB singleton after each test."""
    yield  # type: ignore[misc]
    await reset_db()


def _make_spec(
    *,
    module_structure: dict | None = None,  # type: ignore[type-arg]
    module_api: dict | None = None,  # type: ignore[type-arg]
) -> ParsedSpec:
    """Create a minimal ParsedSpec with pre-extracted cycles."""
    return ParsedSpec(
        functional_requirements=[{"id": "FR-1", "title": "Test"}],
        tdd_cycles=[
            {
                "cycle_number": 1,
                "phase": "Foundation",
                "cycle_title": "Core Setup",
                "components": ["Config"],
                "expected_tests": "5-10",
                "module_hint": "src/myapp/",
            }
        ],
        module_structure=module_structure or {},
        module_api=module_api or {},
        raw_content="test spec",
    )


def _mock_pass2_response() -> str:
    """Return a valid Pass 2 JSON response."""
    return json.dumps([
        {
            "title": "Implement config loader",
            "goal": "Load config files",
            "estimated_tests": 8,
            "estimated_lines": 50,
            "test_file": "tests/unit/test_config.py",
            "impl_file": "src/myapp/config.py",
            "components": ["Config"],
        }
    ])


class TestBreakCyclePassesContext:
    """Tests that _break_cycle passes module_structure and module_api to prompts."""

    async def test_break_cycle_passes_module_structure(self) -> None:
        """Verify prompt contains module_structure paths when provided."""
        captured_prompts: list[str] = []

        async def capture_prompt(prompt: str) -> str:
            captured_prompts.append(prompt)
            return _mock_pass2_response()

        client = MockLLMClient()
        client.send_message = AsyncMock(side_effect=capture_prompt)  # type: ignore[assignment]

        spec = _make_spec(
            module_structure={"files": ["src/myapp/routes.py", "src/myapp/models.py"]}
        )
        config = DecompositionConfig(enable_parallel_calls=False)
        decomposer = LLMDecomposer(client=client, config=config, prefix="TEST")

        await decomposer._break_cycle(spec.tdd_cycles[0], spec)

        assert len(captured_prompts) == 1
        prompt = captured_prompts[0]
        assert "src/myapp/" in prompt

    async def test_break_cycle_passes_module_api_when_enabled(self) -> None:
        """With scaffolding ref enabled, prompt has MODULE API section."""
        captured_prompts: list[str] = []

        async def capture_prompt(prompt: str) -> str:
            captured_prompts.append(prompt)
            return _mock_pass2_response()

        client = MockLLMClient()
        client.send_message = AsyncMock(side_effect=capture_prompt)  # type: ignore[assignment]

        spec = _make_spec(
            module_api={
                "src/myapp/config.py": {
                    "exports": ["ConfigLoader", "load_config"],
                    "test_import": "from myapp.config import ConfigLoader",
                }
            }
        )
        config = DecompositionConfig(
            enable_parallel_calls=False,
            enable_scaffolding_reference=True,
        )
        decomposer = LLMDecomposer(client=client, config=config, prefix="TEST")

        await decomposer._break_cycle(spec.tdd_cycles[0], spec)

        assert len(captured_prompts) == 1
        prompt = captured_prompts[0]
        assert "Module API Specification" in prompt
        assert "ConfigLoader" in prompt

    async def test_break_cycle_omits_module_api_when_disabled(self) -> None:
        """With scaffolding ref disabled, prompt omits MODULE API section."""
        captured_prompts: list[str] = []

        async def capture_prompt(prompt: str) -> str:
            captured_prompts.append(prompt)
            return _mock_pass2_response()

        client = MockLLMClient()
        client.send_message = AsyncMock(side_effect=capture_prompt)  # type: ignore[assignment]

        spec = _make_spec(
            module_api={
                "src/myapp/config.py": {
                    "exports": ["ConfigLoader"],
                }
            }
        )
        config = DecompositionConfig(
            enable_parallel_calls=False,
            enable_scaffolding_reference=False,  # Disabled
        )
        decomposer = LLMDecomposer(client=client, config=config, prefix="TEST")

        await decomposer._break_cycle(spec.tdd_cycles[0], spec)

        assert len(captured_prompts) == 1
        prompt = captured_prompts[0]
        assert "Module API Specification" not in prompt
