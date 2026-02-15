import { cn } from '@/lib/utils'
import type { Attempt } from '@/types/api'

const TDD_STAGES = ['RED', 'RED_FIX', 'GREEN', 'VERIFY', 'FIX', 'RE_VERIFY'] as const

function stageStatus(
  stage: string,
  attempts: Attempt[],
): 'complete' | 'failed' | 'active' | 'pending' {
  const stageAttempts = attempts.filter((a) => a.stage === stage)
  if (stageAttempts.length === 0) return 'pending'
  const lastAttempt = stageAttempts[stageAttempts.length - 1]
  if (lastAttempt?.success) return 'complete'
  // If there are attempts but none succeeded and it's the latest stage worked on
  return 'failed'
}

export function StageProgressBar({ attempts }: { attempts: Attempt[] }) {
  const activeStages = new Set(attempts.map((a) => a.stage))
  const relevantStages = TDD_STAGES.filter(
    (s) => activeStages.has(s) || TDD_STAGES.indexOf(s) <= Math.max(...TDD_STAGES.map((st, i) => (activeStages.has(st) ? i : -1)))
  )

  if (relevantStages.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">No stage attempts yet</p>
    )
  }

  return (
    <div className="flex gap-1">
      {relevantStages.map((stage) => {
        const status = stageStatus(stage, attempts)
        return (
          <div key={stage} className="flex-1">
            <div
              className={cn(
                'h-2 rounded-full',
                status === 'complete' && 'bg-status-passed',
                status === 'failed' && 'bg-status-failed',
                status === 'active' && 'bg-status-running',
                status === 'pending' && 'bg-muted',
              )}
            />
            <p className="mt-1 text-center text-[10px] text-muted-foreground">
              {stage}
            </p>
          </div>
        )
      })}
    </div>
  )
}
