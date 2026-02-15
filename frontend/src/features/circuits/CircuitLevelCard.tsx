import { ShieldCheck, ShieldAlert, ShieldQuestion } from 'lucide-react'
import type { CircuitHealthSummary } from '@/types/api'

const LEVEL_LABELS: Record<string, string> = {
  stage: 'Stage Breakers',
  worker: 'Worker Breakers',
  system: 'System Breakers',
}

export function CircuitLevelCard({ summary }: { summary: CircuitHealthSummary }) {
  const hasOpen = summary.open_count > 0
  const hasHalfOpen = summary.half_open_count > 0

  const Icon = hasOpen ? ShieldAlert : hasHalfOpen ? ShieldQuestion : ShieldCheck
  const iconColor = hasOpen
    ? 'text-status-failed'
    : hasHalfOpen
      ? 'text-status-pending'
      : 'text-status-passed'

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-3 flex items-center gap-2">
        <Icon className={`size-5 ${iconColor}`} />
        <h3 className="text-sm font-semibold">
          {LEVEL_LABELS[summary.level] ?? summary.level}
        </h3>
      </div>
      <div className="grid grid-cols-3 gap-3 text-center">
        <div>
          <p className="text-lg font-bold text-status-passed">
            {summary.closed_count}
          </p>
          <p className="text-xs text-muted-foreground">Closed</p>
        </div>
        <div>
          <p className="text-lg font-bold text-status-failed">
            {summary.open_count}
          </p>
          <p className="text-xs text-muted-foreground">Open</p>
        </div>
        <div>
          <p className="text-lg font-bold text-status-pending">
            {summary.half_open_count}
          </p>
          <p className="text-xs text-muted-foreground">Half-Open</p>
        </div>
      </div>
      <p className="mt-2 text-center text-xs text-muted-foreground">
        {summary.total_circuits} total
      </p>
    </div>
  )
}
