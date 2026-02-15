import { useState, useCallback } from 'react'
import { usePrdSubmission } from '@/hooks/usePrdSubmission'
import { PrdUploadZone } from '@/features/prd/PrdUploadZone'
import { PrdPreview } from '@/features/prd/PrdPreview'
import { PrdConfigForm } from '@/features/prd/PrdConfigForm'
import { PrdPipelineStepper } from '@/features/prd/PrdPipelineStepper'
import { ErrorBoundary } from '@/components/shared/ErrorBoundary'

export function PrdPage() {
  const [content, setContent] = useState<string | null>(null)
  const [filename, setFilename] = useState('')
  const { phase, status, error, submit, reset } = usePrdSubmission()

  const handleContentLoaded = useCallback((text: string, name: string) => {
    setContent(text)
    setFilename(name)
  }, [])

  const handleSubmit = useCallback(
    (config: { name: string; workers: number; dry_run: boolean; create_pr: boolean }) => {
      if (!content) return
      void submit({ ...config, content })
    },
    [content, submit],
  )

  const handleReset = useCallback(() => {
    reset()
    setContent(null)
    setFilename('')
  }, [reset])

  const isTracking = phase === 'tracking' || phase === 'completed' || phase === 'failed'

  return (
    <ErrorBoundary>
      <div className="mx-auto max-w-2xl space-y-6">
        {!isTracking ? (
          <>
            {!content ? (
              <PrdUploadZone onContentLoaded={handleContentLoaded} />
            ) : (
              <>
                <PrdPreview content={content} filename={filename} />
                <PrdConfigForm
                  defaultName={filename.replace(/\.(md|txt)$/, '')}
                  onSubmit={handleSubmit}
                  submitting={phase === 'submitting'}
                />
              </>
            )}
          </>
        ) : (
          <>
            <PrdPipelineStepper
              currentStage={status?.stage ?? 'pending'}
              status={status?.status ?? phase}
              error={error}
            />
            {status && (
              <div className="rounded-lg border border-border bg-card p-4">
                <dl className="grid grid-cols-2 gap-2 text-sm">
                  <dt className="text-muted-foreground">Run ID</dt>
                  <dd className="font-mono text-xs">{status.run_id}</dd>
                  <dt className="text-muted-foreground">Stage</dt>
                  <dd className="capitalize">{status.stage}</dd>
                  <dt className="text-muted-foreground">Status</dt>
                  <dd className="capitalize">{status.status}</dd>
                  {status.task_count !== null && (
                    <>
                      <dt className="text-muted-foreground">Tasks</dt>
                      <dd>{status.task_count}</dd>
                    </>
                  )}
                </dl>
              </div>
            )}
            {(phase === 'completed' || phase === 'failed') && (
              <button
                onClick={handleReset}
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
              >
                Submit Another
              </button>
            )}
          </>
        )}
      </div>
    </ErrorBoundary>
  )
}
