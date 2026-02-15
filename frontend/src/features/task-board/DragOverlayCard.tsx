import { TaskCard } from './TaskCard'
import type { TaskSummary } from '@/types/api'

export function DragOverlayCard({ task }: { task: TaskSummary }) {
  return (
    <div className="rounded-md shadow-xl ring-2 ring-primary/20">
      <TaskCard task={task} />
    </div>
  )
}
