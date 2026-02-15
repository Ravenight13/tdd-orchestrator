import { ArrowLeft, RotateCcw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { StatusBadge } from '@/components/shared/StatusBadge'
import { ComplexityBadge } from '@/components/shared/ComplexityBadge'
import type { TaskDetail } from '@/types/api'

interface TaskDetailHeaderProps {
  task: TaskDetail
  onRetry?: () => void
}

export function TaskDetailHeader({ task, onRetry }: TaskDetailHeaderProps) {
  return (
    <div>
      <Link
        to="/tasks"
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Back to board
      </Link>
      <div className="flex items-start justify-between">
        <div>
          <p className="font-mono text-sm text-muted-foreground">{task.id}</p>
          <h2 className="mt-1 text-xl font-semibold">{task.title}</h2>
          <div className="mt-2 flex items-center gap-2">
            <StatusBadge status={task.status} />
            <ComplexityBadge complexity={task.complexity} />
            <span className="text-xs text-muted-foreground">
              Phase {task.phase} &middot; Seq {task.sequence}
            </span>
          </div>
        </div>
        {task.status === 'failed' && onRetry && (
          <button
            onClick={onRetry}
            className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm font-medium hover:bg-accent"
          >
            <RotateCcw className="size-3.5" />
            Retry
          </button>
        )}
      </div>
    </div>
  )
}
