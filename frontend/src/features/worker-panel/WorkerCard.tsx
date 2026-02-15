import { WorkerHeartbeatDot } from './WorkerHeartbeatDot'
import type { Worker } from '@/types/api'

function formatRelative(dateStr: string | null): string {
  if (!dateStr) return 'Never'
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}

export function WorkerCard({ worker }: { worker: Worker }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-3 flex items-center gap-2">
        <WorkerHeartbeatDot
          status={worker.status}
          lastHeartbeat={worker.last_heartbeat}
        />
        <span className="font-mono text-sm font-medium">
          Worker {worker.id}
        </span>
        <span className="ml-auto rounded-full bg-muted px-2 py-0.5 text-xs capitalize text-muted-foreground">
          {worker.status}
        </span>
      </div>
      <div className="space-y-1 text-xs text-muted-foreground">
        <div className="flex justify-between">
          <span>Last heartbeat</span>
          <span>{formatRelative(worker.last_heartbeat)}</span>
        </div>
        {worker.current_task_id != null && (
          <div className="flex justify-between">
            <span>Current task</span>
            <span className="font-mono">#{worker.current_task_id}</span>
          </div>
        )}
        {worker.branch_name && (
          <div className="flex justify-between">
            <span>Branch</span>
            <span className="font-mono truncate max-w-[140px]">
              {worker.branch_name}
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
