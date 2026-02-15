"""Analytics response models for dashboard chart endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class StageAttemptStats(BaseModel):
    """Stats for a single stage's attempts."""

    stage: str
    total: int
    successes: int
    avg_duration_ms: float | None


class AttemptsByStageResponse(BaseModel):
    """Response for attempts-by-stage endpoint."""

    stages: list[StageAttemptStats]


class TimelinePoint(BaseModel):
    """A single point on the task completion timeline."""

    date: str
    completed: int


class TaskCompletionTimelineResponse(BaseModel):
    """Response for task-completion-timeline endpoint."""

    timeline: list[TimelinePoint]


class InvocationStatsItem(BaseModel):
    """Stats for invocations grouped by stage."""

    stage: str
    count: int
    total_tokens: int
    avg_duration_ms: float | None


class InvocationStatsResponse(BaseModel):
    """Response for invocation-stats endpoint."""

    invocations: list[InvocationStatsItem]
