import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from 'recharts'
import { useChartColors } from './useChartColors'
import type { MetricsJson } from '@/types/api'

export function StatusDistributionChart({ metrics }: { metrics: MetricsJson | null }) {
  const colors = useChartColors()

  if (!metrics || metrics.total_count === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
        No task data yet
      </div>
    )
  }

  const data = [
    { name: 'Pending', value: metrics.pending_count, color: colors.statusPending },
    { name: 'Running', value: metrics.running_count, color: colors.statusRunning },
    { name: 'Passed', value: metrics.passed_count, color: colors.statusPassed },
    { name: 'Failed', value: metrics.failed_count, color: colors.statusFailed },
  ].filter((d) => d.value > 0)

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={50}
            outerRadius={80}
            dataKey="value"
            paddingAngle={2}
          >
            {data.map((entry) => (
              <Cell key={entry.name} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              backgroundColor: colors.card,
              border: `1px solid ${colors.border}`,
              borderRadius: 6,
              color: colors.foreground,
            }}
          />
          <Legend
            formatter={(value: string) => (
              <span style={{ color: colors.foreground, fontSize: 12 }}>{value}</span>
            )}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
