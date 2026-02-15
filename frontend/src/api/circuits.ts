import { apiFetch } from './client'
import type {
  CircuitHealthResponse,
  CircuitBreakerListResponse,
} from '@/types/api'

export function fetchCircuitHealth(): Promise<CircuitHealthResponse> {
  return apiFetch<CircuitHealthResponse>('/circuits/health')
}

export function fetchCircuits(): Promise<CircuitBreakerListResponse> {
  return apiFetch<CircuitBreakerListResponse>('/circuits')
}
