import { useState, useEffect, useCallback } from 'react'
import { useCircuits } from '@/hooks/useCircuits'
import { useSSE } from '@/hooks/useSSE'
import { CircuitOverview } from '@/features/circuits/CircuitOverview'
import { CircuitStateMachine } from '@/features/circuit-viz/CircuitStateMachine'
import { CircuitLevelTabs } from '@/features/circuit-viz/CircuitLevelTabs'
import { CircuitEventLog } from '@/features/circuit-viz/CircuitEventLog'
import { RefreshButton } from '@/components/shared/RefreshButton'
import { ErrorBoundary } from '@/components/shared/ErrorBoundary'
import { fetchCircuitEvents } from '@/api/circuits'
import type { CircuitLevel } from '@/types/domain'
import type { CircuitBreakerEvent } from '@/types/circuit-events'

export function CircuitsPage() {
  const { health, circuits, loading, refresh } = useCircuits()
  const [activeLevel, setActiveLevel] = useState<CircuitLevel | null>(null)
  const [selectedCircuitId, setSelectedCircuitId] = useState<string | null>(null)
  const [events, setEvents] = useState<CircuitBreakerEvent[]>([])

  useSSE({
    circuit_breaker_tripped: () => void refresh(),
  })

  const totalOpen = health.reduce((sum, h) => sum + h.open_count, 0)

  // Filter circuits by selected level
  const filtered = activeLevel
    ? circuits.filter((c) => c.level === activeLevel)
    : circuits

  // Auto-select first circuit when filter changes
  useEffect(() => {
    if (filtered.length > 0 && !filtered.find((c) => c.id === selectedCircuitId)) {
      setSelectedCircuitId(filtered[0].id)
    }
  }, [filtered, selectedCircuitId])

  // Fetch events for selected circuit
  const loadEvents = useCallback(async (id: string) => {
    try {
      const res = await fetchCircuitEvents(id)
      setEvents(res.events)
    } catch {
      setEvents([])
    }
  }, [])

  useEffect(() => {
    if (selectedCircuitId) {
      void loadEvents(selectedCircuitId)
    }
  }, [selectedCircuitId, loadEvents])

  const selectedCircuit = circuits.find((c) => c.id === selectedCircuitId)

  return (
    <ErrorBoundary>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            {circuits.length} circuit{circuits.length !== 1 ? 's' : ''}
            {totalOpen > 0 && (
              <span className="ml-1 text-status-failed">
                ({totalOpen} open)
              </span>
            )}
          </p>
          <RefreshButton onClick={() => void refresh()} loading={loading} />
        </div>

        <CircuitOverview health={health} loading={loading} />

        {circuits.length > 0 && (
          <>
            <CircuitLevelTabs
              health={health}
              activeLevel={activeLevel}
              onSelect={setActiveLevel}
            />

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              <div className="rounded-lg border border-border bg-card p-4">
                <h3 className="mb-4 text-sm font-semibold">State Machine</h3>
                {selectedCircuit && (
                  <CircuitStateMachine currentState={selectedCircuit.state} />
                )}
                {filtered.length > 0 && (
                  <div className="mt-4 flex flex-wrap gap-1">
                    {filtered.map((c) => (
                      <button
                        key={c.id}
                        onClick={() => setSelectedCircuitId(c.id)}
                        className={`rounded-md px-2 py-1 text-xs transition-colors ${
                          c.id === selectedCircuitId
                            ? 'bg-primary text-primary-foreground'
                            : 'bg-muted text-muted-foreground hover:text-foreground'
                        }`}
                      >
                        {c.identifier}
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <div className="rounded-lg border border-border bg-card p-4">
                <h3 className="mb-4 text-sm font-semibold">Recent Events</h3>
                <CircuitEventLog events={events} />
              </div>
            </div>
          </>
        )}
      </div>
    </ErrorBoundary>
  )
}
