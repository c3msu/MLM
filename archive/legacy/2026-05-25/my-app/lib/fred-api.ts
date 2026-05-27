import axios from 'axios'
import { FREDResponse, FREDSeries, EconomicIndicator, IndicatorConfig } from '@/types/fred'

const FRED_API_BASE = process.env.NEXT_PUBLIC_FRED_API_URL || 'https://api.stlouisfed.org/fred'
const FRED_API_KEY = process.env.FRED_API_KEY || ''

// Check if we should use mock data
const USE_MOCK_DATA = process.env.NEXT_PUBLIC_MOCK_DATA === 'true' || !FRED_API_KEY

// Create axios instance for FRED API
const fredClient = axios.create({
  baseURL: FRED_API_BASE,
  timeout: 10000,
})

// Indicator configurations
export const INDICATOR_CONFIGS: Record<string, IndicatorConfig> = {
  'UNRATE': {
    seriesId: 'UNRATE',
    name: 'Unemployment Rate',
    description: 'Civilian unemployment rate',
    category: 'employment',
    frequency: 'monthly',
    units: 'Percent',
    inverted: true,
    weight: 0.25,
  },
  'PAYEMS': {
    seriesId: 'PAYEMS',
    name: 'Nonfarm Payrolls',
    description: 'Total nonfarm payroll employment',
    category: 'employment',
    frequency: 'monthly',
    units: 'Thousands of Persons',
    inverted: false,
    weight: 0.25,
  },
  'CPIAUCSL': {
    seriesId: 'CPIAUCSL',
    name: 'Consumer Price Index',
    description: 'Consumer Price Index for All Urban Consumers',
    category: 'inflation',
    frequency: 'monthly',
    units: 'Index 1982-1984=100',
    inverted: true,
    weight: 0.30,
  },
  'FEDFUNDS': {
    seriesId: 'FEDFUNDS',
    name: 'Federal Funds Rate',
    description: 'Effective Federal Funds Rate',
    category: 'interest_rates',
    frequency: 'monthly',
    units: 'Percent',
    inverted: false,
    weight: 0.20,
  },
  'GDP': {
    seriesId: 'GDP',
    name: 'Gross Domestic Product',
    description: 'Gross Domestic Product',
    category: 'gdp',
    frequency: 'quarterly',
    units: 'Billions of Dollars',
    inverted: false,
    weight: 0.25,
  },
  'HOUST': {
    seriesId: 'HOUST',
    name: 'Housing Starts',
    description: 'New Privately-Owned Housing Units Started',
    category: 'housing',
    frequency: 'monthly',
    units: 'Thousands of Units',
    inverted: false,
    weight: 0.15,
  },
  'UMCSENT': {
    seriesId: 'UMCSENT',
    name: 'Consumer Sentiment',
    description: 'University of Michigan Consumer Sentiment Index',
    category: 'consumer',
    frequency: 'monthly',
    units: 'Index',
    inverted: false,
    weight: 0.15,
  },
  'INDPRO': {
    seriesId: 'INDPRO',
    name: 'Industrial Production',
    description: 'Industrial Production Index',
    category: 'manufacturing',
    frequency: 'monthly',
    units: 'Index 2017=100',
    inverted: false,
    weight: 0.15,
  },
}

// Mock data generator for development
function generateMockData(seriesId: string, observations: number = 24): { observations: Array<{ date: string; value: string }> } {
  const data: Array<{ date: string; value: string }> = []
  const baseValue = getBaseValue(seriesId)
  const volatility = getVolatility(seriesId)
  
  const endDate = new Date()
  
  for (let i = observations - 1; i >= 0; i--) {
    const date = new Date(endDate)
    const config = INDICATOR_CONFIGS[seriesId]
    
    if (config?.frequency === 'monthly') {
      date.setMonth(date.getMonth() - i)
    } else if (config?.frequency === 'quarterly') {
      date.setMonth(date.getMonth() - i * 3)
    } else {
      date.setDate(date.getDate() - i)
    }
    
    const randomChange = (Math.random() - 0.5) * volatility
    const trend = Math.sin(i / 6) * volatility * 0.5
    const value = baseValue + randomChange + trend
    
    data.push({
      date: date.toISOString().split('T')[0],
      value: value.toFixed(2),
    })
  }
  
  return { observations: data }
}

function getBaseValue(seriesId: string): number {
  const baseValues: Record<string, number> = {
    'UNRATE': 4.0,
    'PAYEMS': 155000,
    'CPIAUCSL': 300,
    'FEDFUNDS': 5.0,
    'GDP': 27000,
    'HOUST': 1400,
    'UMCSENT': 65,
    'INDPRO': 105,
  }
  return baseValues[seriesId] || 100
}

function getVolatility(seriesId: string): number {
  const volatilities: Record<string, number> = {
    'UNRATE': 0.5,
    'PAYEMS': 200,
    'CPIAUCSL': 5,
    'FEDFUNDS': 0.25,
    'GDP': 500,
    'HOUST': 100,
    'UMCSENT': 5,
    'INDPRO': 2,
  }
  return volatilities[seriesId] || 1
}

// Fetch observations for a series
export async function fetchSeriesObservations(
  seriesId: string,
  startDate?: string,
  endDate?: string
): Promise<FREDResponse> {
  if (USE_MOCK_DATA) {
    const mockData = generateMockData(seriesId)
    return {
      realtime_start: new Date().toISOString().split('T')[0],
      realtime_end: new Date().toISOString().split('T')[0],
      observation_start: startDate || '',
      observation_end: endDate || '',
      units: 'lin',
      output_type: 1,
      file_type: 'json',
      order_by: 'observation_date',
      sort_order: 'asc',
      count: mockData.observations.length,
      offset: 0,
      limit: 1000,
      observations: mockData.observations,
    }
  }

  const params: Record<string, string> = {
    series_id: seriesId,
    api_key: FRED_API_KEY,
    file_type: 'json',
    sort_order: 'asc',
  }
  
  if (startDate) params.observation_start = startDate
  if (endDate) params.observation_end = endDate

  const response = await fredClient.get('/series/observations', { params })
  return response.data
}

// Fetch series information
export async function fetchSeriesInfo(seriesId: string): Promise<FREDSeries> {
  if (USE_MOCK_DATA) {
    const config = INDICATOR_CONFIGS[seriesId]
    return {
      id: seriesId,
      title: config?.name || seriesId,
      observation_start: '2000-01-01',
      observation_end: new Date().toISOString().split('T')[0],
      frequency: config?.frequency || 'Monthly',
      frequency_short: 'M',
      units: config?.units || 'Index',
      units_short: 'Idx',
      seasonal_adjustment: 'Seasonally Adjusted',
      seasonal_adjustment_short: 'SA',
      last_updated: new Date().toISOString(),
      popularity: 100,
      group_popularity: 100,
      notes: config?.description || '',
    }
  }

  const response = await fredClient.get('/series', {
    params: {
      series_id: seriesId,
      api_key: FRED_API_KEY,
      file_type: 'json',
    },
  })
  
  return response.data.seriess[0]
}

// Get economic indicator with current and historical data
export async function getEconomicIndicator(
  seriesId: string,
  yearsOfHistory: number = 5
): Promise<EconomicIndicator> {
  const config = INDICATOR_CONFIGS[seriesId]
  const endDate = new Date()
  const startDate = new Date()
  startDate.setFullYear(startDate.getFullYear() - yearsOfHistory)

  const [seriesInfo, observationsData] = await Promise.all([
    fetchSeriesInfo(seriesId),
    fetchSeriesObservations(
      seriesId,
      startDate.toISOString().split('T')[0],
      endDate.toISOString().split('T')[0]
    ),
  ])

  const observations = observationsData.observations
    .filter(obs => obs.value !== '.')
    .map(obs => ({
      date: new Date(obs.date),
      value: parseFloat(obs.value),
    }))
    .sort((a, b) => a.date.getTime() - b.date.getTime())

  const currentValue = observations[observations.length - 1]?.value || 0
  const previousValue = observations[observations.length - 2]?.value || currentValue
  const change = currentValue - previousValue
  const changePercent = previousValue !== 0 ? (change / previousValue) * 100 : 0

  return {
    id: seriesId,
    seriesId,
    name: config?.name || seriesInfo.title,
    description: config?.description || seriesInfo.notes,
    category: config?.category || 'other',
    frequency: config?.frequency || 'monthly',
    units: config?.units || seriesInfo.units,
    lastValue: currentValue,
    previousValue,
    change,
    changePercent,
    lastUpdated: new Date(seriesInfo.last_updated),
    historicalData: observations,
  }
}

// Get multiple indicators
export async function getMultipleIndicators(seriesIds: string[]): Promise<EconomicIndicator[]> {
  const indicators = await Promise.all(
    seriesIds.map(id => getEconomicIndicator(id))
  )
  return indicators
}

// Get all configured indicators
export async function getAllIndicators(): Promise<EconomicIndicator[]> {
  const seriesIds = Object.keys(INDICATOR_CONFIGS)
  return getMultipleIndicators(seriesIds)
}
