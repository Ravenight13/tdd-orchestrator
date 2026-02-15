import { apiFetch } from './client'
import type { MetricsJson } from '@/types/api'

export function fetchMetrics(): Promise<MetricsJson> {
  return apiFetch<MetricsJson>('/metrics/json')
}
