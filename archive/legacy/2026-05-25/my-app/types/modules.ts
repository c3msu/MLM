// Module Types for The Dial

export type ModuleId = 
  | 'labor-market'
  | 'inflation'
  | 'gdp-growth'
  | 'interest-rates'
  | 'housing-market'
  | 'consumer-sentiment'
  | 'manufacturing'
  | 'international-trade'

export interface Module {
  id: ModuleId
  name: string
  shortName: string
  description: string
  icon: string
  color: string
  score: number
  previousScore: number
  trend: 'up' | 'down' | 'stable'
  weight: number
  factors: Factor[]
  lastUpdated: Date
  status: 'healthy' | 'warning' | 'critical'
}

export interface Factor {
  id: string
  name: string
  description: string
  seriesId: string
  weight: number
  value: number
  previousValue: number
  change: number
  changePercent: number
  contribution: number
  status: 'positive' | 'neutral' | 'negative'
  direction: 'higher_is_better' | 'lower_is_better' | 'neutral'
  historicalData: FactorDataPoint[]
  lastUpdated: Date
}

export interface FactorDataPoint {
  date: Date
  value: number
  percentile?: number
}

export interface ModuleDetail extends Module {
  detailedDescription: string
  methodology: string
  interpretation: {
    healthy: string
    warning: string
    critical: string
  }
  relatedModules: ModuleId[]
  historicalScores: ModuleScoreHistory[]
}

export interface ModuleScoreHistory {
  date: Date
  score: number
}

export interface ModuleComparison {
  moduleId: ModuleId
  currentScore: number
  previousScore: number
  rank: number
  percentile: number
}

export interface FactorBreakdown {
  factorId: string
  factorName: string
  contribution: number
  weight: number
  impact: 'high' | 'medium' | 'low'
}

export interface ModuleAlert {
  id: string
  moduleId: ModuleId
  type: 'score_change' | 'threshold_crossed' | 'trend_reversal'
  severity: 'info' | 'warning' | 'critical'
  message: string
  createdAt: Date
  read: boolean
}
