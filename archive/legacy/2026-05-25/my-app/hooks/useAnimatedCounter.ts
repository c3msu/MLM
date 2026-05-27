'use client'

import { useState, useEffect, useRef, useCallback } from 'react'

interface UseAnimatedCounterOptions {
  start?: number
  end: number
  duration?: number
  delay?: number
  decimals?: number
  easing?: (t: number) => number
  onComplete?: () => void
}

// Easing functions
const easings = {
  linear: (t: number) => t,
  easeIn: (t: number) => t * t,
  easeOut: (t: number) => 1 - Math.pow(1 - t, 2),
  easeInOut: (t: number) => t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2,
  easeOutBounce: (t: number) => {
    const n1 = 7.5625
    const d1 = 2.75
    if (t < 1 / d1) {
      return n1 * t * t
    } else if (t < 2 / d1) {
      return n1 * (t -= 1.5 / d1) * t + 0.75
    } else if (t < 2.5 / d1) {
      return n1 * (t -= 2.25 / d1) * t + 0.9375
    } else {
      return n1 * (t -= 2.625 / d1) * t + 0.984375
    }
  },
}

export function useAnimatedCounter({
  start = 0,
  end,
  duration = 2000,
  delay = 0,
  decimals = 0,
  easing = easings.easeOut,
  onComplete,
}: UseAnimatedCounterOptions) {
  const [value, setValue] = useState(start)
  const [isAnimating, setIsAnimating] = useState(false)
  const animationRef = useRef<number | null>(null)
  const startTimeRef = useRef<number | null>(null)

  const animate = useCallback((timestamp: number) => {
    if (!startTimeRef.current) {
      startTimeRef.current = timestamp
    }

    const elapsed = timestamp - startTimeRef.current
    const progress = Math.min(elapsed / duration, 1)
    const easedProgress = easing(progress)
    const currentValue = start + (end - start) * easedProgress

    setValue(Number(currentValue.toFixed(decimals)))

    if (progress < 1) {
      animationRef.current = requestAnimationFrame(animate)
    } else {
      setValue(end)
      setIsAnimating(false)
      onComplete?.()
    }
  }, [start, end, duration, decimals, easing, onComplete])

  const startAnimation = useCallback(() => {
    if (isAnimating) return

    setIsAnimating(true)
    startTimeRef.current = null

    if (delay > 0) {
      setTimeout(() => {
        animationRef.current = requestAnimationFrame(animate)
      }, delay)
    } else {
      animationRef.current = requestAnimationFrame(animate)
    }
  }, [animate, delay, isAnimating])

  const stopAnimation = useCallback(() => {
    if (animationRef.current) {
      cancelAnimationFrame(animationRef.current)
      animationRef.current = null
    }
    setIsAnimating(false)
  }, [])

  const reset = useCallback(() => {
    stopAnimation()
    setValue(start)
    startTimeRef.current = null
  }, [start, stopAnimation])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current)
      }
    }
  }, [])

  return {
    value,
    isAnimating,
    startAnimation,
    stopAnimation,
    reset,
  }
}

// Hook for counting up when element is in view
export function useCountInView(
  end: number,
  options: Omit<UseAnimatedCounterOptions, 'end'> = {}
) {
  const [isInView, setIsInView] = useState(false)
  const ref = useRef<HTMLElement>(null)
  const hasAnimated = useRef(false)

  const counter = useAnimatedCounter({
    end,
    ...options,
  })

  useEffect(() => {
    const element = ref.current
    if (!element) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !hasAnimated.current) {
          setIsInView(true)
          hasAnimated.current = true
          counter.startAnimation()
        }
      },
      { threshold: 0.1 }
    )

    observer.observe(element)

    return () => observer.disconnect()
  }, [counter])

  return {
    ref,
    value: counter.value,
    isInView,
    isAnimating: counter.isAnimating,
  }
}

// Hook for staggered counter animations
export function useStaggeredCounters(
  values: number[],
  baseOptions: Omit<UseAnimatedCounterOptions, 'end'> = {}
) {
  const [started, setStarted] = useState(false)
  const counters = values.map((end, index) =>
    useAnimatedCounter({
      end,
      ...baseOptions,
      delay: (baseOptions.delay || 0) + index * 100,
    })
  )

  const startAll = useCallback(() => {
    if (started) return
    setStarted(true)
    counters.forEach(counter => counter.startAnimation())
  }, [counters, started])

  const resetAll = useCallback(() => {
    setStarted(false)
    counters.forEach(counter => counter.reset())
  }, [counters])

  return {
    values: counters.map(c => c.value),
    isAnimating: counters.some(c => c.isAnimating),
    startAll,
    resetAll,
  }
}

// Hook for score gauge animation
export function useScoreGaugeAnimation(
  targetScore: number,
  duration: number = 1500
) {
  const { value, isAnimating, startAnimation } = useAnimatedCounter({
    start: 0,
    end: targetScore,
    duration,
    easing: easings.easeOut,
  })

  // Auto-start on mount
  useEffect(() => {
    const timer = setTimeout(startAnimation, 300)
    return () => clearTimeout(timer)
  }, [startAnimation])

  // Get rotation angle for gauge needle
  const rotation = -90 + (value / 100) * 180

  return {
    score: value,
    rotation,
    isAnimating,
  }
}
