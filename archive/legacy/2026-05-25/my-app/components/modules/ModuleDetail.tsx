'use client'

import React from 'react'
import Link from 'next/link'
import { motion } from 'framer-motion'
import { ArrowLeft, TrendingUp, TrendingDown, Minus, Info } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Module } from '@/types/modules'
import { cn, getScoreColor, getScoreStatus } from '@/lib/utils'
import { ScoreGauge } from '@/components/dashboard/ScoreGauge'
import { TrendChart } from '@/components/dashboard/TrendChart'
import { FactorTable } from '@/components/dashboard/FactorTable'

interface ModuleDetailProps {
  module: Module
}

export function ModuleDetail({ module }: ModuleDetailProps) {
  const scoreColor = getScoreColor(module.score)
  const scoreStatus = getScoreStatus(module.score)

  // Generate mock history data
  const historyData = Array.from({ length: 12 }, (_, i) => {
    const date = new Date()
    date.setMonth(date.getMonth() - (11 - i))
    const variation = (Math.random() - 0.5) * 15
    const score = Math.max(0, Math.min(100, module.score + variation))
    return {
      date,
      score: Math.round(score),
      status: score >= 70 ? 'healthy' : score >= 40 ? 'warning' : 'critical' as const,
    }
  })

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link href="/dashboard/">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="h-5 w-5" />
          </Button>
        </Link>
        <div>
          <h1 className="text-2xl font-bold">{module.name}</h1>
          <p className="text-muted-foreground">{module.description}</p>
        </div>
      </div>

      {/* Score Overview */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-1">
          <CardContent className="p-6 flex flex-col items-center">
            <ScoreGauge score={module.score} size="md" />
            <div className="mt-4 text-center">
              <p className="text-sm text-muted-foreground">Previous: {module.previousScore}</p>
              <div className="flex items-center justify-center gap-2 mt-1">
                {module.trend === 'up' && <TrendingUp className="h-4 w-4 text-score-green" />}
                {module.trend === 'down' && <TrendingDown className="h-4 w-4 text-score-red" />}
                {module.trend === 'stable' && <Minus className="h-4 w-4 text-muted-foreground" />}
                <span
                  className={cn(
                    'text-sm font-medium',
                    module.trend === 'up' && 'text-score-green',
                    module.trend === 'down' && 'text-score-red',
                    module.trend === 'stable' && 'text-muted-foreground'
                  )}
                >
                  {module.score > module.previousScore ? '+' : ''}
                  {module.score - module.previousScore} from last period
                </span>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-lg">12-Month Trend</CardTitle>
          </CardHeader>
          <CardContent>
            <TrendChart data={historyData} showArea height={200} />
          </CardContent>
        </Card>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {module.factors.slice(0, 4).map((factor, index) => (
          <motion.div
            key={factor.id}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.1 }}
          >
            <Card>
              <CardContent className="p-4">
                <div className="flex items-center gap-2 mb-2">
                  <p className="text-sm text-muted-foreground">{factor.name}</p>
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger>
                        <Info className="h-3 w-3 text-muted-foreground" />
                      </TooltipTrigger>
                      <TooltipContent>
                        <p className="max-w-xs">{factor.description}</p>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </div>
                <p className="text-2xl font-bold">{factor.value.toFixed(2)}</p>
                <div className="flex items-center gap-1 mt-1">
                  {factor.change > 0 ? (
                    <TrendingUp className="h-3 w-3 text-score-green" />
                  ) : factor.change < 0 ? (
                    <TrendingDown className="h-3 w-3 text-score-red" />
                  ) : (
                    <Minus className="h-3 w-3 text-muted-foreground" />
                  )}
                  <span
                    className={cn(
                      'text-xs',
                      factor.change > 0 && 'text-score-green',
                      factor.change < 0 && 'text-score-red',
                      factor.change === 0 && 'text-muted-foreground'
                    )}
                  >
                    {factor.change > 0 ? '+' : ''}
                    {factor.changePercent.toFixed(1)}%
                  </span>
                </div>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>

      {/* Factors Table */}
      <FactorTable factors={module.factors} title="All Factors" />

      {/* Interpretation */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">How to Interpret This Score</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 rounded-lg bg-score-green/10 border border-score-green/20">
              <div className="flex items-center gap-2 mb-2">
                <div className="h-3 w-3 rounded-full bg-score-green" />
                <p className="font-medium text-score-green">Healthy (70-100)</p>
              </div>
              <p className="text-sm text-muted-foreground">
                Economic conditions are favorable. The indicator is performing better than 70% of historical observations.
              </p>
            </div>
            <div className="p-4 rounded-lg bg-score-yellow/10 border border-score-yellow/20">
              <div className="flex items-center gap-2 mb-2">
                <div className="h-3 w-3 rounded-full bg-score-yellow" />
                <p className="font-medium text-score-yellow">Warning (40-69)</p>
              </div>
              <p className="text-sm text-muted-foreground">
                Economic conditions are moderate. The indicator is performing around average compared to historical data.
              </p>
            </div>
            <div className="p-4 rounded-lg bg-score-red/10 border border-score-red/20">
              <div className="flex items-center gap-2 mb-2">
                <div className="h-3 w-3 rounded-full bg-score-red" />
                <p className="font-medium text-score-red">Critical (0-39)</p>
              </div>
              <p className="text-sm text-muted-foreground">
                Economic conditions are concerning. The indicator is performing worse than 60% of historical observations.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
