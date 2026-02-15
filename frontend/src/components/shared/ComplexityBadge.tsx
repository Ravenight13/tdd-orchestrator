import { cn } from '@/lib/utils'
import type { Complexity } from '@/types/domain'

const COMPLEXITY_STYLES: Record<Complexity, string> = {
  low: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300',
  medium: 'bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300',
  high: 'bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300',
}

export function ComplexityBadge({ complexity }: { complexity: Complexity }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium capitalize',
        COMPLEXITY_STYLES[complexity],
      )}
    >
      {complexity}
    </span>
  )
}
