import { NextRequest, NextResponse } from 'next/server'
import { getEconomicIndicator, getAllIndicators } from '@/lib/fred-api'

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url)
    const seriesId = searchParams.get('seriesId')
    const action = searchParams.get('action')

    if (action === 'all') {
      const indicators = await getAllIndicators()
      return NextResponse.json({ success: true, data: indicators })
    }

    if (seriesId) {
      const indicator = await getEconomicIndicator(seriesId)
      return NextResponse.json({ success: true, data: indicator })
    }

    return NextResponse.json(
      { success: false, error: 'Missing seriesId parameter' },
      { status: 400 }
    )
  } catch (error) {
    console.error('FRED API Error:', error)
    return NextResponse.json(
      { success: false, error: 'Failed to fetch economic data' },
      { status: 500 }
    )
  }
}
