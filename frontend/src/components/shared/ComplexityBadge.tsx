import { cn } from '@/lib/utils'
import type { Complexity } from '@/types/domain'

const COMPLEXITY_STYLES: Record<Complexity, string> = {
  low: 'bg-emerald-50 text-emerald-700',
  medium: 'bg-amber-50 text-amber-700',
  high: 'bg-red-50 text-red-700',
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
