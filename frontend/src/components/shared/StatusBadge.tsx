import { cn } from '@/lib/utils'
import type { TaskStatus } from '@/types/domain'

const STATUS_STYLES: Record<TaskStatus, string> = {
  pending: 'bg-status-pending/15 text-status-pending',
  running: 'bg-status-running/15 text-status-running',
  passed: 'bg-status-passed/15 text-status-passed',
  failed: 'bg-status-failed/15 text-status-failed',
}

const STATUS_LABELS: Record<TaskStatus, string> = {
  pending: 'Pending',
  running: 'Running',
  passed: 'Passed',
  failed: 'Failed',
}

export function StatusBadge({ status }: { status: TaskStatus }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
        STATUS_STYLES[status],
      )}
    >
      {STATUS_LABELS[status]}
    </span>
  )
}
