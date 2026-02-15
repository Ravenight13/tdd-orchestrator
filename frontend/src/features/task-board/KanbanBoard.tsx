import { useEffect, useMemo, useState } from 'react'
import {
  DndContext,
  DragOverlay,
  closestCorners,
  type DragStartEvent,
  type DragEndEvent,
} from '@dnd-kit/core'
import { arrayMove } from '@dnd-kit/sortable'
import { KanbanColumn } from './KanbanColumn'
import { DragOverlayCard } from './DragOverlayCard'
import { COLUMNS } from './column-config'
import type { TaskSummary } from '@/types/api'
import type { TaskStatus } from '@/types/domain'

interface KanbanBoardProps {
  tasks: TaskSummary[]
  loading: boolean
  onRetry?: (key: string) => void
}

export function KanbanBoard({ tasks, loading, onRetry }: KanbanBoardProps) {
  const [orderedTasks, setOrderedTasks] = useState<TaskSummary[]>(tasks)
  const [activeId, setActiveId] = useState<string | null>(null)

  // Reset local order when upstream tasks change
  useEffect(() => {
    setOrderedTasks(tasks)
  }, [tasks])

  const grouped = useMemo(() => {
    const map: Record<TaskStatus, TaskSummary[]> = {
      pending: [],
      running: [],
      passed: [],
      failed: [],
    }
    for (const task of orderedTasks) {
      map[task.status]?.push(task)
    }
    return map
  }, [orderedTasks])

  const activeTask = useMemo(
    () => orderedTasks.find((t) => t.id === activeId) ?? null,
    [orderedTasks, activeId],
  )

  function handleDragStart(event: DragStartEvent) {
    setActiveId(String(event.active.id))
  }

  function handleDragEnd(event: DragEndEvent) {
    setActiveId(null)

    const { active, over } = event
    if (!over || active.id === over.id) return

    const activeIdStr = String(active.id)
    const overIdStr = String(over.id)

    // Find which column the active item belongs to
    const activeTask = orderedTasks.find((t) => t.id === activeIdStr)
    if (!activeTask) return

    const columnTasks = grouped[activeTask.status]
    const oldIndex = columnTasks.findIndex((t) => t.id === activeIdStr)
    const newIndex = columnTasks.findIndex((t) => t.id === overIdStr)

    if (oldIndex === -1 || newIndex === -1) return

    const reorderedColumn = arrayMove(columnTasks, oldIndex, newIndex)

    // Rebuild full task list with reordered column
    setOrderedTasks((prev) =>
      prev.map((task) => {
        if (task.status !== activeTask.status) return task
        const reorderedIdx = reorderedColumn.findIndex((t) => t.id === task.id)
        return reorderedIdx !== -1 ? reorderedColumn[reorderedIdx] : task
      }).sort((a, b) => {
        if (a.status !== b.status) return 0
        if (a.status !== activeTask.status) return 0
        const aIdx = reorderedColumn.findIndex((t) => t.id === a.id)
        const bIdx = reorderedColumn.findIndex((t) => t.id === b.id)
        return aIdx - bIdx
      }),
    )
  }

  function handleDragCancel() {
    setActiveId(null)
  }

  return (
    <DndContext
      collisionDetection={closestCorners}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
      onDragCancel={handleDragCancel}
    >
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
      <DragOverlay>
        {activeTask ? <DragOverlayCard task={activeTask} /> : null}
      </DragOverlay>
    </DndContext>
  )
}
