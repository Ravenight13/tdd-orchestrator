import { Link } from 'react-router-dom'
import { RotateCcw } from 'lucide-react'
import { ComplexityBadge } from '@/components/shared/ComplexityBadge'
import type { TaskSummary } from '@/types/api'

interface TaskCardProps {
  task: TaskSummary
  onRetry?: (key: string) => void
}

export function TaskCard({ task, onRetry }: TaskCardProps) {
  return (
    <div className="group rounded-md border border-border bg-card p-3 shadow-sm transition-shadow hover:shadow-md">
      <div className="mb-2 flex items-start justify-between gap-2">
        <Link
          to={`/tasks/${task.id}`}
          className="text-xs font-mono text-muted-foreground hover:text-primary hover:underline"
        >
          {task.id}
        </Link>
        <ComplexityBadge complexity={task.complexity} />
      </div>
      <Link to={`/tasks/${task.id}`} className="block">
        <p className="text-sm font-medium leading-snug hover:underline">
          {task.title}
        </p>
      </Link>
      {task.status === 'failed' && onRetry && (
        <button
          onClick={() => onRetry(task.id)}
          className="mt-2 flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-status-failed hover:bg-status-failed/10"
        >
          <RotateCcw className="size-3" />
          Retry
        </button>
      )}
    </div>
  )
}

export function TaskCardSkeleton() {
  return (
    <div className="rounded-md border border-border bg-card p-3">
      <div className="mb-2 h-3 w-20 animate-pulse rounded bg-muted" />
      <div className="h-4 w-full animate-pulse rounded bg-muted" />
    </div>
  )
}
