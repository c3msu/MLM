'use client'

import React from 'react'
import Link from 'next/link'
import { motion } from 'framer-motion'
import { ArrowUp, ArrowDown, Minus, TrendingUp, TrendingDown, Activity } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Module } from '@/types/modules'
import { cn, getScoreColor, getScoreStatus } from '@/lib/utils'

interface ModuleGridProps {
  modules: Module[]
  isLoading?: boolean
}

const iconMap: Record<string, React.ElementType> = {
  Users: Activity,
  TrendingUp: TrendingUp,
  TrendingDown: TrendingDown,
  Percent: Activity,
  Home: Activity,
  Smile: Activity,
  Factory: Activity,
  Globe: Activity,
  Activity: Activity,
}

function ModuleCard({ module, index }: { module: Module; index: number }) {
  const scoreColor = getScoreColor(module.score)
  const scoreStatus = getScoreStatus(module.score)
  const Icon = iconMap[module.icon] || Activity

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1, duration: 0.5 }}
    >
      <Link href={`/module/${module.id}/`}>
        <Card className="h-full cursor-pointer transition-all hover:shadow-lg hover:scale-[1.02]">
          <CardHeader className="pb-2">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2">
                <div
                  className="flex h-8 w-8 items-center justify-center rounded-lg"
                  style={{ backgroundColor: `${module.color}20` }}
                >
                  <Icon className="h-4 w-4" style={{ color: module.color }} />
                </div>
                <CardTitle className="text-base">{module.name}</CardTitle>
              </div>
              <Badge
                variant={
                  scoreStatus === 'healthy'
                    ? 'success'
                    : scoreStatus === 'warning'
                    ? 'warning'
                    : 'critical'
                }
              >
                {module.score}
              </Badge>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground line-clamp-2 mb-3">
              {module.description}
            </p>

            {/* Score bar */}
            <div className="space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">Score</span>
                <div className="flex items-center gap-1">
                  {module.trend === 'up' && (
                    <ArrowUp className="h-3 w-3 text-score-green" />
                  )}
                  {module.trend === 'down' && (
                    <ArrowDown className="h-3 w-3 text-score-red" />
                  )}
                  {module.trend === 'stable' && (
                    <Minus className="h-3 w-3 text-muted-foreground" />
                  )}
                  <span
                    className={cn(
                      module.trend === 'up' && 'text-score-green',
                      module.trend === 'down' && 'text-score-red',
                      module.trend === 'stable' && 'text-muted-foreground'
                    )}
                  >
                    {module.score > module.previousScore ? '+' : ''}
                    {module.score - module.previousScore}
                  </span>
                </div>
              </div>

              {/* Progress bar */}
              <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                <motion.div
                  className={cn(
                    'h-full rounded-full transition-all duration-1000',
                    scoreStatus === 'healthy' && 'bg-score-green',
                    scoreStatus === 'warning' && 'bg-score-yellow',
                    scoreStatus === 'critical' && 'bg-score-red'
                  )}
                  initial={{ width: 0 }}
                  animate={{ width: `${module.score}%` }}
                  transition={{ duration: 1, delay: index * 0.1 + 0.3 }}
                />
              </div>

              {/* Factor count */}
              <p className="text-xs text-muted-foreground">
                {module.factors.length} factors analyzed
              </p>
            </div>
          </CardContent>
        </Card>
      </Link>
    </motion.div>
  )
}

export function ModuleGrid({ modules, isLoading = false }: ModuleGridProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <Card key={i} className="h-full">
            <CardHeader className="pb-2">
              <div className="flex items-center gap-2">
                <div className="h-8 w-8 rounded-lg bg-muted animate-pulse" />
                <div className="h-5 w-24 bg-muted animate-pulse rounded" />
              </div>
            </CardHeader>
            <CardContent>
              <div className="h-4 w-full bg-muted animate-pulse rounded mb-3" />
              <div className="h-4 w-3/4 bg-muted animate-pulse rounded mb-4" />
              <div className="h-2 w-full bg-muted animate-pulse rounded-full" />
            </CardContent>
          </Card>
        ))}
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {modules.map((module, index) => (
        <ModuleCard key={module.id} module={module} index={index} />
      ))}
    </div>
  )
}
