import { apiFetch } from './client'
import type {
  CircuitHealthResponse,
  CircuitBreakerListResponse,
} from '@/types/api'
import type { CircuitEventsResponse } from '@/types/circuit-events'

export function fetchCircuitHealth(): Promise<CircuitHealthResponse> {
  return apiFetch<CircuitHealthResponse>('/circuits/health')
}

export function fetchCircuits(): Promise<CircuitBreakerListResponse> {
  return apiFetch<CircuitBreakerListResponse>('/circuits')
}

export function fetchCircuitEvents(circuitId: string): Promise<CircuitEventsResponse> {
  return apiFetch<CircuitEventsResponse>(`/circuits/${circuitId}/events`)
}
