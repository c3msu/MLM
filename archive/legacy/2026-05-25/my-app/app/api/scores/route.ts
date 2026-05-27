import { NextRequest, NextResponse } from 'next/server'
import { getAllIndicators } from '@/lib/fred-api'
import { calculateOverallScore, calculateModuleScore } from '@/lib/scoring'
import { ModuleId } from '@/types/modules'

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

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    const moduleId = searchParams.get('moduleId') as ModuleId | null

    const indicators = await getAllIndicators()
    const indicatorMap = new Map(indicators.map(i => [i.seriesId, i]))

    if (moduleId) {
      const config = MODULE_CONFIGS[moduleId]
      if (!config) {
        return NextResponse.json(
          { success: false, error: 'Invalid module ID' },
          { status: 400 }
        )
      }

      const moduleIndicators = config.indicators
        .map(id => indicatorMap.get(id))
        .filter((i): i is NonNullable<typeof i> => i !== undefined)

      const module = calculateModuleScore(moduleId, config.name, moduleIndicators, config.weights)
      return NextResponse.json({ success: true, data: module })
    }

    // Calculate all modules
    const modules = (Object.keys(MODULE_CONFIGS) as ModuleId[]).map(id => {
      const config = MODULE_CONFIGS[id]
      const moduleIndicators = config.indicators
        .map(indId => indicatorMap.get(indId))
        .filter((i): i is NonNullable<typeof i> => i !== undefined)
      return calculateModuleScore(id, config.name, moduleIndicators, config.weights)
    })

    const overallScore = calculateOverallScore(modules)

    return NextResponse.json({
      success: true,
      data: {
        overall: overallScore,
        modules,
      },
    })
  } catch (error) {
    console.error('Scores API Error:', error)
    return NextResponse.json(
      { success: false, error: 'Failed to calculate scores' },
      { status: 500 }
    )
  }
}
