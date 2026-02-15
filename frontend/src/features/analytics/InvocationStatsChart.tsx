import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { useChartColors } from './useChartColors'
import type { InvocationStatsItem } from '@/types/analytics'

export function InvocationStatsChart({ data }: { data: InvocationStatsItem[] }) {
  const colors = useChartColors()

  if (data.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
        No invocation data yet
      </div>
    )
  }

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={colors.border} />
          <XAxis
            dataKey="stage"
            tick={{ fill: colors.mutedForeground, fontSize: 12 }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: colors.mutedForeground, fontSize: 12 }}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: colors.card,
              border: `1px solid ${colors.border}`,
              borderRadius: 6,
              color: colors.foreground,
            }}
            formatter={(value: number) => [value.toLocaleString(), 'Total Tokens']}
          />
          <Bar dataKey="total_tokens" fill={colors.statusPending} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
