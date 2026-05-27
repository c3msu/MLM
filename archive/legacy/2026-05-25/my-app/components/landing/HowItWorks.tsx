'use client'

import React from 'react'
import { motion } from 'framer-motion'
import { Database, Calculator, LineChart } from 'lucide-react'
import { ScrollReveal } from '@/components/shared/ScrollReveal'

const steps = [
  {
    number: '01',
    icon: Database,
    title: 'Data Collection',
    description: 'We collect real-time economic data from trusted sources like FRED (Federal Reserve Economic Data), ensuring accuracy and reliability.',
    details: [
      '50+ economic indicators',
      'Daily data updates',
      'Historical data back to 1970',
      'Multiple data sources verified',
    ],
  },
  {
    number: '02',
    icon: Calculator,
    title: 'Smart Analysis',
    description: 'Our proprietary algorithm analyzes each indicator, calculating percentiles and weighted scores based on historical context.',
    details: [
      'Percentile-based scoring',
      'Weighted factor analysis',
      'Trend detection',
      'Anomaly identification',
    ],
  },
  {
    number: '03',
    icon: LineChart,
    title: 'Clear Insights',
    description: 'Get actionable insights through our intuitive dashboard, with visualizations that make complex data easy to understand.',
    details: [
      'Overall health score (0-100)',
      'Module breakdowns',
      'Trend visualizations',
      'Custom alerts',
    ],
  },
]

export function HowItWorks() {
  return (
    <section className="py-20 bg-muted/30">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        <ScrollReveal>
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              How It Works
            </h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Simple, data-driven insights in three steps.
            </p>
          </div>
        </ScrollReveal>

        <div className="relative">
          {/* Connecting line */}
          <div className="hidden lg:block absolute top-1/2 left-0 right-0 h-0.5 bg-border -translate-y-1/2" />

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 lg:gap-12">
            {steps.map((step, index) => (
              <ScrollReveal key={step.number} delay={index * 0.2}>
                <motion.div
                  className="relative"
                  whileHover={{ y: -5 }}
                  transition={{ duration: 0.2 }}
                >
                  {/* Step number */}
                  <div className="absolute -top-4 left-1/2 -translate-x-1/2 lg:left-0 lg:translate-x-0 z-10">
                    <div className="h-8 w-8 rounded-full bg-primary flex items-center justify-center text-primary-foreground text-sm font-bold">
                      {step.number}
                    </div>
                  </div>

                  <div className="pt-8 text-center lg:text-left">
                    <div className="inline-flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 mb-6">
                      <step.icon className="h-8 w-8 text-primary" />
                    </div>

                    <h3 className="text-xl font-semibold mb-3">{step.title}</h3>
                    <p className="text-muted-foreground mb-6">{step.description}</p>

                    <ul className="space-y-2">
                      {step.details.map((detail) => (
                        <li key={detail} className="flex items-center gap-2 text-sm">
                          <div className="h-1.5 w-1.5 rounded-full bg-primary" />
                          {detail}
                        </li>
                      ))}
                    </ul>
                  </div>
                </motion.div>
              </ScrollReveal>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
