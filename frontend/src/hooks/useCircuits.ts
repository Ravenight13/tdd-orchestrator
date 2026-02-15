import { useState, useEffect, useCallback } from 'react'
import { fetchCircuitHealth, fetchCircuits } from '@/api/circuits'
import type { CircuitHealthSummary, CircuitBreakerDetail } from '@/types/api'
import { POLL_INTERVAL_MS } from '@/lib/constants'
import { useInterval } from './useInterval'

export function useCircuits() {
  const [health, setHealth] = useState<CircuitHealthSummary[]>([])
  const [circuits, setCircuits] = useState<CircuitBreakerDetail[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [h, c] = await Promise.all([fetchCircuitHealth(), fetchCircuits()])
      setHealth(h)
      setCircuits(c.circuits)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch circuits')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useInterval(() => void refresh(), POLL_INTERVAL_MS)

  return { health, circuits, loading, error, refresh }
}
