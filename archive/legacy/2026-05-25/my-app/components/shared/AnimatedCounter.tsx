'use client'

import React, { useEffect, useRef, useState } from 'react'
import { useCountInView } from '@/hooks/useAnimatedCounter'
import { cn, formatNumber } from '@/lib/utils'

interface AnimatedCounterProps {
  value: number
  duration?: number
  decimals?: number
  prefix?: string
  suffix?: string
  className?: string
  formatter?: (value: number) => string
}

export function AnimatedCounter({
  value,
  duration = 2000,
  decimals = 0,
  prefix = '',
  suffix = '',
  className,
  formatter,
}: AnimatedCounterProps) {
  const { ref, value: animatedValue, isInView } = useCountInView(value, {
    duration,
    decimals,
  })

  const displayValue = formatter
    ? formatter(animatedValue)
    : formatNumber(animatedValue, decimals)

  return (
    <span ref={ref as React.RefObject<HTMLSpanElement>} className={className}>
      {prefix}
      {displayValue}
      {suffix}
    </span>
  )
}

// Simple counter that animates on mount
export function SimpleCounter({
  value,
  duration = 1500,
  decimals = 0,
  prefix = '',
  suffix = '',
  className,
}: AnimatedCounterProps) {
  const [displayValue, setDisplayValue] = useState(0)
  const startTimeRef = useRef<number | null>(null)
  const animationRef = useRef<number | null>(null)

  useEffect(() => {
    const animate = (timestamp: number) => {
      if (!startTimeRef.current) {
        startTimeRef.current = timestamp
      }

      const elapsed = timestamp - startTimeRef.current
      const progress = Math.min(elapsed / duration, 1)
      
      // Ease out cubic
      const eased = 1 - Math.pow(1 - progress, 3)
      const currentValue = value * eased

      setDisplayValue(currentValue)

      if (progress < 1) {
        animationRef.current = requestAnimationFrame(animate)
      }
    }

    animationRef.current = requestAnimationFrame(animate)

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
    }
  }, [value, duration])

  return (
    <span className={className}>
      {prefix}
      {formatNumber(displayValue, decimals)}
      {suffix}
    </span>
  )
}

// Stat card with animated counter
interface StatCardProps {
  label: string
  value: number
  change?: number
  prefix?: string
  suffix?: string
  decimals?: number
  className?: string
}

export function StatCard({
  label,
  value,
  change,
  prefix = '',
  suffix = '',
  decimals = 0,
  className,
}: StatCardProps) {
  return (
    <div className={cn('p-4 rounded-lg border bg-card', className)}>
      <p className="text-sm text-muted-foreground">{label}</p>
      <div className="flex items-baseline gap-2 mt-1">
        <span className="text-2xl font-bold">
          <SimpleCounter
            value={value}
            prefix={prefix}
            suffix={suffix}
            decimals={decimals}
          />
        </span>
        {change !== undefined && (
          <span
            className={cn(
              'text-sm font-medium',
              change > 0 && 'text-score-green',
              change < 0 && 'text-score-red',
              change === 0 && 'text-muted-foreground'
            )}
          >
            {change > 0 ? '+' : ''}
            {change}%
          </span>
        )}
      </div>
    </div>
  )
}
