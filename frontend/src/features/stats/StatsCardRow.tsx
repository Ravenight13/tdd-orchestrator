import {
  Clock,
  Play,
  CheckCircle2,
  XCircle,
  BarChart3,
} from 'lucide-react'
import { StatCard } from './StatCard'
import type { TaskStats } from '@/types/api'
import { CardSkeleton } from '@/components/shared/LoadingSkeleton'

interface StatsCardRowProps {
  stats: TaskStats | null
  loading: boolean
}

export function StatsCardRow({ stats, loading }: StatsCardRowProps) {
  if (loading || !stats) {
    return (
      <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <CardSkeleton key={i} />
        ))}
      </div>
    )
  }

  return (
    <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
      <StatCard label="Total" value={stats.total} icon={BarChart3} />
      <StatCard
        label="Pending"
        value={stats.pending}
        icon={Clock}
        color="text-status-pending"
      />
      <StatCard
        label="Running"
        value={stats.running}
        icon={Play}
        color="text-status-running"
      />
      <StatCard
        label="Passed"
        value={stats.passed}
        icon={CheckCircle2}
        color="text-status-passed"
      />
      <StatCard
        label="Failed"
        value={stats.failed}
        icon={XCircle}
        color="text-status-failed"
      />
    </div>
  )
}
