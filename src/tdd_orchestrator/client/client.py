"""Async HTTP client for the TDD Orchestrator REST API."""

from __future__ import annotations

from typing import Any

import httpx

from .errors import ClientError, NotFoundError, ServerError


class TDDOrchestratorClient:
    """Async client wrapping the TDD Orchestrator REST API.

    Usage::

        async with TDDOrchestratorClient() as client:
            health = await client.health()
            tasks = await client.list_tasks(status="pending")

    Args:
        base_url: Base URL of the orchestrator API server.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8420",
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout,
        )

    async def __aenter__(self) -> TDDOrchestratorClient:
        """Enter the async context manager.

        Returns:
            The client instance.
        """
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit the async context manager, closing the underlying HTTP client."""
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send an HTTP request and return the parsed JSON response.

        Args:
            method: HTTP method (GET, POST, etc.).
            path: URL path relative to ``base_url``.
            **kwargs: Extra keyword arguments forwarded to ``httpx.AsyncClient.request``.

        Returns:
            Parsed JSON response as a dictionary.

        Raises:
            NotFoundError: If the server responds with 404.
            ServerError: If the server responds with a 5xx status code.
            ClientError: For any other non-2xx status code.
        """
        response = await self._client.request(method, path, **kwargs)

        if response.status_code == 404:
            detail = self._extract_detail(response)
            raise NotFoundError(message=detail)

        if response.status_code >= 500:
            detail = self._extract_detail(response)
            raise ServerError(status_code=response.status_code, message=detail)

        if response.status_code >= 400:
            detail = self._extract_detail(response)
            raise ClientError(status_code=response.status_code, message=detail)

        result: dict[str, Any] = response.json()
        return result

    @staticmethod
    def _extract_detail(response: httpx.Response) -> str:
        """Extract a human-readable error detail from a response.

        Tries to parse the JSON body for a ``detail`` key; falls back to the
        raw response text.

        Args:
            response: The HTTP response to extract detail from.

        Returns:
            The error detail string.
        """
        try:
            body = response.json()
            if isinstance(body, dict) and "detail" in body:
                return str(body["detail"])
        except Exception:
            pass
        return response.text

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def health(self) -> dict[str, Any]:
        """Check API health.

        Returns:
            Server health payload.
        """
        return await self._request("GET", "/health")

    async def list_tasks(
        self,
        *,
        status: str | None = None,
        phase: str | None = None,
        complexity: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """List tasks with optional filtering and pagination.

        Args:
            status: Filter by task status (pending, running, completed, failed).
            phase: Filter by task phase (decomposition, red, green, verify, refactor).
            complexity: Filter by complexity (low, medium, high).
            limit: Maximum number of tasks to return.
            offset: Number of tasks to skip.

        Returns:
            Dictionary with ``tasks``, ``total``, ``limit``, and ``offset``.
        """
        params: dict[str, str | int] = {"limit": limit, "offset": offset}
        if status is not None:
            params["status"] = status
        if phase is not None:
            params["phase"] = phase
        if complexity is not None:
            params["complexity"] = complexity
        return await self._request("GET", "/tasks", params=params)

    async def get_task(self, task_key: str) -> dict[str, Any]:
        """Get full detail for a single task.

        Args:
            task_key: Unique task identifier.

        Returns:
            Task detail including attempt history.
        """
        return await self._request("GET", f"/tasks/{task_key}")

    async def retry_task(self, task_key: str) -> dict[str, Any]:
        """Retry a failed task by resetting it to pending.

        Args:
            task_key: Unique task identifier.

        Returns:
            Updated task status payload.
        """
        return await self._request("POST", f"/tasks/{task_key}/retry")

    async def task_stats(self) -> dict[str, Any]:
        """Get aggregate task counts by status.

        Returns:
            Dictionary with counts per status and total.
        """
        return await self._request("GET", "/tasks/stats")

    async def task_progress(self) -> dict[str, Any]:
        """Get task completion progress.

        Returns:
            Dictionary with total, completed, percentage, and by_status breakdown.
        """
        return await self._request("GET", "/tasks/progress")
