import { cn } from '@/lib/utils'

interface WorkerHeartbeatDotProps {
  status: string
  lastHeartbeat: string | null
}

export function WorkerHeartbeatDot({ status, lastHeartbeat }: WorkerHeartbeatDotProps) {
  const isStale =
    lastHeartbeat != null &&
    Date.now() - new Date(lastHeartbeat).getTime() > 10 * 60 * 1000

  const color =
    status === 'dead'
      ? 'bg-status-failed'
      : isStale
        ? 'bg-status-pending animate-pulse'
        : status === 'active'
          ? 'bg-status-passed'
          : 'bg-muted-foreground'

  return <span className={cn('inline-block size-2.5 rounded-full', color)} />
}
