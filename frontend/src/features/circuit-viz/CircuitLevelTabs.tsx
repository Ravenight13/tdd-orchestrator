import { cn } from '@/lib/utils'
import type { CircuitLevel } from '@/types/domain'
import type { CircuitHealthSummary } from '@/types/api'

interface CircuitLevelTabsProps {
  health: CircuitHealthSummary[]
  activeLevel: CircuitLevel | null
  onSelect: (level: CircuitLevel | null) => void
}

const LEVELS: { id: CircuitLevel; label: string }[] = [
  { id: 'stage', label: 'Stage' },
  { id: 'worker', label: 'Worker' },
  { id: 'system', label: 'System' },
]

export function CircuitLevelTabs({ health, activeLevel, onSelect }: CircuitLevelTabsProps) {
  const countMap = new Map(health.map((h) => [h.level, h.total_circuits]))

  return (
    <div className="flex gap-1 rounded-lg bg-muted p-1">
      <button
        onClick={() => onSelect(null)}
        className={cn(
          'rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
          activeLevel === null
            ? 'bg-card text-foreground shadow-sm'
            : 'text-muted-foreground hover:text-foreground',
        )}
      >
        All
      </button>
      {LEVELS.map(({ id, label }) => {
        const count = countMap.get(id) ?? 0
        return (
          <button
            key={id}
            onClick={() => onSelect(id)}
            className={cn(
              'flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
              activeLevel === id
                ? 'bg-card text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {label}
            {count > 0 && (
              <span className="rounded-full bg-muted-foreground/20 px-1.5 py-0.5 text-[10px]">
                {count}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
