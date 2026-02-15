import { useWorkers } from '@/hooks/useWorkers'
import { WorkerGrid } from '@/features/worker-panel/WorkerGrid'
import { StaleWorkerBanner } from '@/features/worker-panel/StaleWorkerBanner'
import { RefreshButton } from '@/components/shared/RefreshButton'
import { ErrorBoundary } from '@/components/shared/ErrorBoundary'

export function WorkersPage() {
  const { workers, staleWorkers, loading, refresh } = useWorkers()

  return (
    <ErrorBoundary>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            {workers.length} worker{workers.length !== 1 ? 's' : ''} registered
          </p>
          <RefreshButton onClick={() => void refresh()} loading={loading} />
        </div>
        <StaleWorkerBanner stale={staleWorkers} />
        <WorkerGrid workers={workers} loading={loading} />
      </div>
    </ErrorBoundary>
  )
}
