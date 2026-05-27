'use client'

import { useEffect, useState, useCallback } from 'react'

type Theme = 'light' | 'dark' | 'system'

interface ThemeState {
  theme: Theme
  resolvedTheme: 'light' | 'dark'
  setTheme: (theme: Theme) => void
  toggleTheme: () => void
}

const THEME_STORAGE_KEY = 'the-dial-theme'

export function useTheme(): ThemeState {
  const [theme, setThemeState] = useState<Theme>('system')
  const [resolvedTheme, setResolvedTheme] = useState<'light' | 'dark'>('light')
  const [mounted, setMounted] = useState(false)

  // Initialize theme from storage
  useEffect(() => {
    setMounted(true)
    
    const storedTheme = localStorage.getItem(THEME_STORAGE_KEY) as Theme | null
    if (storedTheme && ['light', 'dark', 'system'].includes(storedTheme)) {
      setThemeState(storedTheme)
    }
  }, [])

  // Apply theme to document
  useEffect(() => {
    if (!mounted) return

    const root = document.documentElement
    const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    const activeTheme = theme === 'system' ? systemTheme : theme

    setResolvedTheme(activeTheme)

    if (activeTheme === 'dark') {
      root.classList.add('dark')
    } else {
      root.classList.remove('dark')
    }

    // Set CSS variables for theming
    root.style.setProperty('--background', activeTheme === 'dark' ? '222.2 84% 4.9%' : '0 0% 100%')
    root.style.setProperty('--foreground', activeTheme === 'dark' ? '210 40% 98%' : '222.2 84% 4.9%')
    root.style.setProperty('--card', activeTheme === 'dark' ? '222.2 84% 4.9%' : '0 0% 100%')
    root.style.setProperty('--card-foreground', activeTheme === 'dark' ? '210 40% 98%' : '222.2 84% 4.9%')
    root.style.setProperty('--popover', activeTheme === 'dark' ? '222.2 84% 4.9%' : '0 0% 100%')
    root.style.setProperty('--popover-foreground', activeTheme === 'dark' ? '210 40% 98%' : '222.2 84% 4.9%')
    root.style.setProperty('--primary', activeTheme === 'dark' ? '217.2 91.2% 59.8%' : '221.2 83.2% 53.3%')
    root.style.setProperty('--primary-foreground', activeTheme === 'dark' ? '222.2 47.4% 11.2%' : '210 40% 98%')
    root.style.setProperty('--secondary', activeTheme === 'dark' ? '217.2 32.6% 17.5%' : '210 40% 96.1%')
    root.style.setProperty('--secondary-foreground', activeTheme === 'dark' ? '210 40% 98%' : '222.2 47.4% 11.2%')
    root.style.setProperty('--muted', activeTheme === 'dark' ? '217.2 32.6% 17.5%' : '210 40% 96.1%')
    root.style.setProperty('--muted-foreground', activeTheme === 'dark' ? '215 20.2% 65.1%' : '215.4 16.3% 46.9%')
    root.style.setProperty('--accent', activeTheme === 'dark' ? '217.2 32.6% 17.5%' : '210 40% 96.1%')
    root.style.setProperty('--accent-foreground', activeTheme === 'dark' ? '210 40% 98%' : '222.2 47.4% 11.2%')
    root.style.setProperty('--destructive', activeTheme === 'dark' ? '0 62.8% 30.6%' : '0 84.2% 60.2%')
    root.style.setProperty('--destructive-foreground', activeTheme === 'dark' ? '210 40% 98%' : '210 40% 98%')
    root.style.setProperty('--border', activeTheme === 'dark' ? '217.2 32.6% 17.5%' : '214.3 31.8% 91.4%')
    root.style.setProperty('--input', activeTheme === 'dark' ? '217.2 32.6% 17.5%' : '214.3 31.8% 91.4%')
    root.style.setProperty('--ring', activeTheme === 'dark' ? '224.3 76.3% 48%' : '221.2 83.2% 53.3%')
    root.style.setProperty('--radius', '0.5rem')
  }, [theme, mounted])

  // Listen for system theme changes
  useEffect(() => {
    if (!mounted) return

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    
    const handleChange = () => {
      if (theme === 'system') {
        const newTheme = mediaQuery.matches ? 'dark' : 'light'
        setResolvedTheme(newTheme)
      }
    }

    mediaQuery.addEventListener('change', handleChange)
    return () => mediaQuery.removeEventListener('change', handleChange)
  }, [theme, mounted])

  // Set theme function
  const setTheme = useCallback((newTheme: Theme) => {
    setThemeState(newTheme)
    localStorage.setItem(THEME_STORAGE_KEY, newTheme)
  }, [])

  // Toggle theme function
  const toggleTheme = useCallback(() => {
    const themes: Theme[] = ['light', 'dark', 'system']
    const currentIndex = themes.indexOf(theme)
    const nextTheme = themes[(currentIndex + 1) % themes.length]
    setTheme(nextTheme)
  }, [theme, setTheme])

  // Prevent hydration mismatch
  if (!mounted) {
    return {
      theme: 'system',
      resolvedTheme: 'light',
      setTheme: () => {},
      toggleTheme: () => {},
    }
  }

  return {
    theme,
    resolvedTheme,
    setTheme,
    toggleTheme,
  }
}

// Hook for theme-aware colors
export function useThemeColors() {
  const { resolvedTheme } = useTheme()
  const isDark = resolvedTheme === 'dark'

  return {
    isDark,
    colors: {
      background: isDark ? '#0f172a' : '#ffffff',
      foreground: isDark ? '#f8fafc' : '#0f172a',
      card: isDark ? '#1e293b' : '#ffffff',
      border: isDark ? '#334155' : '#e2e8f0',
      muted: isDark ? '#334155' : '#f1f5f9',
      'muted-foreground': isDark ? '#94a3b8' : '#64748b',
      primary: isDark ? '#60a5fa' : '#3b82f6',
      secondary: isDark ? '#1e293b' : '#f1f5f9',
      accent: isDark ? '#334155' : '#f1f5f9',
    },
    chartColors: {
      primary: isDark ? '#60a5fa' : '#3b82f6',
      secondary: isDark ? '#a78bfa' : '#8b5cf6',
      success: isDark ? '#4ade80' : '#22c55e',
      warning: isDark ? '#facc15' : '#eab308',
      danger: isDark ? '#f87171' : '#ef4444',
      neutral: isDark ? '#94a3b8' : '#64748b',
    },
  }
}
