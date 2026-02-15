export interface StageAttemptStats {
  stage: string
  total: number
  successes: number
  avg_duration_ms: number | null
}

export interface AttemptsByStageResponse {
  stages: StageAttemptStats[]
}

export interface TimelinePoint {
  date: string
  completed: number
}

export interface TaskCompletionTimelineResponse {
  timeline: TimelinePoint[]
}

export interface InvocationStatsItem {
  stage: string
  count: number
  total_tokens: number
  avg_duration_ms: number | null
}

export interface InvocationStatsResponse {
  invocations: InvocationStatsItem[]
}
