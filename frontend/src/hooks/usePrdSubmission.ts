import { useState, useCallback, useRef, useEffect } from 'react'
import { submitPrd, fetchPrdStatus } from '@/api/prd'
import type { PrdStatusResponse } from '@/types/prd'

type PrdPhase = 'idle' | 'submitting' | 'tracking' | 'completed' | 'failed'

export function usePrdSubmission() {
  const [phase, setPhase] = useState<PrdPhase>('idle')
  const [runId, setRunId] = useState<string | null>(null)
  const [status, setStatus] = useState<PrdStatusResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [])

  const submit = useCallback(async (data: {
    name: string
    content: string
    workers: number
    dry_run: boolean
    create_pr: boolean
  }) => {
    setPhase('submitting')
    setError(null)
    try {
      const res = await submitPrd(data)
      setRunId(res.run_id)
      setPhase('tracking')

      // Start polling
      pollRef.current = setInterval(async () => {
        try {
          const s = await fetchPrdStatus(res.run_id)
          setStatus(s)
          if (s.status === 'completed') {
            setPhase('completed')
            stopPolling()
          } else if (s.status === 'failed') {
            setPhase('failed')
            setError(s.error_message ?? 'Pipeline failed')
            stopPolling()
          }
        } catch {
          // Continue polling on transient errors
        }
      }, 2000)
    } catch (err) {
      setPhase('failed')
      setError(err instanceof Error ? err.message : 'Submission failed')
    }
  }, [stopPolling])

  const reset = useCallback(() => {
    stopPolling()
    setPhase('idle')
    setRunId(null)
    setStatus(null)
    setError(null)
  }, [stopPolling])

  useEffect(() => stopPolling, [stopPolling])

  return { phase, runId, status, error, submit, reset }
}
