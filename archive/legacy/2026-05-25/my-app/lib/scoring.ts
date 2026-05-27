import { EconomicIndicator } from '@/types/fred'
import { 
  OverallScore, 
  ScoreHistoryPoint, 
  ScoreBreakdown, 
  ModuleScore, 
  PercentileData,
  ScoreTrend,
  DEFAULT_SCORE_THRESHOLDS 
} from '@/types/scores'
import { Module, Factor, ModuleId } from '@/types/modules'
import { INDICATOR_CONFIGS } from './fred-api'

// Calculate percentile of a value within a dataset
export function calculatePercentile(value: number, dataset: number[]): number {
  if (dataset.length === 0) return 50
  
  const sorted = [...dataset].sort((a, b) => a - b)
  const position = sorted.findIndex(v => v >= value)
  
  if (position === -1) return 100
  return (position / sorted.length) * 100
}

// Normalize a value to a 0-100 scale
export function normalizeToScore(
  value: number,
  minValue: number,
  maxValue: number,
  inverted: boolean = false
): number {
  let normalized = ((value - minValue) / (maxValue - minValue)) * 100
  normalized = Math.max(0, Math.min(100, normalized))
  
  if (inverted) {
    normalized = 100 - normalized
  }
  
  return normalized
}

// Calculate score from indicator using percentile method
export function calculateIndicatorScore(
  indicator: EconomicIndicator,
  lookbackYears: number = 10
): { score: number; percentile: number } {
  const historicalValues = indicator.historicalData
    .filter(d => {
      const yearsAgo = (new Date().getTime() - d.date.getTime()) / (1000 * 60 * 60 * 24 * 365)
      return yearsAgo <= lookbackYears
    })
    .map(d => d.value)
  
  const percentile = calculatePercentile(indicator.lastValue, historicalValues)
  
  // Get config to check if inverted
  const config = INDICATOR_CONFIGS[indicator.seriesId]
  const inverted = config?.inverted || false
  
  // Convert percentile to score (0-100)
  let score = percentile
  if (inverted) {
    score = 100 - percentile
  }
  
  return { score, percentile }
}

// Calculate factor score and contribution
export function calculateFactorScore(
  indicator: EconomicIndicator,
  weight: number
): Factor {
  const { score, percentile } = calculateIndicatorScore(indicator)
  
  const historicalValues = indicator.historicalData
  const currentValue = indicator.lastValue
  const previousValue = indicator.previousValue
  const change = currentValue - previousValue
  const changePercent = previousValue !== 0 ? (change / previousValue) * 100 : 0
  
  // Determine status based on percentile
  let status: 'positive' | 'neutral' | 'negative' = 'neutral'
  if (percentile >= 70) status = 'positive'
  else if (percentile <= 30) status = 'negative'
  
  const config = INDICATOR_CONFIGS[indicator.seriesId]
  
  return {
    id: indicator.seriesId,
    name: indicator.name,
    description: indicator.description,
    seriesId: indicator.seriesId,
    weight,
    value: currentValue,
    previousValue,
    change,
    changePercent,
    contribution: score * weight,
    status,
    direction: config?.inverted ? 'lower_is_better' : 'higher_is_better',
    historicalData: indicator.historicalData.map(d => ({
      date: d.date,
      value: d.value,
      percentile: calculatePercentile(d.value, historicalValues.map(h => h.value)),
    })),
    lastUpdated: indicator.lastUpdated,
  }
}

// Calculate module score from its factors
export function calculateModuleScore(
  moduleId: ModuleId,
  moduleName: string,
  indicators: EconomicIndicator[],
  weights: Record<string, number>
): Module {
  const factors = indicators.map(indicator => 
    calculateFactorScore(indicator, weights[indicator.seriesId] || 0.1)
  )
  
  // Calculate weighted average score
  const totalWeight = factors.reduce((sum, f) => sum + f.weight, 0)
  const score = factors.reduce((sum, f) => sum + (f.contribution / totalWeight), 0)
  
  // Determine trend
  const previousScore = factors.reduce((sum, f) => {
    const prevPercentile = calculatePercentile(f.previousValue, 
      f.historicalData.map(h => h.value)
    )
    return sum + (prevPercentile * f.weight / totalWeight)
  }, 0)
  
  let trend: 'up' | 'down' | 'stable' = 'stable'
  if (score > previousScore + 2) trend = 'up'
  else if (score < previousScore - 2) trend = 'down'
  
  // Determine status
  let status: 'healthy' | 'warning' | 'critical' = 'warning'
  if (score >= 70) status = 'healthy'
  else if (score < 40) status = 'critical'
  
  // Module colors
  const moduleColors: Record<ModuleId, string> = {
    'labor-market': '#3b82f6',
    'inflation': '#f59e0b',
    'gdp-growth': '#10b981',
    'interest-rates': '#8b5cf6',
    'housing-market': '#ec4899',
    'consumer-sentiment': '#06b6d4',
    'manufacturing': '#f97316',
    'international-trade': '#84cc16',
  }
  
  return {
    id: moduleId,
    name: moduleName,
    shortName: moduleName.split(' ')[0],
    description: `Economic indicators for ${moduleName.toLowerCase()}`,
    icon: getModuleIcon(moduleId),
    color: moduleColors[moduleId] || '#6b7280',
    score: Math.round(score),
    previousScore: Math.round(previousScore),
    trend,
    weight: 1,
    factors,
    lastUpdated: new Date(),
    status,
  }
}

// Get module icon name
function getModuleIcon(moduleId: ModuleId): string {
  const icons: Record<ModuleId, string> = {
    'labor-market': 'Users',
    'inflation': 'TrendingUp',
    'gdp-growth': 'BarChart3',
    'interest-rates': 'Percent',
    'housing-market': 'Home',
    'consumer-sentiment': 'Smile',
    'manufacturing': 'Factory',
    'international-trade': 'Globe',
  }
  return icons[moduleId] || 'Activity'
}

// Calculate overall score from modules
export function calculateOverallScore(modules: Module[]): OverallScore {
  const totalWeight = modules.reduce((sum, m) => sum + m.weight, 0)
  const score = modules.reduce((sum, m) => sum + (m.score * m.weight / totalWeight), 0)
  
  const previousScore = modules.reduce((sum, m) => 
    sum + (m.previousScore * m.weight / totalWeight), 0
  )
  
  const change = score - previousScore
  const changePercent = previousScore !== 0 ? (change / previousScore) * 100 : 0
  
  let trend: 'improving' | 'declining' | 'stable' = 'stable'
  if (change > 2) trend = 'improving'
  else if (change < -2) trend = 'declining'
  
  let status: 'healthy' | 'warning' | 'critical' = 'warning'
  if (score >= 70) status = 'healthy'
  else if (score < 40) status = 'critical'
  
  // Generate mock history
  const history: ScoreHistoryPoint[] = []
  for (let i = 12; i >= 0; i--) {
    const date = new Date()
    date.setMonth(date.getMonth() - i)
    const variation = (Math.random() - 0.5) * 10
    const historicalScore = Math.max(0, Math.min(100, score + variation))
    let historicalStatus: 'healthy' | 'warning' | 'critical' = 'warning'
    if (historicalScore >= 70) historicalStatus = 'healthy'
    else if (historicalScore < 40) historicalStatus = 'critical'
    
    history.push({
      date,
      score: Math.round(historicalScore),
      status: historicalStatus,
    })
  }
  
  return {
    current: Math.round(score),
    previous: Math.round(previousScore),
    change: Math.round(change * 10) / 10,
    changePercent: Math.round(changePercent * 10) / 10,
    trend,
    status,
    lastUpdated: new Date(),
    history,
  }
}

// Calculate score breakdown
export function calculateScoreBreakdown(modules: Module[]): ScoreBreakdown {
  const overall = calculateOverallScore(modules)
  
  const moduleScores: ModuleScore[] = modules.map(m => ({
    moduleId: m.id,
    moduleName: m.name,
    score: m.score,
    weight: m.weight,
    weightedContribution: m.score * m.weight,
    status: m.status,
  }))
  
  return {
    overall: overall.current,
    modules: moduleScores,
    timestamp: new Date(),
  }
}

// Calculate score trend
export function calculateScoreTrend(history: ScoreHistoryPoint[]): ScoreTrend {
  if (history.length < 2) {
    return { direction: 'flat', strength: 'weak', duration: 0, changeOverPeriod: 0 }
  }
  
  const recent = history.slice(-6)
  const first = recent[0].score
  const last = recent[recent.length - 1].score
  const change = last - first
  
  let direction: 'up' | 'down' | 'flat' = 'flat'
  if (change > 3) direction = 'up'
  else if (change < -3) direction = 'down'
  
  let strength: 'strong' | 'moderate' | 'weak' = 'weak'
  const absChange = Math.abs(change)
  if (absChange > 10) strength = 'strong'
  else if (absChange > 5) strength = 'moderate'
  
  return {
    direction,
    strength,
    duration: recent.length,
    changeOverPeriod: change,
  }
}

// Get score interpretation
export function getScoreInterpretation(score: number): string {
  if (score >= 90) return 'Excellent economic conditions'
  if (score >= 80) return 'Very good economic conditions'
  if (score >= 70) return 'Good economic conditions'
  if (score >= 60) return 'Moderate economic conditions'
  if (score >= 50) return 'Fair economic conditions'
  if (score >= 40) return 'Weak economic conditions'
  if (score >= 30) return 'Poor economic conditions'
  if (score >= 20) return 'Very poor economic conditions'
  return 'Critical economic conditions'
}

// Get trend description
export function getTrendDescription(trend: ScoreTrend): string {
  const directionText = {
    up: 'improving',
    down: 'declining',
    flat: 'stable',
  }[trend.direction]
  
  const strengthText = {
    strong: 'strongly',
    moderate: 'moderately',
    weak: 'slightly',
  }[trend.strength]
  
  return `The economy is ${strengthText} ${directionText}`
}
