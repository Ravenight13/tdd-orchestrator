import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { useChartColors } from './useChartColors'
import type { TimelinePoint } from '@/types/analytics'

export function TaskCompletionChart({ data }: { data: TimelinePoint[] }) {
  const colors = useChartColors()

  if (data.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
        No completion data yet
      </div>
    )
  }

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={colors.border} />
          <XAxis
            dataKey="date"
            tick={{ fill: colors.mutedForeground, fontSize: 12 }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: colors.mutedForeground, fontSize: 12 }}
            tickLine={false}
            allowDecimals={false}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: colors.card,
              border: `1px solid ${colors.border}`,
              borderRadius: 6,
              color: colors.foreground,
            }}
          />
          <Area
            type="monotone"
            dataKey="completed"
            stroke={colors.statusPassed}
            fill={colors.statusPassed}
            fillOpacity={0.2}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
