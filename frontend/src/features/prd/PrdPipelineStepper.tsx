import { Check, X, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

const STAGES = [
  { id: 'init', label: 'Init' },
  { id: 'branch', label: 'Branch' },
  { id: 'decompose', label: 'Decompose' },
  { id: 'execute', label: 'Execute' },
  { id: 'pr', label: 'PR' },
  { id: 'done', label: 'Done' },
]

interface PrdPipelineStepperProps {
  currentStage: string
  status: string
  error: string | null
}

export function PrdPipelineStepper({ currentStage, status, error }: PrdPipelineStepperProps) {
  const currentIdx = STAGES.findIndex((s) => s.id === currentStage)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        {STAGES.map((stage, idx) => {
          const isCompleted = idx < currentIdx || (idx === currentIdx && status === 'completed')
          const isCurrent = idx === currentIdx && status === 'running'
          const isFailed = idx === currentIdx && status === 'failed'

          return (
            <div key={stage.id} className="flex flex-col items-center gap-1">
              <div
                className={cn(
                  'flex size-8 items-center justify-center rounded-full border-2 text-xs font-medium transition-all',
                  isCompleted && 'border-status-passed bg-status-passed/10 text-status-passed',
                  isCurrent && 'border-status-running bg-status-running/10 text-status-running',
                  isFailed && 'border-status-failed bg-status-failed/10 text-status-failed',
                  !isCompleted && !isCurrent && !isFailed && 'border-border text-muted-foreground',
                )}
              >
                {isCompleted && <Check className="size-4" />}
                {isCurrent && <Loader2 className="size-4 animate-spin" />}
                {isFailed && <X className="size-4" />}
                {!isCompleted && !isCurrent && !isFailed && (idx + 1)}
              </div>
              <span className="text-[10px] font-medium text-muted-foreground">
                {stage.label}
              </span>
            </div>
          )
        })}
      </div>
      {error && (
        <p className="rounded-md bg-status-failed/10 px-3 py-2 text-sm text-status-failed">
          {error}
        </p>
      )}
    </div>
  )
}
