import { AttemptCard } from './AttemptCard'
import { EmptyState } from '@/components/shared/EmptyState'
import { ListChecks } from 'lucide-react'
import type { Attempt } from '@/types/api'

export function AttemptsTimeline({ attempts }: { attempts: Attempt[] }) {
  if (attempts.length === 0) {
    return (
      <EmptyState
        icon={ListChecks}
        title="No attempts yet"
        description="Attempts will appear here as the task progresses through TDD stages"
      />
    )
  }

  return (
    <div className="space-y-2">
      {attempts.map((a) => (
        <AttemptCard key={a.id} attempt={a} />
      ))}
    </div>
  )
}
