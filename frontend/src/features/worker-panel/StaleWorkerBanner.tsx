import { AlertTriangle } from 'lucide-react'
import type { StaleWorker } from '@/types/api'

export function StaleWorkerBanner({ stale }: { stale: StaleWorker[] }) {
  if (stale.length === 0) return null

  return (
    <div className="rounded-lg border border-status-pending/30 bg-status-pending/5 p-4">
      <div className="flex items-center gap-2">
        <AlertTriangle className="size-4 text-status-pending" />
        <span className="text-sm font-medium text-status-pending">
          {stale.length} stale worker{stale.length > 1 ? 's' : ''} detected
        </span>
      </div>
      <div className="mt-2 space-y-1">
        {stale.map((w) => (
          <p key={w.id} className="text-xs text-muted-foreground">
            Worker {w.id}
            {w.minutes_since_heartbeat != null &&
              ` — no heartbeat for ${w.minutes_since_heartbeat}m`}
            {w.current_task_key && ` (working on ${w.current_task_key})`}
          </p>
        ))}
      </div>
    </div>
  )
}
