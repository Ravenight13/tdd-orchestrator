import { cn } from '@/lib/utils'

const STAGE_COLORS: Record<string, string> = {
  RED: 'bg-red-500',
  RED_FIX: 'bg-orange-500',
  GREEN: 'bg-green-500',
  VERIFY: 'bg-blue-500',
  FIX: 'bg-amber-500',
  RE_VERIFY: 'bg-indigo-500',
}

export function StageIndicator({ stage }: { stage: string }) {
  const color = STAGE_COLORS[stage] ?? 'bg-muted-foreground'
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <span className={cn('size-2 rounded-full', color)} />
      {stage}
    </span>
  )
}
