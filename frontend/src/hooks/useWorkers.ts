import { useState, useEffect, useCallback } from 'react'
import { fetchWorkers, fetchStaleWorkers } from '@/api/workers'
import type { Worker, StaleWorker } from '@/types/api'
import { POLL_INTERVAL_MS } from '@/lib/constants'
import { useInterval } from './useInterval'

export function useWorkers() {
  const [workers, setWorkers] = useState<Worker[]>([])
  const [staleWorkers, setStaleWorkers] = useState<StaleWorker[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [wRes, sRes] = await Promise.all([
        fetchWorkers(),
        fetchStaleWorkers(),
      ])
      setWorkers(wRes.workers)
      setStaleWorkers(sRes.items)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch workers')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useInterval(() => void refresh(), POLL_INTERVAL_MS)

  return { workers, staleWorkers, loading, error, refresh }
}
