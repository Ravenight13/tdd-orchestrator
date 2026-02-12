"""Shared fixtures for orchestrator integration tests."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock

import pytest

from tdd_orchestrator.database import OrchestratorDB


@pytest.fixture
async def db():
    """In-memory database with schema initialized."""
    async with OrchestratorDB(":memory:") as database:
        yield database


@pytest.fixture
async def db_with_tasks(db):
    """Database pre-populated with sample tasks."""
    await db.create_task("TDD-00", "Foundation", phase=0, sequence=0)
    await db.create_task("TDD-01", "Core Feature", phase=0, sequence=1, depends_on=["TDD-00"])
    await db.create_task("TDD-02", "Enhancement", phase=1, sequence=0, depends_on=["TDD-01"])
    return db


@pytest.fixture
async def db_with_workers(db):
    """Database with registered workers."""
    await db.register_worker(1)
    await db.register_worker(2)
    return db


class TaskFactory:
    """Factory for creating test tasks with sensible defaults."""

    def __init__(self, db: OrchestratorDB) -> None:
        self.db = db
        self.counter = 0

    async def create(
        self,
        task_key: str | None = None,
        title: str = "Test Task",
        phase: int = 0,
        sequence: int | None = None,
        depends_on: list[str] | None = None,
        status: str = "pending",
    ) -> int:
        """Create a task with defaults for unspecified fields."""
        self.counter += 1
        task_key = task_key or f"TDD-{self.counter:03d}"
        sequence = sequence if sequence is not None else self.counter

        task_id = await self.db.create_task(
            task_key=task_key,
            title=title,
            phase=phase,
            sequence=sequence,
            depends_on=depends_on,
        )

        if status != "pending":
            await self.db.update_task_status(task_key, status)

        return task_id


class WorkerFactory:
    """Factory for creating test workers."""

    def __init__(self, db: OrchestratorDB) -> None:
        self.db = db
        self.counter = 0

    async def create(self, worker_id: int | None = None) -> int:
        """Create and register a worker."""
        self.counter += 1
        worker_id = worker_id or self.counter
        await self.db.register_worker(worker_id)
        return worker_id


@pytest.fixture
async def task_factory(db):
    """Task factory for test data generation."""
    return TaskFactory(db)


@pytest.fixture
async def worker_factory(db):
    """Worker factory for test data generation."""
    return WorkerFactory(db)


@pytest.fixture
def git_repo(tmp_path):
    """Initialized Git repository in temp directory."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("# Test Repository\n")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=tmp_path, check=True)
    return tmp_path


@pytest.fixture
def mock_agent_sdk(monkeypatch):
    """Mock Claude Agent SDK for testing without API calls."""

    async def mock_query(prompt, options=None):
        yield MagicMock(text="Mocked LLM response")

    monkeypatch.setattr("tdd_orchestrator.worker_pool.worker.sdk_query", mock_query, raising=False)
    monkeypatch.setattr("tdd_orchestrator.worker_pool.worker.HAS_AGENT_SDK", True, raising=False)
    monkeypatch.setattr("tdd_orchestrator.worker_pool.worker.ClaudeAgentOptions", MagicMock, raising=False)
