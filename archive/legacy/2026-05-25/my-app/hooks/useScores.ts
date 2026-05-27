'use client'

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo } from 'react'
import { useAllIndicators } from './useFREDData'
import { 
  calculateOverallScore, 
  calculateModuleScore,
  calculateScoreBreakdown,
  calculateScoreTrend,
  getScoreInterpretation,
  getTrendDescription
} from '@/lib/scoring'
import { OverallScore, ScoreBreakdown, Module, ModuleId } from '@/types/modules'
import { INDICATOR_CONFIGS } from '@/lib/fred-api'

// Module configurations
const MODULE_CONFIGS: Record<ModuleId, { name: string; indicators: string[]; weights: Record<string, number> }> = {
  'labor-market': {
    name: 'Labor Market',
    indicators: ['UNRATE', 'PAYEMS'],
    weights: { UNRATE: 0.6, PAYEMS: 0.4 },
  },
  'inflation': {
    name: 'Inflation',
    indicators: ['CPIAUCSL'],
    weights: { CPIAUCSL: 1.0 },
  },
  'gdp-growth': {
    name: 'GDP Growth',
    indicators: ['GDP'],
    weights: { GDP: 1.0 },
  },
  'interest-rates': {
    name: 'Interest Rates',
    indicators: ['FEDFUNDS'],
    weights: { FEDFUNDS: 1.0 },
  },
  'housing-market': {
    name: 'Housing Market',
    indicators: ['HOUST'],
    weights: { HOUST: 1.0 },
  },
  'consumer-sentiment': {
    name: 'Consumer Sentiment',
    indicators: ['UMCSENT'],
    weights: { UMCSENT: 1.0 },
  },
  'manufacturing': {
    name: 'Manufacturing',
    indicators: ['INDPRO'],
    weights: { INDPRO: 1.0 },
  },
  'international-trade': {
    name: 'International Trade',
    indicators: ['GDP'],
    weights: { GDP: 1.0 },
  },
}

// Query keys
const scoreKeys = {
  all: ['scores'] as const,
  overall: () => [...scoreKeys.all, 'overall'] as const,
  modules: () => [...scoreKeys.all, 'modules'] as const,
  module: (id: ModuleId) => [...scoreKeys.all, 'module', id] as const,
  breakdown: () => [...scoreKeys.all, 'breakdown'] as const,
}

// Hook for calculating modules from indicators
export function useModules() {
  const { data: indicators, isLoading, error } = useAllIndicators()

  const modules = useMemo(() => {
    if (!indicators) return []

    const indicatorMap = new Map(indicators.map(i => [i.seriesId, i]))

    return (Object.keys(MODULE_CONFIGS) as ModuleId[]).map(moduleId => {
      const config = MODULE_CONFIGS[moduleId]
      const moduleIndicators = config.indicators
        .map(id => indicatorMap.get(id))
        .filter((i): i is NonNullable<typeof i> => i !== undefined)

      return calculateModuleScore(moduleId, config.name, moduleIndicators, config.weights)
    })
  }, [indicators])

  return { modules, isLoading, error }
}

// Hook for overall score
export function useOverallScore() {
  const { modules, isLoading, error } = useModules()

  const overallScore = useMemo(() => {
    if (modules.length === 0) return null
    return calculateOverallScore(modules)
  }, [modules])

  const interpretation = useMemo(() => {
    if (!overallScore) return ''
    return getScoreInterpretation(overallScore.current)
  }, [overallScore])

  const trend = useMemo(() => {
    if (!overallScore) return null
    return calculateScoreTrend(overallScore.history)
  }, [overallScore])

  const trendDescription = useMemo(() => {
    if (!trend) return ''
    return getTrendDescription(trend)
  }, [trend])

  return {
    overallScore,
    interpretation,
    trend,
    trendDescription,
    isLoading,
    error,
  }
}

// Hook for score breakdown
export function useScoreBreakdown() {
  const { modules, isLoading, error } = useModules()

  const breakdown = useMemo(() => {
    if (modules.length === 0) return null
    return calculateScoreBreakdown(modules)
  }, [modules])

  return { breakdown, isLoading, error }
}

// Hook for a specific module
export function useModule(moduleId: ModuleId) {
  const { modules, isLoading, error } = useModules()

  const module = useMemo(() => {
    return modules.find(m => m.id === moduleId) || null
  }, [modules, moduleId])

  return { module, isLoading, error }
}

// Hook for module comparison
export function useModuleComparison() {
  const { modules, isLoading, error } = useModules()

  const sortedModules = useMemo(() => {
    return [...modules].sort((a, b) => b.score - a.score)
  }, [modules])

  const rankings = useMemo(() => {
    return modules.map((m, index) => ({
      moduleId: m.id,
      rank: index + 1,
      score: m.score,
      percentile: (m.score / 100) * 100,
    }))
  }, [modules])

  return {
    modules,
    sortedModules,
    rankings,
    isLoading,
    error,
  }
}

// Hook for score history
export function useScoreHistory(days: number = 30) {
  const { overallScore, isLoading, error } = useOverallScore()

  const history = useMemo(() => {
    if (!overallScore) return []
    
    // Filter history to requested time range
    const cutoffDate = new Date()
    cutoffDate.setDate(cutoffDate.getDate() - days)
    
    return overallScore.history.filter(h => h.date >= cutoffDate)
  }, [overallScore, days])

  return { history, isLoading, error }
}

// Hook for refreshing scores
export function useRefreshScores() {
  const queryClient = useQueryClient()

  const refreshScores = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: scoreKeys.all })
    queryClient.invalidateQueries({ queryKey: ['fred'] })
  }, [queryClient])

  const refreshModule = useCallback(
    (moduleId: ModuleId) => {
      queryClient.invalidateQueries({ queryKey: scoreKeys.module(moduleId) })
    },
    [queryClient]
  )

  return { refreshScores, refreshModule }
}

// Hook for score alerts
export function useScoreAlerts() {
  const { overallScore, modules, isLoading } = useOverallScore()
  const { modules: allModules } = useModules()

  const alerts = useMemo(() => {
    const alertList: Array<{
      id: string
      type: 'score_change' | 'threshold_crossed' | 'trend_reversal'
      severity: 'info' | 'warning' | 'critical'
      message: string
      moduleId?: ModuleId
    }> = []

    if (!overallScore) return alertList

    // Check for significant score changes
    if (Math.abs(overallScore.change) > 5) {
      alertList.push({
        id: 'overall-change',
        type: 'score_change',
        severity: Math.abs(overallScore.change) > 10 ? 'critical' : 'warning',
        message: `Overall score ${overallScore.change > 0 ? 'increased' : 'decreased'} by ${Math.abs(overallScore.change)} points`,
      })
    }

    // Check for threshold crossings
    if (overallScore.status === 'critical' && overallScore.previous >= 40) {
      alertList.push({
        id: 'critical-threshold',
        type: 'threshold_crossed',
        severity: 'critical',
        message: 'Overall score has entered critical range',
      })
    }

    // Check module-specific alerts
    allModules.forEach(module => {
      if (Math.abs(module.score - module.previousScore) > 10) {
        alertList.push({
          id: `module-${module.id}-change`,
          type: 'score_change',
          severity: 'warning',
          message: `${module.name} score changed significantly`,
          moduleId: module.id,
        })
      }
    })

    return alertList
  }, [overallScore, allModules])

  return { alerts, isLoading }
}
