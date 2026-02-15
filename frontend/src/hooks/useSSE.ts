import { useEffect, useRef, useCallback } from 'react'
import { API_BASE_URL, SSE_RECONNECT_BASE_MS, SSE_RECONNECT_MAX_MS } from '@/lib/constants'
import type { SSEEventType } from '@/types/events'

type SSEHandler = (data: string) => void

export function useSSE(handlers: Partial<Record<SSEEventType, SSEHandler>>) {
  const handlersRef = useRef(handlers)
  handlersRef.current = handlers

  const reconnectDelay = useRef(SSE_RECONNECT_BASE_MS)

  const connect = useCallback(() => {
    const es = new EventSource(`${API_BASE_URL}/events`)

    es.onopen = () => {
      reconnectDelay.current = SSE_RECONNECT_BASE_MS
    }

    es.onerror = () => {
      es.close()
      const delay = reconnectDelay.current
      reconnectDelay.current = Math.min(delay * 2, SSE_RECONNECT_MAX_MS)
      setTimeout(connect, delay)
    }

    // Register typed event listeners
    const eventTypes: SSEEventType[] = [
      'task_status_changed',
      'circuit_breaker_tripped',
      'heartbeat',
    ]

    for (const type of eventTypes) {
      es.addEventListener(type, (evt: MessageEvent) => {
        handlersRef.current[type]?.(evt.data as string)
      })
    }

    return es
  }, [])

  useEffect(() => {
    const es = connect()
    return () => es.close()
  }, [connect])
}
