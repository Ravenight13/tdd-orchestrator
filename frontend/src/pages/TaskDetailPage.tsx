import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { fetchTaskDetail, retryTask } from '@/api/tasks'
import { useSSE } from '@/hooks/useSSE'
import { TaskDetailHeader } from '@/features/task-detail/TaskDetailHeader'
import { StageProgressBar } from '@/features/task-detail/StageProgressBar'
import { AttemptsTimeline } from '@/features/task-detail/AttemptsTimeline'
import { ListSkeleton } from '@/components/shared/LoadingSkeleton'
import { ErrorBoundary } from '@/components/shared/ErrorBoundary'
import type { TaskDetail } from '@/types/api'

export function TaskDetailPage() {
  const { taskKey } = useParams<{ taskKey: string }>()
  const [task, setTask] = useState<TaskDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!taskKey) return
    try {
      const data = await fetchTaskDetail(taskKey)
      setTask(data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load task')
    } finally {
      setLoading(false)
    }
  }, [taskKey])

  useEffect(() => {
    void load()
  }, [load])

  useSSE({
    task_status_changed: (data) => {
      try {
        const parsed = JSON.parse(data) as { task_key?: string }
        if (parsed.task_key === taskKey) void load()
      } catch {
        // ignore malformed data
      }
    },
  })

  const handleRetry = useCallback(async () => {
    if (!taskKey) return
    try {
      await retryTask(taskKey)
      await load()
    } catch (err) {
      console.error('Failed to retry:', err)
    }
  }, [taskKey, load])

  if (loading) {
    return <ListSkeleton rows={6} />
  }

  if (error || !task) {
    return (
      <div className="rounded-lg border border-destructive/20 bg-destructive/5 p-6 text-center">
        <p className="text-sm text-destructive">{error ?? 'Task not found'}</p>
      </div>
    )
  }

  return (
    <ErrorBoundary>
      <div className="mx-auto max-w-3xl space-y-6">
        <TaskDetailHeader task={task} onRetry={handleRetry} />

        <div className="rounded-lg border border-border p-4">
          <h3 className="mb-3 text-sm font-medium text-muted-foreground">
            Stage Progress
          </h3>
          <StageProgressBar attempts={task.attempts} />
        </div>

        <div>
          <h3 className="mb-3 text-sm font-medium text-muted-foreground">
            Attempts ({task.attempts.length})
          </h3>
          <AttemptsTimeline attempts={task.attempts} />
        </div>
      </div>
    </ErrorBoundary>
  )
}
