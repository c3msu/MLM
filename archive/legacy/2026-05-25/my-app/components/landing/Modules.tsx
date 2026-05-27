'use client'

import React from 'react'
import Link from 'next/link'
import { motion } from 'framer-motion'
import { 
  Users, 
  TrendingUp, 
  TrendingDown, 
  DollarSign, 
  Home, 
  Smile, 
  Factory, 
  Globe,
  ArrowRight
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollReveal } from '@/components/shared/ScrollReveal'
import { cn } from '@/lib/utils'

const modules = [
  {
    id: 'labor-market',
    name: 'Labor Market',
    description: 'Track unemployment rates, job creation, and workforce participation.',
    icon: Users,
    color: '#3b82f6',
    score: 78,
    indicators: ['Unemployment Rate', 'Nonfarm Payrolls'],
  },
  {
    id: 'inflation',
    name: 'Inflation',
    description: 'Monitor consumer and producer price indices and inflation trends.',
    icon: TrendingUp,
    color: '#f59e0b',
    score: 65,
    indicators: ['CPI', 'PPI', 'Core Inflation'],
  },
  {
    id: 'gdp-growth',
    name: 'GDP Growth',
    description: 'Analyze gross domestic product and economic growth rates.',
    icon: TrendingUp,
    color: '#10b981',
    score: 82,
    indicators: ['Real GDP', 'Nominal GDP'],
  },
  {
    id: 'interest-rates',
    name: 'Interest Rates',
    description: 'Follow Federal Reserve policy and market interest rates.',
    icon: DollarSign,
    color: '#8b5cf6',
    score: 70,
    indicators: ['Fed Funds Rate', 'Treasury Yields'],
  },
  {
    id: 'housing-market',
    name: 'Housing Market',
    description: 'Track housing starts, sales, and price trends.',
    icon: Home,
    color: '#ec4899',
    score: 58,
    indicators: ['Housing Starts', 'Home Sales', 'Home Prices'],
  },
  {
    id: 'consumer-sentiment',
    name: 'Consumer Sentiment',
    description: 'Measure consumer confidence and spending intentions.',
    icon: Smile,
    color: '#06b6d4',
    score: 72,
    indicators: ['Consumer Confidence', 'Retail Sales'],
  },
  {
    id: 'manufacturing',
    name: 'Manufacturing',
    description: 'Monitor industrial production and manufacturing activity.',
    icon: Factory,
    color: '#f97316',
    score: 68,
    indicators: ['Industrial Production', 'PMI'],
  },
  {
    id: 'international-trade',
    name: 'International Trade',
    description: 'Track imports, exports, and trade balance.',
    icon: Globe,
    color: '#84cc16',
    score: 63,
    indicators: ['Trade Balance', 'Export/Import Data'],
  },
]

function ModuleCard({ module, index }: { module: typeof modules[0]; index: number }) {
  const getScoreColor = (score: number) => {
    if (score >= 70) return 'bg-score-green'
    if (score >= 40) return 'bg-score-yellow'
    return 'bg-score-red'
  }

  const getScoreBadge = (score: number) => {
    if (score >= 70) return 'success'
    if (score >= 40) return 'warning'
    return 'critical'
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ delay: index * 0.1, duration: 0.5 }}
    >
      <Link href={`/module/${module.id}/`}>
        <Card className="h-full hover:shadow-lg hover:scale-[1.02] transition-all cursor-pointer group">
          <CardContent className="p-6">
            <div className="flex items-start justify-between mb-4">
              <div
                className="h-12 w-12 rounded-lg flex items-center justify-center"
                style={{ backgroundColor: `${module.color}20` }}
              >
                <module.icon className="h-6 w-6" style={{ color: module.color }} />
              </div>
              <Badge variant={getScoreBadge(module.score)}>{module.score}</Badge>
            </div>

            <h3 className="text-lg font-semibold mb-2">{module.name}</h3>
            <p className="text-sm text-muted-foreground mb-4">{module.description}</p>

            {/* Score bar */}
            <div className="mb-4">
              <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                <motion.div
                  className={cn('h-full rounded-full', getScoreColor(module.score))}
                  initial={{ width: 0 }}
                  whileInView={{ width: `${module.score}%` }}
                  viewport={{ once: true }}
                  transition={{ duration: 1, delay: index * 0.1 + 0.3 }}
                />
              </div>
            </div>

            {/* Indicators */}
            <div className="flex flex-wrap gap-1">
              {module.indicators.map((indicator) => (
                <span
                  key={indicator}
                  className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground"
                >
                  {indicator}
                </span>
              ))}
            </div>

            <div className="mt-4 flex items-center text-sm text-primary opacity-0 group-hover:opacity-100 transition-opacity">
              Explore <ArrowRight className="h-4 w-4 ml-1" />
            </div>
          </CardContent>
        </Card>
      </Link>
    </motion.div>
  )
}

export function Modules() {
  return (
    <section className="py-20">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        <ScrollReveal>
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              Economic Modules
            </h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Eight comprehensive modules covering all major aspects of the economy.
            </p>
          </div>
        </ScrollReveal>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {modules.map((module, index) => (
            <ModuleCard key={module.id} module={module} index={index} />
          ))}
        </div>

        <ScrollReveal delay={0.4}>
          <div className="text-center mt-12">
            <Link href="/dashboard/">
              <Button size="lg">
                View All Modules
                <ArrowRight className="h-4 w-4 ml-2" />
              </Button>
            </Link>
          </div>
        </ScrollReveal>
      </div>
    </section>
  )
}
