// Scoring Types for The Dial

export interface OverallScore {
  current: number
  previous: number
  change: number
  changePercent: number
  trend: 'improving' | 'declining' | 'stable'
  status: 'healthy' | 'warning' | 'critical'
  lastUpdated: Date
  history: ScoreHistoryPoint[]
}

export interface ScoreHistoryPoint {
  date: Date
  score: number
  status: 'healthy' | 'warning' | 'critical'
}

export interface ScoreBreakdown {
  overall: number
  modules: ModuleScore[]
  timestamp: Date
}

export interface ModuleScore {
  moduleId: string
  moduleName: string
  score: number
  weight: number
  weightedContribution: number
  status: 'healthy' | 'warning' | 'critical'
}

export interface ScoreCalculation {
  method: 'weighted_average' | 'percentile' | 'z_score'
  parameters: ScoreParameters
  factors: FactorWeight[]
}

export interface ScoreParameters {
  minValue: number
  maxValue: number
  neutralRange: [number, number]
  lookbackPeriod: number
}

export interface FactorWeight {
  factorId: string
  weight: number
  currentValue: number
  normalizedValue: number
}

export interface PercentileData {
  current: number
  historical: number[]
  percentile: number
  rank: 'very_low' | 'low' | 'average' | 'high' | 'very_high'
}

export interface ScoreThresholds {
  healthy: { min: number; max: number }
  warning: { min: number; max: number }
  critical: { min: number; max: number }
}

export const DEFAULT_SCORE_THRESHOLDS: ScoreThresholds = {
  healthy: { min: 70, max: 100 },
  warning: { min: 40, max: 69 },
  critical: { min: 0, max: 39 },
}

export interface ScoreTrend {
  direction: 'up' | 'down' | 'flat'
  strength: 'strong' | 'moderate' | 'weak'
  duration: number
  changeOverPeriod: number
}

export interface ScoreForecast {
  current: number
  predicted: number
  confidence: number
  horizon: string
  factors: string[]
}
