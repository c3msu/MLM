'use client'

import React from 'react'
import { motion } from 'framer-motion'
import { 
  BarChart3, 
  TrendingUp, 
  Bell, 
  Download, 
  Shield, 
  Zap,
  Globe,
  Clock
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { ScrollReveal, StaggerReveal } from '@/components/shared/ScrollReveal'

const features = [
  {
    icon: BarChart3,
    title: 'Comprehensive Dashboard',
    description: 'View all key economic indicators in one place with intuitive visualizations and real-time updates.',
  },
  {
    icon: TrendingUp,
    title: 'Smart Scoring',
    description: 'Our proprietary algorithm calculates an overall economic health score based on multiple weighted factors.',
  },
  {
    icon: Bell,
    title: 'Custom Alerts',
    description: 'Set up personalized notifications for significant changes in economic indicators that matter to you.',
  },
  {
    icon: Download,
    title: 'Export Reports',
    description: 'Download detailed reports in PDF, Excel, or CSV format for further analysis and sharing.',
  },
  {
    icon: Shield,
    title: 'Data Integrity',
    description: 'All data sourced directly from FRED (Federal Reserve Economic Data) for maximum reliability.',
  },
  {
    icon: Zap,
    title: 'Real-time Updates',
    description: 'Get the latest economic data as soon as it is published by official sources.',
  },
  {
    icon: Globe,
    title: 'Multi-language',
    description: 'Access the dashboard in multiple languages including English and Chinese.',
  },
  {
    icon: Clock,
    title: 'Historical Analysis',
    description: 'Analyze trends over time with up to 50 years of historical economic data.',
  },
]

export function Features() {
  return (
    <section className="py-20 bg-muted/30">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        <ScrollReveal>
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              Powerful Features
            </h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Everything you need to track and understand the economy, all in one place.
            </p>
          </div>
        </ScrollReveal>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {features.map((feature, index) => (
            <ScrollReveal key={feature.title} delay={index * 0.1}>
              <Card className="h-full hover:shadow-lg transition-shadow group">
                <CardContent className="p-6">
                  <div className="h-12 w-12 rounded-lg bg-primary/10 flex items-center justify-center mb-4 group-hover:bg-primary/20 transition-colors">
                    <feature.icon className="h-6 w-6 text-primary" />
                  </div>
                  <h3 className="text-lg font-semibold mb-2">{feature.title}</h3>
                  <p className="text-sm text-muted-foreground">{feature.description}</p>
                </CardContent>
              </Card>
            </ScrollReveal>
          ))}
        </div>
      </div>
    </section>
  )
}
