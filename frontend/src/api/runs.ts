import { apiFetch } from './client'
import type { RunListResponse } from '@/types/api'

export function fetchRuns(): Promise<RunListResponse> {
  return apiFetch<RunListResponse>('/runs')
}
