export interface TaskStatusChangedData {
  task_key: string
  status: string
}

export interface CircuitBreakerTrippedData {
  breaker_name: string
  new_state: string
}

export type SSEEventType =
  | 'task_status_changed'
  | 'circuit_breaker_tripped'
  | 'heartbeat'
