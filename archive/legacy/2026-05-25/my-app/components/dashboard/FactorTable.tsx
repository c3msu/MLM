'use client'

import React from 'react'
import { motion } from 'framer-motion'
import { ArrowUp, ArrowDown, Minus, TrendingUp, TrendingDown } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Factor } from '@/types/modules'
import { cn, formatNumber } from '@/lib/utils'

interface FactorTableProps {
  factors: Factor[]
  title?: string
  className?: string
}

function FactorRow({ factor, index }: { factor: Factor; index: number }) {
  const isPositive = factor.change > 0
  const isNegative = factor.change < 0
  const isNeutral = factor.change === 0

  return (
    <motion.tr
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.05, duration: 0.3 }}
      className="border-b last:border-b-0 hover:bg-muted/50 transition-colors"
    >
      <td className="py-3 px-4">
        <div>
          <p className="font-medium text-sm">{factor.name}</p>
          <p className="text-xs text-muted-foreground line-clamp-1">
            {factor.description}
          </p>
        </div>
      </td>
      <td className="py-3 px-4">
        <span className="font-mono text-sm">{formatNumber(factor.value)}</span>
      </td>
      <td className="py-3 px-4">
        <div className="flex items-center gap-1">
          {isPositive && <ArrowUp className="h-3 w-3 text-score-green" />}
          {isNegative && <ArrowDown className="h-3 w-3 text-score-red" />}
          {isNeutral && <Minus className="h-3 w-3 text-muted-foreground" />}
          <span
            className={cn(
              'text-sm font-medium',
              isPositive && 'text-score-green',
              isNegative && 'text-score-red',
              isNeutral && 'text-muted-foreground'
            )}
          >
            {isPositive ? '+' : ''}
            {formatNumber(factor.changePercent, 1)}%
          </span>
        </div>
      </td>
      <td className="py-3 px-4">
        <Badge
          variant={
            factor.status === 'positive'
              ? 'success'
              : factor.status === 'negative'
              ? 'critical'
              : 'secondary'
          }
          className="text-xs"
        >
          {factor.status === 'positive' && 'Positive'}
          {factor.status === 'negative' && 'Negative'}
          {factor.status === 'neutral' && 'Neutral'}
        </Badge>
      </td>
      <td className="py-3 px-4">
        <div className="flex items-center gap-2">
          <div className="flex-1 h-2 w-16 rounded-full bg-muted overflow-hidden">
            <div
              className={cn(
                'h-full rounded-full transition-all duration-500',
                factor.status === 'positive' && 'bg-score-green',
                factor.status === 'negative' && 'bg-score-red',
                factor.status === 'neutral' && 'bg-muted-foreground'
              )}
              style={{ width: `${factor.contribution}%` }}
            />
          </div>
          <span className="text-xs text-muted-foreground w-8">
            {formatNumber(factor.contribution, 0)}
          </span>
        </div>
      </td>
    </motion.tr>
  )
}

export function FactorTable({ factors, title = 'Key Factors', className }: FactorTableProps) {
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="text-lg">{title}</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="py-2 px-4 text-left text-xs font-medium text-muted-foreground uppercase">
                  Factor
                </th>
                <th className="py-2 px-4 text-left text-xs font-medium text-muted-foreground uppercase">
                  Value
                </th>
                <th className="py-2 px-4 text-left text-xs font-medium text-muted-foreground uppercase">
                  Change
                </th>
                <th className="py-2 px-4 text-left text-xs font-medium text-muted-foreground uppercase">
                  Status
                </th>
                <th className="py-2 px-4 text-left text-xs font-medium text-muted-foreground uppercase">
                  Contribution
                </th>
              </tr>
            </thead>
            <tbody>
              {factors.map((factor, index) => (
                <FactorRow key={factor.id} factor={factor} index={index} />
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}
