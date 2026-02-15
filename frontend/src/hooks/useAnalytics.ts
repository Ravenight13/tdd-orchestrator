import { useState, useEffect, useCallback } from 'react'
import {
  fetchAttemptsByStage,
  fetchTaskCompletionTimeline,
  fetchInvocationStats,
} from '@/api/analytics'
import { fetchMetrics } from '@/api/metrics'
import type { StageAttemptStats, TimelinePoint, InvocationStatsItem } from '@/types/analytics'
import type { MetricsJson } from '@/types/api'
import { POLL_INTERVAL_MS } from '@/lib/constants'
import { useInterval } from './useInterval'

export function useAnalytics() {
  const [stages, setStages] = useState<StageAttemptStats[]>([])
  const [timeline, setTimeline] = useState<TimelinePoint[]>([])
  const [invocations, setInvocations] = useState<InvocationStatsItem[]>([])
  const [metrics, setMetrics] = useState<MetricsJson | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [a, t, i, m] = await Promise.all([
        fetchAttemptsByStage(),
        fetchTaskCompletionTimeline(),
        fetchInvocationStats(),
        fetchMetrics(),
      ])
      setStages(a.stages)
      setTimeline(t.timeline)
      setInvocations(i.invocations)
      setMetrics(m)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch analytics')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useInterval(() => void refresh(), POLL_INTERVAL_MS)

  return { stages, timeline, invocations, metrics, loading, error, refresh }
}
