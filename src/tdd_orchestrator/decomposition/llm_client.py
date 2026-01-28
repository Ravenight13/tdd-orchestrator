"""LLM client abstraction for decomposition engine.

This module provides an abstract LLM client protocol and implementations
for both testing (mock) and production (Claude Agent SDK) use cases.

IMPORTANT: This project uses Claude Max subscription auth via `claude login`,
NOT API keys. The production client uses claude_agent_sdk.query() which
authenticates through the subscription model.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

import psutil

logger = logging.getLogger(__name__)


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for LLM clients used in decomposition.

    This protocol defines the interface that all LLM clients must implement.
    It allows for easy swapping between mock clients (for testing) and
    production clients (Anthropic API).
    """

    async def send_message(self, prompt: str) -> str:
        """Send a prompt to the LLM and return the response text.

        Args:
            prompt: The formatted prompt to send to the LLM.

        Returns:
            The text response from the LLM.

        Raises:
            LLMClientError: If the API call fails.
        """
        ...


class LLMClientError(Exception):
    """Base exception for LLM client errors."""

    pass


class LLMResponseParseError(LLMClientError):
    """Raised when LLM response cannot be parsed as expected format."""

    pass


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients.

    Provides common functionality like response parsing and error handling.
    Subclasses must implement the _call_api method.
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514") -> None:
        """Initialize the LLM client.

        Args:
            model: The model identifier to use for API calls.
        """
        self.model = model

    @abstractmethod
    async def _call_api(self, prompt: str) -> str:
        """Make the actual API call.

        Args:
            prompt: The prompt to send.

        Returns:
            Raw response text from the API.
        """
        ...

    async def send_message(self, prompt: str) -> str:
        """Send a message and return the response.

        Args:
            prompt: The prompt to send to the LLM.

        Returns:
            The text response from the LLM.
        """
        return await self._call_api(prompt)


class MockLLMClient(BaseLLMClient):
    """Mock LLM client for testing.

    Returns predefined responses based on prompt content. Useful for
    unit testing the decomposition pipeline without making actual API calls.
    """

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        default_response: str | None = None,
    ) -> None:
        """Initialize the mock client with predefined responses.

        Args:
            responses: Dict mapping prompt substrings to responses.
            default_response: Fallback response if no match found.
        """
        super().__init__(model="mock")
        self.responses = responses or {}
        self.default_response = default_response or "[]"
        self.call_history: list[str] = []

    async def _call_api(self, prompt: str) -> str:
        """Return a predefined response based on prompt content.

        Args:
            prompt: The prompt to match against.

        Returns:
            Matching predefined response or default response.
        """
        self.call_history.append(prompt)

        # Check for matching response based on prompt content
        for key, response in self.responses.items():
            if key in prompt:
                logger.debug(f"MockLLMClient matched key: {key}")
                return response

        logger.debug("MockLLMClient using default response")
        return self.default_response

    def get_call_count(self) -> int:
        """Return the number of API calls made.

        Returns:
            Number of times send_message was called.
        """
        return len(self.call_history)

    def reset(self) -> None:
        """Reset call history for fresh test runs."""
        self.call_history.clear()


class SubscriptionErrorSimulator(BaseLLMClient):
    """Simulates Claude Agent SDK subscription-model errors for testing.

    IMPORTANT: This simulates SUBSCRIPTION errors, not API key errors.
    We use `claude login` for auth, not API keys.

    Error Types (subscription-appropriate):
    - session_expired: Subscription session needs refresh via 'claude login'
    - quota_exceeded: Monthly subscription quota exhausted
    - sdk_not_installed: claude_agent_sdk ImportError
    - timeout: Async operation timeout (generic)
    - connection_error: Network failure (generic)
    - malformed_response: Model returns unparseable content
    - model_unavailable: Model temporarily unavailable for subscription tier
    - partial_response: Truncated/incomplete response
    """

    def __init__(
        self,
        error_type: str,
        error_after_calls: int = 0,
        recovery_response: str | None = None,
    ) -> None:
        """Initialize subscription error simulator.

        Args:
            error_type: One of the subscription-appropriate error types listed above.
            error_after_calls: Number of successful calls before error triggers.
            recovery_response: Response to return after recovery (for retry testing).
        """
        super().__init__(model="subscription-error-simulator")
        self.error_type = error_type
        self.error_after_calls = error_after_calls
        self.recovery_response = recovery_response
        self.call_count = 0
        self.errors_raised = 0

    async def _call_api(self, prompt: str) -> str:
        """Simulate API call, raising subscription-model errors."""
        import asyncio

        self.call_count += 1

        # Return valid response before error trigger point
        if self.call_count <= self.error_after_calls:
            return json.dumps([{"cycle_number": 1, "cycle_title": "Pre-error"}])

        # After recovery, return recovery response if configured
        if self.recovery_response and self.errors_raised > 0:
            return self.recovery_response

        self.errors_raised += 1

        if self.error_type == "session_expired":
            # Subscription session expired - need to re-authenticate
            raise LLMClientError(
                "Query failed: Session expired. Please run 'claude login' to refresh your subscription authentication."
            )

        elif self.error_type == "quota_exceeded":
            # Monthly subscription quota exhausted
            raise LLMClientError(
                "Query failed: Monthly usage quota exceeded for your Claude Max subscription. "
                "Quota resets on the 1st of next month."
            )

        elif self.error_type == "sdk_not_installed":
            # Simulates ImportError when SDK missing
            raise LLMClientError(
                "claude_agent_sdk not installed. Ensure Claude Code CLI is available and you are logged in via 'claude login'."
            )

        elif self.error_type == "timeout":
            # Generic async timeout
            raise asyncio.TimeoutError("Simulated timeout: Claude query exceeded 60s limit")

        elif self.error_type == "connection_error":
            # Network failure
            raise ConnectionError("Simulated network failure: Unable to reach Claude service")

        elif self.error_type == "malformed_response":
            # Model returns unparseable content
            return "This is not valid JSON at all {{{malformed response from model"

        elif self.error_type == "model_unavailable":
            # Model not available for subscription tier
            raise LLMClientError(
                "Query failed: Model claude-sonnet-4 is temporarily unavailable. "
                "Please try again in a few minutes or contact support if the issue persists."
            )

        elif self.error_type == "partial_response":
            # Truncated/incomplete response from model
            return '[{"cycle_number": 1, "cycle_title": "Trunca'

        raise ValueError(f"Unknown error_type: {self.error_type}")


class ClaudeAgentSDKClient(BaseLLMClient):
    """Claude Agent SDK client for production use.

    Uses claude_agent_sdk.query() with subscription auth via `claude login`.
    Does NOT require API keys - uses Claude Max subscription authentication.

    IMPORTANT: Ensure you are logged in via `claude login` before using.
    """

    # Default system prompt for JSON-only responses
    DEFAULT_SYSTEM_PROMPT = (
        "You are a JSON-only API. Return ONLY valid JSON arrays or objects. "
        "No explanations, no markdown code blocks, no text before or after the JSON."
    )

    def __init__(
        self,
        max_turns: int = 1,
        system_prompt: str | None = None,
    ) -> None:
        """Initialize the Claude Agent SDK client.

        Args:
            max_turns: Maximum conversation turns (default: 1 for single response).
            system_prompt: Custom system prompt. Defaults to JSON-only instruction.
        """
        super().__init__(model="claude-agent-sdk")
        self.max_turns = max_turns
        self.system_prompt = system_prompt or self.DEFAULT_SYSTEM_PROMPT

    async def _call_api(self, prompt: str) -> str:
        """Make a query using Claude Agent SDK with subscription auth.

        Args:
            prompt: The prompt to send.

        Returns:
            Response text from Claude.

        Raises:
            LLMClientError: If the query fails or SDK not installed.
        """
        try:
            from claude_agent_sdk import ClaudeAgentOptions, query

            options = ClaudeAgentOptions(
                tools=[],  # Explicitly disable ALL tools for JSON-only responses
                max_turns=self.max_turns,
                system_prompt=self.system_prompt,
            )

            # Collect response text from the async generator
            # Only extract from AssistantMessage (skip SystemMessage and ResultMessage)
            # IMPORTANT: Explicitly close the generator to prevent CLI hang
            response_text = ""
            generator = query(prompt=prompt, options=options)
            try:
                async for message in generator:
                    # Filter to assistant messages only (type checking)
                    if type(message).__name__ != "AssistantMessage":
                        continue

                    # Extract text from message if available
                    text_attr = getattr(message, "text", None)
                    if text_attr is not None:
                        response_text += str(text_attr)
                    else:
                        # Handle content blocks (TextBlock has .text attribute)
                        content = getattr(message, "content", None)
                        if isinstance(content, str):
                            response_text += content
                        elif isinstance(content, list):
                            for block in content:
                                block_text = getattr(block, "text", None)
                                if block_text is not None:
                                    response_text += str(block_text)
            finally:
                await generator.aclose()  # type: ignore[attr-defined]

            return response_text

        except ImportError as e:
            raise LLMClientError(
                "claude_agent_sdk not installed. Ensure Claude Code CLI is available."
            ) from e
        except Exception as e:
            logger.error(f"Claude Agent SDK query failed: {e}")
            raise LLMClientError(f"Query failed: {e}") from e
        # NO finally block here - cleanup happens at CLI exit via cleanup_sdk_child_processes()


def cleanup_sdk_child_processes() -> None:
    """Kill any Claude CLI child processes spawned by this process.

    The Claude Agent SDK spawns actual OS subprocesses that may not terminate
    when the Python generator is closed. This function finds and terminates
    any lingering Claude CLI processes.

    IMPORTANT: Call this ONCE at program exit, not after each SDK call.
    Calling per-call kills parallel SDK queries prematurely.
    """
    import os

    try:
        parent = psutil.Process(os.getpid())
        children = parent.children(recursive=True)

        # Find and terminate Claude CLI processes
        claude_procs = [p for p in children if "claude" in p.name().lower()]
        for proc in claude_procs:
            try:
                logger.debug(f"Terminating Claude CLI process: {proc.pid}")
                proc.terminate()
            except psutil.NoSuchProcess:
                pass

        # Wait for termination with timeout, then force kill stragglers
        if claude_procs:
            gone, alive = psutil.wait_procs(claude_procs, timeout=3)
            for proc in alive:
                try:
                    logger.warning(f"Force killing Claude CLI process: {proc.pid}")
                    proc.kill()
                except psutil.NoSuchProcess:
                    pass
    except Exception as e:
        logger.warning(f"Failed to cleanup child processes: {e}")


def parse_json_response(response: str) -> Any:
    """Extract JSON from LLM response, handling markdown code blocks.

    LLMs often wrap JSON in markdown code blocks. This function handles
    both direct JSON and JSON wrapped in ```json ... ``` blocks.

    Args:
        response: Raw response text from LLM.

    Returns:
        Parsed JSON data.

    Raises:
        LLMResponseParseError: If JSON cannot be extracted or parsed.
    """
    import re

    # Strip leading/trailing whitespace
    response = response.strip()

    # Try direct parse first
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", response, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError as e:
            raise LLMResponseParseError(
                f"JSON in code block is invalid: {e}\nContent: {match.group(1)[:200]}"
            ) from e

    # Try finding JSON array or object directly
    # Look for array
    array_match = re.search(r"\[.*\]", response, re.DOTALL)
    if array_match:
        try:
            return json.loads(array_match.group(0))
        except json.JSONDecodeError:
            pass

    # Look for object
    object_match = re.search(r"\{.*\}", response, re.DOTALL)
    if object_match:
        try:
            return json.loads(object_match.group(0))
        except json.JSONDecodeError:
            pass

    raise LLMResponseParseError(f"Could not parse JSON from response: {response[:200]}...")
