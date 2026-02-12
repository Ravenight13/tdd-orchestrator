"""Integration tests for task CRUD lifecycle through the API.

Tests verify the complete task lifecycle: create tasks via the database,
list with filters, retrieve details, and retry failed tasks.

This module re-exports type classes and test classes from split modules
for backward compatibility.

Test classes are organized in separate modules by functionality:
- test_task_crud_list.py: List filtering and pagination tests
- test_task_crud_retry.py: Retry, not-found, and conflict tests
- test_task_crud_detail.py: Detail retrieval and filter param tests
"""

from __future__ import annotations

# Re-export type alias classes for backward compatibility
# These must be preserved as module exports per requirements
from tests.integration.api.test_task_crud_types import (
    TaskDetailResponse,
    TaskFilterParams,
    TaskListResponse,
    TaskResponse,
    TaskRetryRequest,
)

# Re-export test classes to maintain test discovery at original location
from tests.integration.api.test_task_crud_list import (
    TestTaskListFiltering,
    TestTaskListPagination,
)
from tests.integration.api.test_task_crud_retry import (
    TestTaskNotFound,
    TestTaskRetry,
    TestTaskRetryConflict,
)
from tests.integration.api.test_task_crud_detail import (
    TestTaskDetailResponse,
    TestTaskFilterParams,
    TestTaskResponseModel,
)

__all__ = [
    # Type aliases (required exports)
    "TaskResponse",
    "TaskDetailResponse",
    "TaskListResponse",
    "TaskFilterParams",
    "TaskRetryRequest",
    # Test classes (for discovery)
    "TestTaskListFiltering",
    "TestTaskListPagination",
    "TestTaskRetry",
    "TestTaskNotFound",
    "TestTaskRetryConflict",
    "TestTaskDetailResponse",
    "TestTaskFilterParams",
    "TestTaskResponseModel",
]
