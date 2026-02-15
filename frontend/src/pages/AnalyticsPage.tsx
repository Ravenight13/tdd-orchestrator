import { useAnalytics } from '@/hooks/useAnalytics'
import { useSSE } from '@/hooks/useSSE'
import { RefreshButton } from '@/components/shared/RefreshButton'
import { ErrorBoundary } from '@/components/shared/ErrorBoundary'
import { TaskCompletionChart } from '@/features/analytics/TaskCompletionChart'
import { StageDurationChart } from '@/features/analytics/StageDurationChart'
import { InvocationStatsChart } from '@/features/analytics/InvocationStatsChart'
import { StatusDistributionChart } from '@/features/analytics/StatusDistributionChart'

export function AnalyticsPage() {
  const { stages, timeline, invocations, metrics, loading, refresh } = useAnalytics()

  useSSE({
    task_status_changed: () => void refresh(),
  })

  return (
    <ErrorBoundary>
      <div className="space-y-6">
        <div className="flex items-center justify-end">
          <RefreshButton onClick={() => void refresh()} loading={loading} />
        </div>
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="rounded-lg border border-border bg-card p-4">
            <h3 className="mb-4 text-sm font-semibold">Task Completions Over Time</h3>
            <TaskCompletionChart data={timeline} />
          </div>
          <div className="rounded-lg border border-border bg-card p-4">
            <h3 className="mb-4 text-sm font-semibold">Status Distribution</h3>
            <StatusDistributionChart metrics={metrics} />
          </div>
          <div className="rounded-lg border border-border bg-card p-4">
            <h3 className="mb-4 text-sm font-semibold">Avg Duration by Stage</h3>
            <StageDurationChart data={stages} />
          </div>
          <div className="rounded-lg border border-border bg-card p-4">
            <h3 className="mb-4 text-sm font-semibold">Token Usage by Stage</h3>
            <InvocationStatsChart data={invocations} />
          </div>
        </div>
      </div>
    </ErrorBoundary>
  )
}
