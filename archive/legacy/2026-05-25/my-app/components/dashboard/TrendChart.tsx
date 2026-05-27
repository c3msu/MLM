'use client'

import React, { useMemo } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
  Legend,
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ScoreHistoryPoint } from '@/types/scores'
import { useThemeColors } from '@/hooks/useTheme'
import { formatDate } from '@/lib/utils'

interface TrendChartProps {
  data: ScoreHistoryPoint[]
  title?: string
  showArea?: boolean
  height?: number
  className?: string
}

interface ChartDataPoint {
  date: string
  score: number
  status: string
}

export function TrendChart({
  data,
  title = 'Score Trend',
  showArea = true,
  height = 300,
  className,
}: TrendChartProps) {
  const { chartColors } = useThemeColors()

  const chartData: ChartDataPoint[] = useMemo(() => {
    return data.map(point => ({
      date: formatDate(point.date, 'short'),
      score: point.score,
      status: point.status,
    }))
  }, [data])

  const getStrokeColor = (score: number) => {
    if (score >= 70) return chartColors.success
    if (score >= 40) return chartColors.warning
    return chartColors.danger
  }

  const CustomTooltip = ({ active, payload, label }: {
    active?: boolean
    payload?: Array<{ value: number }>
    label?: string
  }) => {
    if (active && payload && payload.length) {
      const score = payload[0].value
      return (
        <div className="rounded-lg border bg-background p-3 shadow-lg">
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className="text-lg font-bold" style={{ color: getStrokeColor(score) }}>
            Score: {score}
          </p>
        </div>
      )
    }
    return null
  }

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="text-lg">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={height}>
          {showArea ? (
            <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="scoreGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={chartColors.primary} stopOpacity={0.3} />
                  <stop offset="95%" stopColor={chartColors.primary} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" opacity={0.5} />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 12 }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                domain={[0, 100]}
                tick={{ fontSize: 12 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(value) => `${value}`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Area
                type="monotone"
                dataKey="score"
                stroke={chartColors.primary}
                strokeWidth={2}
                fill="url(#scoreGradient)"
                animationDuration={1500}
              />
              {/* Reference lines for thresholds */}
              <line
                x1="0"
                y1="70%"
                x2="100%"
                y2="70%"
                stroke="#22c55e"
                strokeDasharray="5 5"
                strokeOpacity={0.5}
              />
              <line
                x1="0"
                y1="40%"
                x2="100%"
                y2="40%"
                stroke="#eab308"
                strokeDasharray="5 5"
                strokeOpacity={0.5}
              />
            </AreaChart>
          ) : (
            <LineChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" opacity={0.5} />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 12 }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                domain={[0, 100]}
                tick={{ fontSize: 12 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(value) => `${value}`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Line
                type="monotone"
                dataKey="score"
                stroke={chartColors.primary}
                strokeWidth={2}
                dot={{ fill: chartColors.primary, strokeWidth: 2, r: 4 }}
                activeDot={{ r: 6, strokeWidth: 0 }}
                animationDuration={1500}
              />
            </LineChart>
          )}
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}
