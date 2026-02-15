import { useState, useEffect, useCallback } from 'react'
import { fetchMetrics } from '@/api/metrics'
import type { MetricsJson } from '@/types/api'
import { POLL_INTERVAL_MS } from '@/lib/constants'
import { useInterval } from './useInterval'

export function useMetrics() {
  const [metrics, setMetrics] = useState<MetricsJson | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const data = await fetchMetrics()
      setMetrics(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch metrics')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useInterval(() => void refresh(), POLL_INTERVAL_MS)

  return { metrics, loading, error, refresh }
}
