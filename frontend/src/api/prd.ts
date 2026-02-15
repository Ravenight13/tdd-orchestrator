import { apiFetch } from './client'
import type { PrdSubmitResponse, PrdStatusResponse } from '@/types/prd'

interface PrdSubmitRequest {
  name: string
  content: string
  workers: number
  dry_run: boolean
  create_pr: boolean
}

export function submitPrd(data: PrdSubmitRequest): Promise<PrdSubmitResponse> {
  return apiFetch<PrdSubmitResponse>('/prd/submit', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function fetchPrdStatus(runId: string): Promise<PrdStatusResponse> {
  return apiFetch<PrdStatusResponse>(`/prd/status/${runId}`)
}
