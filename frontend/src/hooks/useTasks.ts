import { useState, useEffect, useCallback } from 'react'
import { fetchTasks, fetchTaskStats } from '@/api/tasks'
import type { TaskSummary, TaskStats } from '@/types/api'
import { POLL_INTERVAL_MS } from '@/lib/constants'
import { useInterval } from './useInterval'

export function useTasks(limit = 200) {
  const [tasks, setTasks] = useState<TaskSummary[]>([])
  const [stats, setStats] = useState<TaskStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [taskRes, statsRes] = await Promise.all([
        fetchTasks({ limit }),
        fetchTaskStats(),
      ])
      setTasks(taskRes.tasks)
      setStats(statsRes)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch tasks')
    } finally {
      setLoading(false)
    }
  }, [limit])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useInterval(() => void refresh(), POLL_INTERVAL_MS)

  return { tasks, stats, loading, error, refresh }
}
