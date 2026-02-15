import { apiFetch } from './client'
import type {
  AttemptsByStageResponse,
  TaskCompletionTimelineResponse,
  InvocationStatsResponse,
} from '@/types/analytics'

export function fetchAttemptsByStage(): Promise<AttemptsByStageResponse> {
  return apiFetch<AttemptsByStageResponse>('/analytics/attempts-by-stage')
}

export function fetchTaskCompletionTimeline(): Promise<TaskCompletionTimelineResponse> {
  return apiFetch<TaskCompletionTimelineResponse>('/analytics/task-completion-timeline')
}

export function fetchInvocationStats(): Promise<InvocationStatsResponse> {
  return apiFetch<InvocationStatsResponse>('/analytics/invocation-stats')
}
