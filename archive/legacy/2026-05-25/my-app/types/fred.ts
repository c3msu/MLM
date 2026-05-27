// FRED API Types

export interface FREDSeries {
  id: string
  title: string
  observation_start: string
  observation_end: string
  frequency: string
  frequency_short: string
  units: string
  units_short: string
  seasonal_adjustment: string
  seasonal_adjustment_short: string
  last_updated: string
  popularity: number
  group_popularity: number
  notes: string
}

export interface FRADOBServation {
  date: string
  value: string
}

export interface FREDResponse {
  realtime_start: string
  realtime_end: string
  observation_start: string
  observation_end: string
  units: string
  output_type: number
  file_type: string
  order_by: string
  sort_order: string
  count: number
  offset: number
  limit: number
  observations: FRADOBServation[]
}

export interface FREDSearchResult {
  realtime_start: string
  realtime_end: string
  order_by: string
  sort_order: string
  count: number
  offset: number
  limit: number
  seriess: FREDSeries[]
}

export interface EconomicIndicator {
  id: string
  seriesId: string
  name: string
  description: string
  category: string
  frequency: 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'annual'
  units: string
  lastValue: number
  previousValue: number
  change: number
  changePercent: number
  lastUpdated: Date
  historicalData: IndicatorDataPoint[]
}

export interface IndicatorDataPoint {
  date: Date
  value: number
}

export type IndicatorCategory = 
  | 'employment'
  | 'inflation'
  | 'gdp'
  | 'interest_rates'
  | 'housing'
  | 'consumer'
  | 'manufacturing'
  | 'trade'

export interface IndicatorConfig {
  seriesId: string
  name: string
  description: string
  category: IndicatorCategory
  frequency: 'daily' | 'weekly' | 'monthly' | 'quarterly' | 'annual'
  units: string
  inverted: boolean
  weight: number
}
