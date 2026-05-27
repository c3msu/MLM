'use client'

import React from 'react'
import Link from 'next/link'
import { motion } from 'framer-motion'
import { ArrowRight, Play, BarChart3, TrendingUp, Activity } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { ScoreGauge } from '@/components/dashboard/ScoreGauge'
import { ScrollReveal } from '@/components/shared/ScrollReveal'

export function Hero() {
  return (
    <section className="relative overflow-hidden py-20 lg:py-32">
      {/* Background gradient */}
      <div className="absolute inset-0 bg-gradient-to-br from-primary/5 via-background to-accent-primary/5" />
      
      {/* Animated background shapes */}
      <div className="absolute inset-0 overflow-hidden">
        <motion.div
          className="absolute -top-1/2 -right-1/4 w-[800px] h-[800px] rounded-full bg-accent-primary/10 blur-3xl"
          animate={{
            scale: [1, 1.1, 1],
            opacity: [0.3, 0.5, 0.3],
          }}
          transition={{
            duration: 8,
            repeat: Infinity,
            ease: 'easeInOut',
          }}
        />
        <motion.div
          className="absolute -bottom-1/2 -left-1/4 w-[600px] h-[600px] rounded-full bg-score-green/10 blur-3xl"
          animate={{
            scale: [1.1, 1, 1.1],
            opacity: [0.3, 0.5, 0.3],
          }}
          transition={{
            duration: 10,
            repeat: Infinity,
            ease: 'easeInOut',
          }}
        />
      </div>

      <div className="container mx-auto px-4 sm:px-6 lg:px-8 relative">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          {/* Left content */}
          <div className="text-center lg:text-left">
            <ScrollReveal>
              <div className="inline-flex items-center gap-2 rounded-full border bg-background/50 px-4 py-1.5 text-sm mb-6">
                <span className="flex h-2 w-2 rounded-full bg-score-green animate-pulse" />
                Live Economic Data
              </div>
            </ScrollReveal>

            <ScrollReveal delay={0.1}>
              <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight mb-6">
                Understand the{' '}
                <span className="bg-gradient-to-r from-accent-primary to-accent-primary-light bg-clip-text text-transparent">
                  Economy
                </span>{' '}
                at a Glance
              </h1>
            </ScrollReveal>

            <ScrollReveal delay={0.2}>
              <p className="text-lg text-muted-foreground mb-8 max-w-xl mx-auto lg:mx-0">
                The Dial aggregates key macroeconomic indicators into a single, intuitive 
                score that helps you understand economic conditions in real-time.
              </p>
            </ScrollReveal>

            <ScrollReveal delay={0.3}>
              <div className="flex flex-col sm:flex-row gap-4 justify-center lg:justify-start">
                <Link href="/dashboard/">
                  <Button size="lg" className="gap-2">
                    Get Started
                    <ArrowRight className="h-4 w-4" />
                  </Button>
                </Link>
                <Link href="/about/">
                  <Button size="lg" variant="outline" className="gap-2">
                    <Play className="h-4 w-4" />
                    Watch Demo
                  </Button>
                </Link>
              </div>
            </ScrollReveal>

            {/* Stats */}
            <ScrollReveal delay={0.4}>
              <div className="mt-12 grid grid-cols-3 gap-8">
                <div>
                  <p className="text-3xl font-bold">8+</p>
                  <p className="text-sm text-muted-foreground">Modules</p>
                </div>
                <div>
                  <p className="text-3xl font-bold">50+</p>
                  <p className="text-sm text-muted-foreground">Indicators</p>
                </div>
                <div>
                  <p className="text-3xl font-bold">Real-time</p>
                  <p className="text-sm text-muted-foreground">Updates</p>
                </div>
              </div>
            </ScrollReveal>
          </div>

          {/* Right content - Gauge */}
          <ScrollReveal delay={0.2} direction="left">
            <div className="relative">
              <div className="relative bg-card border rounded-2xl p-8 shadow-2xl">
                <div className="absolute -top-4 -right-4 flex gap-2">
                  <div className="flex items-center gap-1 rounded-full bg-score-green/10 px-3 py-1 text-sm text-score-green">
                    <TrendingUp className="h-4 w-4" />
                    +2.4%
                  </div>
                </div>

                <div className="flex flex-col items-center">
                  <p className="text-sm text-muted-foreground mb-4">Current Economic Health</p>
                  <ScoreGauge score={72} size="lg" animated />
                  
                  <div className="mt-6 grid grid-cols-3 gap-4 w-full">
                    <div className="text-center p-3 rounded-lg bg-muted">
                      <BarChart3 className="h-5 w-5 mx-auto mb-1 text-score-green" />
                      <p className="text-xs text-muted-foreground">Labor</p>
                      <p className="font-semibold">78</p>
                    </div>
                    <div className="text-center p-3 rounded-lg bg-muted">
                      <Activity className="h-5 w-5 mx-auto mb-1 text-score-yellow" />
                      <p className="text-xs text-muted-foreground">Inflation</p>
                      <p className="font-semibold">65</p>
                    </div>
                    <div className="text-center p-3 rounded-lg bg-muted">
                      <TrendingUp className="h-5 w-5 mx-auto mb-1 text-score-green" />
                      <p className="text-xs text-muted-foreground">GDP</p>
                      <p className="font-semibold">82</p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Floating cards */}
              <motion.div
                className="absolute -bottom-6 -left-6 bg-card border rounded-xl p-4 shadow-lg"
                animate={{ y: [0, -10, 0] }}
                transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }}
              >
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-full bg-score-green/20 flex items-center justify-center">
                    <TrendingUp className="h-5 w-5 text-score-green" />
                  </div>
                  <div>
                    <p className="text-sm font-medium">Employment</p>
                    <p className="text-xs text-muted-foreground">+150K jobs</p>
                  </div>
                </div>
              </motion.div>

              <motion.div
                className="absolute -top-6 -right-6 bg-card border rounded-xl p-4 shadow-lg"
                animate={{ y: [0, 10, 0] }}
                transition={{ duration: 5, repeat: Infinity, ease: 'easeInOut' }}
              >
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-full bg-score-yellow/20 flex items-center justify-center">
                    <Activity className="h-5 w-5 text-score-yellow" />
                  </div>
                  <div>
                    <p className="text-sm font-medium">CPI</p>
                    <p className="text-xs text-muted-foreground">3.2% YoY</p>
                  </div>
                </div>
              </motion.div>
            </div>
          </ScrollReveal>
        </div>
      </div>
    </section>
  )
}
