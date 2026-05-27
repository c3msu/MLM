'use client'

import React from 'react'
import { motion } from 'framer-motion'
import { ArrowUp, ArrowDown, Minus, TrendingUp, TrendingDown, Activity } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Factor } from '@/types/modules'
import { cn, formatNumber } from '@/lib/utils'

interface FactorListProps {
  factors: Factor[]
  className?: string
}

function FactorCard({ factor, index }: { factor: Factor; index: number }) {
  const isPositive = factor.change > 0
  const isNegative = factor.change < 0

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.05, duration: 0.3 }}
    >
      <Card className="hover:shadow-md transition-shadow">
        <CardContent className="p-4">
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <h4 className="font-medium">{factor.name}</h4>
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
                  {factor.status}
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground line-clamp-2">
                {factor.description}
              </p>
            </div>
            <div className="text-right ml-4">
              <p className="text-lg font-bold font-mono">
                {formatNumber(factor.value)}
              </p>
              <div className="flex items-center justify-end gap-1">
                {isPositive && <ArrowUp className="h-3 w-3 text-score-green" />}
                {isNegative && <ArrowDown className="h-3 w-3 text-score-red" />}
                {factor.change === 0 && <Minus className="h-3 w-3 text-muted-foreground" />}
                <span
                  className={cn(
                    'text-xs',
                    isPositive && 'text-score-green',
                    isNegative && 'text-score-red',
                    factor.change === 0 && 'text-muted-foreground'
                  )}
                >
                  {isPositive ? '+' : ''}
                  {formatNumber(factor.changePercent, 1)}%
                </span>
              </div>
            </div>
          </div>

          {/* Mini chart placeholder */}
          <div className="mt-3 h-8 flex items-end gap-0.5">
            {factor.historicalData.slice(-20).map((point, i) => {
              const max = Math.max(...factor.historicalData.map(h => h.value))
              const min = Math.min(...factor.historicalData.map(h => h.value))
              const range = max - min || 1
              const height = ((point.value - min) / range) * 100
              
              return (
                <div
                  key={i}
                  className={cn(
                    'flex-1 rounded-sm transition-all',
                    factor.status === 'positive' && 'bg-score-green/60',
                    factor.status === 'negative' && 'bg-score-red/60',
                    factor.status === 'neutral' && 'bg-muted-foreground/40'
                  )}
                  style={{ height: `${Math.max(10, height)}%` }}
                />
              )
            })}
          </div>
        </CardContent>
      </Card>
    </motion.div>
  )
}

export function FactorList({ factors, className }: FactorListProps) {
  return (
    <div className={cn('space-y-3', className)}>
      {factors.map((factor, index) => (
        <FactorCard key={factor.id} factor={factor} index={index} />
      ))}
    </div>
  )
}
