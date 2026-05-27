'use client'

import React from 'react'
import Link from 'next/link'
import { motion } from 'framer-motion'
import { Check, X } from 'lucide-react'
import { Card, CardContent, CardHeader } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollReveal } from '@/components/shared/ScrollReveal'
import { cn } from '@/lib/utils'

const plans = [
  {
    name: 'Free',
    description: 'Perfect for getting started',
    price: 0,
    period: 'month',
    features: [
      { text: 'Basic dashboard access', included: true },
      { text: '8 economic modules', included: true },
      { text: 'Daily data updates', included: true },
      { text: '7-day history', included: true },
      { text: 'Email support', included: false },
      { text: 'Export reports', included: false },
      { text: 'Custom alerts', included: false },
      { text: 'API access', included: false },
    ],
    cta: 'Get Started',
    href: '/signup/',
    highlighted: false,
  },
  {
    name: 'Pro',
    description: 'For serious investors',
    price: 19,
    period: 'month',
    features: [
      { text: 'Full dashboard access', included: true },
      { text: 'All 8 modules + detailed analysis', included: true },
      { text: 'Real-time data updates', included: true },
      { text: '5-year history', included: true },
      { text: 'Priority email support', included: true },
      { text: 'PDF & CSV exports', included: true },
      { text: 'Custom alerts (10)', included: true },
      { text: 'API access', included: false },
    ],
    cta: 'Start Free Trial',
    href: '/signup/',
    highlighted: true,
  },
  {
    name: 'Enterprise',
    description: 'For teams and businesses',
    price: 99,
    period: 'month',
    features: [
      { text: 'Everything in Pro', included: true },
      { text: 'Unlimited team members', included: true },
      { text: 'Real-time data + webhooks', included: true },
      { text: 'Full historical data', included: true },
      { text: '24/7 phone support', included: true },
      { text: 'All export formats', included: true },
      { text: 'Unlimited custom alerts', included: true },
      { text: 'Full API access', included: true },
    ],
    cta: 'Contact Sales',
    href: '/contact/',
    highlighted: false,
  },
]

export function Pricing() {
  return (
    <section className="py-20">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        <ScrollReveal>
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              Simple Pricing
            </h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Choose the plan that fits your needs. Upgrade or downgrade anytime.
            </p>
          </div>
        </ScrollReveal>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8 max-w-5xl mx-auto">
          {plans.map((plan, index) => (
            <ScrollReveal key={plan.name} delay={index * 0.1}>
              <motion.div
                whileHover={{ y: -5 }}
                transition={{ duration: 0.2 }}
              >
                <Card
                  className={cn(
                    'h-full relative',
                    plan.highlighted && 'border-primary shadow-lg scale-105'
                  )}
                >
                  {plan.highlighted && (
                    <Badge className="absolute -top-3 left-1/2 -translate-x-1/2">
                      Most Popular
                    </Badge>
                  )}

                  <CardHeader className="text-center pb-4">
                    <h3 className="text-xl font-semibold">{plan.name}</h3>
                    <p className="text-sm text-muted-foreground">{plan.description}</p>
                    <div className="mt-4">
                      <span className="text-4xl font-bold">${plan.price}</span>
                      <span className="text-muted-foreground">/{plan.period}</span>
                    </div>
                  </CardHeader>

                  <CardContent>
                    <ul className="space-y-3 mb-6">
                      {plan.features.map((feature) => (
                        <li key={feature.text} className="flex items-center gap-3">
                          {feature.included ? (
                            <Check className="h-4 w-4 text-score-green flex-shrink-0" />
                          ) : (
                            <X className="h-4 w-4 text-muted-foreground flex-shrink-0" />
                          )}
                          <span
                            className={cn(
                              'text-sm',
                              !feature.included && 'text-muted-foreground'
                            )}
                          >
                            {feature.text}
                          </span>
                        </li>
                      ))}
                    </ul>

                    <Link href={plan.href}>
                      <Button
                        className="w-full"
                        variant={plan.highlighted ? 'default' : 'outline'}
                      >
                        {plan.cta}
                      </Button>
                    </Link>
                  </CardContent>
                </Card>
              </motion.div>
            </ScrollReveal>
          ))}
        </div>
      </div>
    </section>
  )
}
