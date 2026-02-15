import type { TaskStatus } from '@/types/domain'

export interface ColumnDef {
  id: TaskStatus
  label: string
  color: string
}

export const COLUMNS: ColumnDef[] = [
  { id: 'pending', label: 'PENDING', color: 'border-status-pending' },
  { id: 'running', label: 'IN PROGRESS', color: 'border-status-running' },
  { id: 'passed', label: 'PASSED', color: 'border-status-passed' },
  { id: 'failed', label: 'FAILED', color: 'border-status-failed' },
]
