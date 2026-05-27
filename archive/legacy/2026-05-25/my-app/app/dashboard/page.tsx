'use client'

import React, { useState } from 'react'
import Link from 'next/link'
import { motion } from 'framer-motion'
import { 
  Download, 
  RefreshCw, 
  Calendar, 
  TrendingUp, 
  TrendingDown, 
  ArrowRight 
} from 'lucide-react'
import { MainLayout } from '@/components/layout/MainLayout'
import { Sidebar } from '@/components/layout/Sidebar'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { ScoreGauge } from '@/components/dashboard/ScoreGauge'
import { ModuleGrid } from '@/components/dashboard/ModuleGrid'
import { TrendChart } from '@/components/dashboard/TrendChart'
import { useOverallScore, useModules, useScoreBreakdown } from '@/hooks/useScores'
import { useRefreshScores } from '@/hooks/useScores'
import { cn, formatDate } from '@/lib/utils'

export default function DashboardPage() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const { overallScore, interpretation, trendDescription, isLoading: scoreLoading } = useOverallScore()
  const { modules, isLoading: modulesLoading } = useModules()
  const { refreshScores } = useRefreshScores()

  const isLoading = scoreLoading || modulesLoading

  return (
    <MainLayout showFooter={false}>
      <div className="flex min-h-[calc(100vh-4rem)]">
        <Sidebar 
          isCollapsed={sidebarCollapsed} 
          onToggle={() => setSidebarCollapsed(!sidebarCollapsed)} 
        />
        
        <main 
          className={cn(
            'flex-1 transition-all duration-300 p-6',
            sidebarCollapsed ? 'ml-16' : 'ml-64'
          )}
        >
          <div className="max-w-7xl mx-auto space-y-6">
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div>
                <h1 className="text-2xl font-bold">Economic Dashboard</h1>
                <p className="text-sm text-muted-foreground">
                  Last updated: {formatDate(new Date(), 'medium')}
                </p>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => refreshScores()}
                  disabled={isLoading}
                >
                  <RefreshCw className={cn('h-4 w-4 mr-2', isLoading && 'animate-spin')} />
                  Refresh
                </Button>
                <Button variant="outline" size="sm">
                  <Download className="h-4 w-4 mr-2" />
                  Export
                </Button>
              </div>
            </div>

            {/* Overall Score Section */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Score Gauge */}
              <Card className="lg:col-span-1">
                <CardContent className="p-6">
                  <div className="flex flex-col items-center">
                    {isLoading ? (
                      <div className="h-48 w-48 rounded-full bg-muted animate-pulse" />
                    ) : (
                      <ScoreGauge 
                        score={overallScore?.current || 50} 
                        size="md" 
                        animated 
                      />
                    )}
                    <div className="mt-4 text-center">
                      {isLoading ? (
                        <div className="h-4 w-32 bg-muted animate-pulse rounded mx-auto" />
                      ) : (
                        <>
                          <p className="text-sm text-muted-foreground">{interpretation}</p>
                          <p className="text-sm font-medium mt-1">{trendDescription}</p>
                        </>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Key Metrics */}
              <div className="lg:col-span-2 grid grid-cols-2 gap-4">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-muted-foreground">
                      Overall Score
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {isLoading ? (
                      <div className="h-8 w-16 bg-muted animate-pulse rounded" />
                    ) : (
                      <div className="flex items-baseline gap-2">
                        <span className="text-3xl font-bold">
                          {overallScore?.current || 0}
                        </span>
                        <Badge
                          variant={
                            (overallScore?.change || 0) > 0
                              ? 'success'
                              : (overallScore?.change || 0) < 0
                              ? 'critical'
                              : 'secondary'
                          }
                        >
                          {(overallScore?.change || 0) > 0 ? '+' : ''}
                          {overallScore?.change || 0}
                        </Badge>
                      </div>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-muted-foreground">
                      Trend
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {isLoading ? (
                      <div className="h-8 w-24 bg-muted animate-pulse rounded" />
                    ) : (
                      <div className="flex items-center gap-2">
                        {overallScore?.trend === 'improving' && (
                          <>
                            <TrendingUp className="h-5 w-5 text-score-green" />
                            <span className="text-lg font-medium text-score-green">
                              Improving
                            </span>
                          </>
                        )}
                        {overallScore?.trend === 'declining' && (
                          <>
                            <TrendingDown className="h-5 w-5 text-score-red" />
                            <span className="text-lg font-medium text-score-red">
                              Declining
                            </span>
                          </>
                        )}
                        {overallScore?.trend === 'stable' && (
                          <span className="text-lg font-medium">Stable</span>
                        )}
                      </div>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-muted-foreground">
                      Healthy Modules
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {isLoading ? (
                      <div className="h-8 w-16 bg-muted animate-pulse rounded" />
                    ) : (
                      <div className="flex items-baseline gap-2">
                        <span className="text-3xl font-bold">
                          {modules.filter(m => m.status === 'healthy').length}
                        </span>
                        <span className="text-sm text-muted-foreground">
                          of {modules.length}
                        </span>
                      </div>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium text-muted-foreground">
                      Critical Modules
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    {isLoading ? (
                      <div className="h-8 w-16 bg-muted animate-pulse rounded" />
                    ) : (
                      <div className="flex items-baseline gap-2">
                        <span className="text-3xl font-bold">
                          {modules.filter(m => m.status === 'critical').length}
                        </span>
                        <span className="text-sm text-muted-foreground">
                          of {modules.length}
                        </span>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </div>
            </div>

            {/* Trend Chart */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg">Score History</CardTitle>
              </CardHeader>
              <CardContent>
                {isLoading ? (
                  <div className="h-64 bg-muted animate-pulse rounded" />
                ) : (
                  <TrendChart 
                    data={overallScore?.history || []} 
                    showArea 
                    height={250} 
                  />
                )}
              </CardContent>
            </Card>

            {/* Modules Grid */}
            <div>
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold">Economic Modules</h2>
                <Link href="/dashboard/">
                  <Button variant="ghost" size="sm">
                    View All
                    <ArrowRight className="h-4 w-4 ml-1" />
                  </Button>
                </Link>
              </div>
              <ModuleGrid modules={modules} isLoading={isLoading} />
            </div>
          </div>
        </main>
      </div>
    </MainLayout>
  )
}
