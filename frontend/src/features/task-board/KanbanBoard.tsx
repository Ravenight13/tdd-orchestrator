import { useMemo } from 'react'
import { KanbanColumn } from './KanbanColumn'
import { COLUMNS } from './column-config'
import type { TaskSummary } from '@/types/api'
import type { TaskStatus } from '@/types/domain'

interface KanbanBoardProps {
  tasks: TaskSummary[]
  loading: boolean
  onRetry?: (key: string) => void
}

export function KanbanBoard({ tasks, loading, onRetry }: KanbanBoardProps) {
  const grouped = useMemo(() => {
    const map: Record<TaskStatus, TaskSummary[]> = {
      pending: [],
      running: [],
      passed: [],
      failed: [],
    }
    for (const task of tasks) {
      map[task.status]?.push(task)
    }
    return map
  }, [tasks])

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
      {COLUMNS.map((col) => (
        <KanbanColumn
          key={col.id}
          column={col}
          tasks={grouped[col.id] ?? []}
          loading={loading}
          onRetry={col.id === 'failed' ? onRetry : undefined}
        />
      ))}
    </div>
  )
}
