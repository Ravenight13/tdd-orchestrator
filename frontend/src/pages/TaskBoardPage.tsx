import { useCallback } from 'react'
import { useTasks } from '@/hooks/useTasks'
import { useSSE } from '@/hooks/useSSE'
import { retryTask } from '@/api/tasks'
import { KanbanBoard } from '@/features/task-board/KanbanBoard'
import { StatsCardRow } from '@/features/stats/StatsCardRow'
import { RefreshButton } from '@/components/shared/RefreshButton'
import { ErrorBoundary } from '@/components/shared/ErrorBoundary'

export function TaskBoardPage() {
  const { tasks, stats, loading, refresh } = useTasks()

  useSSE({
    task_status_changed: () => void refresh(),
  })

  const handleRetry = useCallback(
    async (key: string) => {
      try {
        await retryTask(key)
        await refresh()
      } catch (err) {
        console.error('Failed to retry task:', err)
      }
    },
    [refresh],
  )

  return (
    <ErrorBoundary>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <StatsCardRow stats={stats} loading={loading} />
          <RefreshButton onClick={() => void refresh()} loading={loading} />
        </div>
        <KanbanBoard tasks={tasks} loading={loading} onRetry={handleRetry} />
      </div>
    </ErrorBoundary>
  )
}
