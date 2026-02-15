import {
  SortableContext,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { cn } from '@/lib/utils'
import { SortableTaskCard } from './SortableTaskCard'
import { TaskCardSkeleton } from './TaskCard'
import type { ColumnDef } from './column-config'
import type { TaskSummary } from '@/types/api'

interface KanbanColumnProps {
  column: ColumnDef
  tasks: TaskSummary[]
  loading: boolean
  onRetry?: (key: string) => void
}

export function KanbanColumn({
  column,
  tasks,
  loading,
  onRetry,
}: KanbanColumnProps) {
  const taskIds = tasks.map((t) => t.id)

  return (
    <div className="flex min-w-[260px] flex-col">
      <div
        className={cn(
          'mb-3 flex items-center gap-2 border-t-2 pt-3',
          column.color,
        )}
      >
        <h3 className="text-xs font-semibold tracking-wider text-muted-foreground">
          {column.label}
        </h3>
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
          {tasks.length}
        </span>
      </div>
      <SortableContext items={taskIds} strategy={verticalListSortingStrategy}>
        <div className="flex-1 space-y-2 overflow-y-auto">
          {loading
            ? Array.from({ length: 3 }).map((_, i) => (
                <TaskCardSkeleton key={i} />
              ))
            : tasks.map((t) => (
                <SortableTaskCard key={t.id} task={t} onRetry={onRetry} />
              ))}
        </div>
      </SortableContext>
    </div>
  )
}
