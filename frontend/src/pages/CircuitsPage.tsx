import { useCircuits } from '@/hooks/useCircuits'
import { useSSE } from '@/hooks/useSSE'
import { CircuitOverview } from '@/features/circuits/CircuitOverview'
import { RefreshButton } from '@/components/shared/RefreshButton'
import { ErrorBoundary } from '@/components/shared/ErrorBoundary'

export function CircuitsPage() {
  const { health, circuits, loading, refresh } = useCircuits()

  useSSE({
    circuit_breaker_tripped: () => void refresh(),
  })

  const totalOpen = health.reduce((sum, h) => sum + h.open_count, 0)

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
      </div>
    </ErrorBoundary>
  )
}
