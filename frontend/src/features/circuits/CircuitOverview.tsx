import { CircuitLevelCard } from './CircuitLevelCard'
import { CardSkeleton } from '@/components/shared/LoadingSkeleton'
import { EmptyState } from '@/components/shared/EmptyState'
import { ShieldCheck } from 'lucide-react'
import type { CircuitHealthSummary } from '@/types/api'

interface CircuitOverviewProps {
  health: CircuitHealthSummary[]
  loading: boolean
}

export function CircuitOverview({ health, loading }: CircuitOverviewProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <CardSkeleton key={i} />
        ))}
      </div>
    )
  }

  if (health.length === 0) {
    return (
      <EmptyState
        icon={ShieldCheck}
        title="No circuit breakers"
        description="Circuit breakers appear here during orchestration runs"
      />
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      {health.map((h) => (
        <CircuitLevelCard key={h.level} summary={h} />
      ))}
    </div>
  )
}
