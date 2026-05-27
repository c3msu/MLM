'use client'

import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback } from 'react'
import { 
  getEconomicIndicator, 
  getMultipleIndicators, 
  getAllIndicators,
  fetchSeriesObservations 
} from '@/lib/fred-api'
import { EconomicIndicator, FRADOBServation } from '@/types/fred'

// Query keys
const fredKeys = {
  all: ['fred'] as const,
  indicator: (seriesId: string) => [...fredKeys.all, 'indicator', seriesId] as const,
  indicators: (seriesIds: string[]) => [...fredKeys.all, 'indicators', seriesIds] as const,
  allIndicators: () => [...fredKeys.all, 'all-indicators'] as const,
  observations: (seriesId: string) => [...fredKeys.all, 'observations', seriesId] as const,
}

// Hook for a single indicator
export function useIndicator(seriesId: string, yearsOfHistory: number = 5) {
  return useQuery({
    queryKey: fredKeys.indicator(seriesId),
    queryFn: () => getEconomicIndicator(seriesId, yearsOfHistory),
    staleTime: 1000 * 60 * 15, // 15 minutes
    refetchInterval: 1000 * 60 * 30, // 30 minutes
  })
}

// Hook for multiple indicators
export function useIndicators(seriesIds: string[]) {
  return useQuery({
    queryKey: fredKeys.indicators(seriesIds),
    queryFn: () => getMultipleIndicators(seriesIds),
    staleTime: 1000 * 60 * 15,
    refetchInterval: 1000 * 60 * 30,
    enabled: seriesIds.length > 0,
  })
}

// Hook for all configured indicators
export function useAllIndicators() {
  return useQuery({
    queryKey: fredKeys.allIndicators(),
    queryFn: getAllIndicators,
    staleTime: 1000 * 60 * 15,
    refetchInterval: 1000 * 60 * 30,
  })
}

// Hook for series observations
export function useSeriesObservations(
  seriesId: string,
  startDate?: string,
  endDate?: string
) {
  return useQuery({
    queryKey: [...fredKeys.observations(seriesId), startDate, endDate],
    queryFn: () => fetchSeriesObservations(seriesId, startDate, endDate),
    staleTime: 1000 * 60 * 15,
    enabled: !!seriesId,
  })
}

// Hook for prefetching indicators
export function usePrefetchIndicators() {
  const queryClient = useQueryClient()

  const prefetchIndicator = useCallback(
    (seriesId: string) => {
      queryClient.prefetchQuery({
        queryKey: fredKeys.indicator(seriesId),
        queryFn: () => getEconomicIndicator(seriesId),
        staleTime: 1000 * 60 * 15,
      })
    },
    [queryClient]
  )

  const prefetchIndicators = useCallback(
    (seriesIds: string[]) => {
      queryClient.prefetchQuery({
        queryKey: fredKeys.indicators(seriesIds),
        queryFn: () => getMultipleIndicators(seriesIds),
        staleTime: 1000 * 60 * 15,
      })
    },
    [queryClient]
  )

  return { prefetchIndicator, prefetchIndicators }
}

// Hook for refreshing indicators
export function useRefreshIndicators() {
  const queryClient = useQueryClient()

  const refreshIndicator = useCallback(
    (seriesId: string) => {
      queryClient.invalidateQueries({
        queryKey: fredKeys.indicator(seriesId),
      })
    },
    [queryClient]
  )

  const refreshAllIndicators = useCallback(() => {
    queryClient.invalidateQueries({
      queryKey: fredKeys.all,
    })
  }, [queryClient])

  return { refreshIndicator, refreshAllIndicators }
}

// Hook for indicator comparison
export function useIndicatorComparison(
  seriesId: string,
  compareSeriesId: string
) {
  const { data: indicator1, isLoading: isLoading1 } = useIndicator(seriesId)
  const { data: indicator2, isLoading: isLoading2 } = useIndicator(compareSeriesId)

  const comparison = {
    indicator1,
    indicator2,
    isLoading: isLoading1 || isLoading2,
    correlation: calculateCorrelation(
      indicator1?.historicalData.map(d => d.value) || [],
      indicator2?.historicalData.map(d => d.value) || []
    ),
  }

  return comparison
}

// Calculate correlation between two datasets
function calculateCorrelation(x: number[], y: number[]): number {
  if (x.length !== y.length || x.length === 0) return 0

  const n = x.length
  const sumX = x.reduce((a, b) => a + b, 0)
  const sumY = y.reduce((a, b) => a + b, 0)
  const sumXY = x.reduce((sum, xi, i) => sum + xi * y[i], 0)
  const sumX2 = x.reduce((sum, xi) => sum + xi * xi, 0)
  const sumY2 = y.reduce((sum, yi) => sum + yi * yi, 0)

  const numerator = n * sumXY - sumX * sumY
  const denominator = Math.sqrt((n * sumX2 - sumX * sumX) * (n * sumY2 - sumY * sumY))

  return denominator === 0 ? 0 : numerator / denominator
}
