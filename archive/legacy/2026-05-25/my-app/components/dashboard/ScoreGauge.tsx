'use client'

import React, { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { cn, getScoreColor, getScoreStatus } from '@/lib/utils'
import { useScoreGaugeAnimation } from '@/hooks/useAnimatedCounter'

interface ScoreGaugeProps {
  score: number
  size?: 'sm' | 'md' | 'lg'
  showLabel?: boolean
  className?: string
  animated?: boolean
}

const sizeConfig = {
  sm: { width: 120, strokeWidth: 8, fontSize: 24 },
  md: { width: 200, strokeWidth: 12, fontSize: 40 },
  lg: { width: 300, strokeWidth: 16, fontSize: 56 },
}

export function ScoreGauge({
  score,
  size = 'md',
  showLabel = true,
  className,
  animated = true,
}: ScoreGaugeProps) {
  const config = sizeConfig[size]
  const radius = (config.width - config.strokeWidth) / 2
  const circumference = Math.PI * radius
  const center = config.width / 2

  const { score: animatedScore, rotation, isAnimating } = useScoreGaugeAnimation(
    animated ? score : score,
    1500
  )

  const displayScore = animated ? animatedScore : score
  const scoreColor = getScoreColor(score)
  const scoreStatus = getScoreStatus(score)

  // Get color based on score
  const getColor = (s: number) => {
    if (s >= 70) return '#22c55e'
    if (s >= 40) return '#eab308'
    return '#ef4444'
  }

  const color = getColor(score)

  return (
    <div className={cn('flex flex-col items-center', className)}>
      <div className="relative" style={{ width: config.width, height: config.width / 2 + 20 }}>
        <svg
          width={config.width}
          height={config.width / 2 + 20}
          viewBox={`0 0 ${config.width} ${config.width / 2 + 20}`}
        >
          {/* Background arc */}
          <path
            d={`M ${config.strokeWidth / 2} ${center} A ${radius} ${radius} 0 0 1 ${config.width - config.strokeWidth / 2} ${center}`}
            fill="none"
            stroke="currentColor"
            strokeWidth={config.strokeWidth}
            className="text-muted"
            strokeLinecap="round"
          />

          {/* Colored arc segments */}
          <defs>
            <linearGradient id={`gaugeGradient-${size}`} x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#ef4444" />
              <stop offset="40%" stopColor="#eab308" />
              <stop offset="70%" stopColor="#22c55e" />
            </linearGradient>
          </defs>

          {/* Progress arc */}
          <motion.path
            d={`M ${config.strokeWidth / 2} ${center} A ${radius} ${radius} 0 0 1 ${config.width - config.strokeWidth / 2} ${center}`}
            fill="none"
            stroke={`url(#gaugeGradient-${size})`}
            strokeWidth={config.strokeWidth}
            strokeLinecap="round"
            initial={{ pathLength: 0 }}
            animate={{ pathLength: score / 100 }}
            transition={{ duration: 1.5, ease: 'easeOut' }}
            style={{
              strokeDasharray: circumference,
            }}
          />

          {/* Needle */}
          <motion.g
            initial={{ rotate: -90 }}
            animate={{ rotate: rotation }}
            style={{
              transformOrigin: `${center}px ${center}px`,
            }}
            transition={{ duration: 1.5, ease: 'easeOut' }}
          >
            <line
              x1={center}
              y1={center}
              x2={center}
              y2={config.strokeWidth}
              stroke={color}
              strokeWidth={config.strokeWidth / 2}
              strokeLinecap="round"
            />
            <circle
              cx={center}
              cy={center}
              r={config.strokeWidth}
              fill={color}
            />
          </motion.g>

          {/* Ticks */}
          {[0, 25, 50, 75, 100].map((tick) => {
            const angle = -90 + (tick / 100) * 180
            const rad = (angle * Math.PI) / 180
            const tickRadius = radius + config.strokeWidth
            const x1 = center + (tickRadius - 8) * Math.cos(rad)
            const y1 = center + (tickRadius - 8) * Math.sin(rad)
            const x2 = center + tickRadius * Math.cos(rad)
            const y2 = center + tickRadius * Math.sin(rad)

            return (
              <g key={tick}>
                <line
                  x1={x1}
                  y1={y1}
                  x2={x2}
                  y2={y2}
                  stroke="currentColor"
                  strokeWidth={2}
                  className="text-muted-foreground"
                />
                <text
                  x={center + (tickRadius + 15) * Math.cos(rad)}
                  y={center + (tickRadius + 15) * Math.sin(rad)}
                  textAnchor="middle"
                  dominantBaseline="middle"
                  className="text-xs fill-muted-foreground"
                >
                  {tick}
                </text>
              </g>
            )
          })}
        </svg>

        {/* Score display */}
        <div className="absolute bottom-0 left-1/2 -translate-x-1/2 text-center">
          <motion.span
            className="font-bold"
            style={{ fontSize: config.fontSize, color }}
            initial={{ opacity: 0, scale: 0.5 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.5, duration: 0.3 }}
          >
            {Math.round(displayScore)}
          </motion.span>
        </div>
      </div>

      {showLabel && (
        <motion.div
          className="mt-2 text-center"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.8 }}
        >
          <span
            className={cn(
              'inline-flex items-center rounded-full px-3 py-1 text-sm font-medium',
              scoreStatus === 'healthy' && 'bg-score-green/10 text-score-green',
              scoreStatus === 'warning' && 'bg-score-yellow/10 text-score-yellow',
              scoreStatus === 'critical' && 'bg-score-red/10 text-score-red'
            )}
          >
            {scoreStatus === 'healthy' && 'Healthy'}
            {scoreStatus === 'warning' && 'Warning'}
            {scoreStatus === 'critical' && 'Critical'}
          </span>
        </motion.div>
      )}
    </div>
  )
}
