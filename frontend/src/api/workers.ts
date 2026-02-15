import { apiFetch } from './client'
import type {
  WorkerListResponse,
  StaleWorkersResponse,
  Worker,
} from '@/types/api'

export function fetchWorkers(): Promise<WorkerListResponse> {
  return apiFetch<WorkerListResponse>('/workers')
}

export function fetchStaleWorkers(): Promise<StaleWorkersResponse> {
  return apiFetch<StaleWorkersResponse>('/workers/stale')
}

export function fetchWorker(id: string): Promise<Worker> {
  return apiFetch<Worker>(`/workers/${encodeURIComponent(id)}`)
}
