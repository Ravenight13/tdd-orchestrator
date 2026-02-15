import { Link } from 'react-router-dom'
import { useTasks } from '@/hooks/useTasks'
import { useWorkers } from '@/hooks/useWorkers'
import { StatsCardRow } from '@/features/stats/StatsCardRow'
import { ProgressRing } from '@/features/stats/ProgressRing'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { ComplexityBadge } from '@/components/shared/ComplexityBadge'
import { Skeleton } from '@/components/shared/LoadingSkeleton'
import { ErrorBoundary } from '@/components/shared/ErrorBoundary'

export function DashboardPage() {
  const { tasks, stats, loading } = useTasks(10)
  const { workers, loading: wLoading } = useWorkers()

  const totalTasks = stats?.total ?? 0
  const passedTasks = stats?.passed ?? 0
  const percentage = totalTasks > 0 ? (passedTasks / totalTasks) * 100 : 0

  return (
    <ErrorBoundary>
      <div className="space-y-6">
        <StatsCardRow stats={stats} loading={loading} />

        <div className="grid gap-6 lg:grid-cols-3">
          {/* Progress Ring */}
          <div className="flex flex-col items-center justify-center rounded-lg border border-border p-6">
            <h2 className="mb-4 text-sm font-medium text-muted-foreground">
              Overall Progress
            </h2>
            {loading ? (
              <Skeleton className="size-[120px] rounded-full" />
            ) : (
              <ProgressRing percentage={percentage} />
            )}
            <p className="mt-3 text-xs text-muted-foreground">
              {passedTasks} of {totalTasks} tasks passed
            </p>
          </div>

          {/* Recent Tasks */}
          <div className="rounded-lg border border-border p-4 lg:col-span-2">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-medium text-muted-foreground">
                Recent Tasks
              </h2>
              <Link
                to="/tasks"
                className="text-xs text-primary underline underline-offset-4"
              >
                View all
              </Link>
            </div>
            {loading ? (
              <div className="space-y-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : (
              <div className="space-y-1">
                {tasks.slice(0, 8).map((t) => (
                  <Link
                    key={t.id}
                    to={`/tasks/${t.id}`}
                    className="flex items-center justify-between rounded-md px-3 py-2 text-sm hover:bg-accent"
                  >
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-xs text-muted-foreground">
                        {t.id}
                      </span>
                      <span className="truncate">{t.title}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <ComplexityBadge complexity={t.complexity} />
                      <StatusBadge status={t.status} />
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Worker Summary */}
        <div className="rounded-lg border border-border p-4">
          <h2 className="mb-3 text-sm font-medium text-muted-foreground">
            Workers
          </h2>
          {wLoading ? (
            <Skeleton className="h-10 w-full" />
          ) : workers.length === 0 ? (
            <p className="text-sm text-muted-foreground">No workers registered</p>
          ) : (
            <div className="flex flex-wrap gap-3">
              {workers.map((w) => (
                <div
                  key={w.id}
                  className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm"
                >
                  <div
                    className={`size-2 rounded-full ${
                      w.status === 'active'
                        ? 'bg-status-passed'
                        : w.status === 'idle'
                          ? 'bg-status-pending'
                          : 'bg-status-failed'
                    }`}
                  />
                  <span className="font-mono text-xs">Worker {w.id}</span>
                  <span className="text-xs text-muted-foreground capitalize">
                    {w.status}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </ErrorBoundary>
  )
}
