export interface CircuitBreakerEvent {
  id: number
  event_type: string
  from_state: string | null
  to_state: string | null
  created_at: string
  error_context: string | null
}

export interface CircuitEventsResponse {
  events: CircuitBreakerEvent[]
}
