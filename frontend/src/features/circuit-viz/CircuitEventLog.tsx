import type { CircuitBreakerEvent } from '@/types/circuit-events'

function formatEventType(type: string): string {
  return type.replace(/_/g, ' ')
}

function stateColor(state: string | null): string {
  if (!state) return 'text-muted-foreground'
  switch (state) {
    case 'closed': return 'text-status-passed'
    case 'open': return 'text-status-failed'
    case 'half_open': return 'text-status-pending'
    default: return 'text-muted-foreground'
  }
}

export function CircuitEventLog({ events }: { events: CircuitBreakerEvent[] }) {
  if (events.length === 0) {
    return (
      <p className="py-4 text-center text-sm text-muted-foreground">
        No events recorded
      </p>
    )
  }

  return (
    <div className="max-h-64 space-y-1 overflow-y-auto">
      {events.map((evt) => (
        <div
          key={evt.id}
          className="flex items-center gap-3 rounded-md px-3 py-1.5 text-xs hover:bg-muted/50"
        >
          <span className="w-28 shrink-0 text-muted-foreground">
            {new Date(evt.created_at).toLocaleString(undefined, {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>
          <span className="font-medium capitalize">
            {formatEventType(evt.event_type)}
          </span>
          {evt.from_state && evt.to_state && (
            <span className="flex items-center gap-1">
              <span className={stateColor(evt.from_state)}>{evt.from_state}</span>
              <span className="text-muted-foreground">&rarr;</span>
              <span className={stateColor(evt.to_state)}>{evt.to_state}</span>
            </span>
          )}
        </div>
      ))}
    </div>
  )
}
