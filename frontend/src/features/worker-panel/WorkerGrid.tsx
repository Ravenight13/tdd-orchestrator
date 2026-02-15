import { WorkerCard } from './WorkerCard'
import { CardSkeleton } from '@/components/shared/LoadingSkeleton'
import { EmptyState } from '@/components/shared/EmptyState'
import { Users } from 'lucide-react'
import type { Worker } from '@/types/api'

interface WorkerGridProps {
  workers: Worker[]
  loading: boolean
}

export function WorkerGrid({ workers, loading }: WorkerGridProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <CardSkeleton key={i} />
        ))}
      </div>
    )
  }

  if (workers.length === 0) {
    return (
      <EmptyState
        icon={Users}
        title="No workers registered"
        description="Workers appear here when the orchestrator is running"
      />
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {workers.map((w) => (
        <WorkerCard key={w.id} worker={w} />
      ))}
    </div>
  )
}
