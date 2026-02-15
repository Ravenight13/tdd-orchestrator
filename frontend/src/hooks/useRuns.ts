import { useState, useEffect, useCallback } from 'react'
import { fetchRuns } from '@/api/runs'
import type { Run } from '@/types/api'
import { POLL_INTERVAL_MS } from '@/lib/constants'
import { useInterval } from './useInterval'

export function useRuns() {
  const [runs, setRuns] = useState<Run[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const data = await fetchRuns()
      setRuns(data.runs)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch runs')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useInterval(() => void refresh(), POLL_INTERVAL_MS)

  return { runs, loading, error, refresh }
}
