import { apiFetch } from './client'
import type {
  TaskListResponse,
  TaskStats,
  TaskProgress,
  TaskDetail,
  RetryResponse,
} from '@/types/api'

export function fetchTasks(params?: {
  status?: string
  limit?: number
  offset?: number
}): Promise<TaskListResponse> {
  const search = new URLSearchParams()
  if (params?.status) search.set('status', params.status)
  if (params?.limit !== undefined) search.set('limit', String(params.limit))
  if (params?.offset !== undefined) search.set('offset', String(params.offset))
  const qs = search.toString()
  return apiFetch<TaskListResponse>(`/tasks${qs ? `?${qs}` : ''}`)
}

export function fetchTaskStats(): Promise<TaskStats> {
  return apiFetch<TaskStats>('/tasks/stats')
}

export function fetchTaskProgress(): Promise<TaskProgress> {
  return apiFetch<TaskProgress>('/tasks/progress')
}

export function fetchTaskDetail(key: string): Promise<TaskDetail> {
  return apiFetch<TaskDetail>(`/tasks/${encodeURIComponent(key)}`)
}

export function retryTask(key: string): Promise<RetryResponse> {
  return apiFetch<RetryResponse>(`/tasks/${encodeURIComponent(key)}/retry`, {
    method: 'POST',
  })
}
