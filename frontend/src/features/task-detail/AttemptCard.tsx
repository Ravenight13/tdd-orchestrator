import { CheckCircle2, XCircle } from 'lucide-react'
import { StageIndicator } from '@/components/shared/StageIndicator'
import type { Attempt } from '@/types/api'

export function AttemptCard({ attempt }: { attempt: Attempt }) {
  return (
    <div className="flex items-start gap-3 rounded-md border border-border p-3">
      {attempt.success ? (
        <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-status-passed" />
      ) : (
        <XCircle className="mt-0.5 size-4 shrink-0 text-status-failed" />
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <StageIndicator stage={attempt.stage} />
          <span className="text-xs text-muted-foreground">
            Attempt #{attempt.attempt_number}
          </span>
          {attempt.started_at && (
            <span className="text-xs text-muted-foreground">
              {new Date(attempt.started_at).toLocaleTimeString()}
            </span>
          )}
        </div>
        {attempt.error_message && (
          <pre className="mt-2 whitespace-pre-wrap rounded bg-muted p-2 text-xs text-destructive">
            {attempt.error_message}
          </pre>
        )}
      </div>
    </div>
  )
}
