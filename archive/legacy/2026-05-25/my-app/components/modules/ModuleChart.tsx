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
  ReferenceLine,
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Factor } from '@/types/modules'
import { useThemeColors } from '@/hooks/useTheme'
import { formatDate } from '@/lib/utils'

interface ModuleChartProps {
  factors: Factor[]
  title?: string
  height?: number
  className?: string
}

interface ChartDataPoint {
  date: string
  [key: string]: string | number
}

export function ModuleChart({
  factors,
  title = 'Factor Trends',
  height = 300,
  className,
}: ModuleChartProps) {
  const { chartColors } = useThemeColors()

  const chartData = useMemo(() => {
    // Get all unique dates from all factors
    const allDates = new Set<string>()
    factors.forEach(factor => {
      factor.historicalData.forEach(point => {
        allDates.add(point.date.toISOString().split('T')[0])
      })
    })

    const sortedDates = Array.from(allDates).sort()

    // Create data points for each date
    return sortedDates.map(date => {
      const point: ChartDataPoint = { date }
      
      factors.forEach(factor => {
        const dataPoint = factor.historicalData.find(
          d => d.date.toISOString().split('T')[0] === date
        )
        if (dataPoint) {
          // Normalize value to 0-100 scale for comparison
          const values = factor.historicalData.map(h => h.value)
          const min = Math.min(...values)
          const max = Math.max(...values)
          const range = max - min || 1
          const normalized = ((dataPoint.value - min) / range) * 100
          point[factor.name] = Math.round(normalized)
        }
      })

      return point
    })
  }, [factors])

  const colors = [
    chartColors.primary,
    chartColors.secondary,
    chartColors.success,
    chartColors.warning,
    chartColors.danger,
    chartColors.neutral,
  ]

  const CustomTooltip = ({ active, payload, label }: {
    active?: boolean
    payload?: Array<{ name: string; value: number; color: string }>
    label?: string
  }) => {
    if (active && payload && payload.length) {
      return (
        <div className="rounded-lg border bg-background p-3 shadow-lg">
          <p className="text-sm text-muted-foreground mb-2">
            {formatDate(new Date(label || ''), 'medium')}
          </p>
          {payload.map((entry) => (
            <div key={entry.name} className="flex items-center gap-2">
              <div
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: entry.color }}
              />
              <span className="text-sm">{entry.name}:</span>
              <span className="text-sm font-medium">{entry.value}</span>
            </div>
          ))}
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
          <LineChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" opacity={0.5} />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value) => formatDate(new Date(value), 'short')}
            />
            <YAxis
              domain={[0, 100]}
              tick={{ fontSize: 12 }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value) => `${value}`}
            />
            <Tooltip content={<CustomTooltip />} />
            
            {factors.map((factor, index) => (
              <Line
                key={factor.id}
                type="monotone"
                dataKey={factor.name}
                stroke={colors[index % colors.length]}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, strokeWidth: 0 }}
                animationDuration={1500}
              />
            ))}
            
            {/* Reference lines */}
            <ReferenceLine y={70} stroke="#22c55e" strokeDasharray="5 5" strokeOpacity={0.5} />
            <ReferenceLine y={40} stroke="#eab308" strokeDasharray="5 5" strokeOpacity={0.5} />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  )
}
