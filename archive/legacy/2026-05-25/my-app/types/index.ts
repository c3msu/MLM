// Core types for The Dial application

export interface User {
  id: string
  email: string
  name: string
  avatar?: string
  role: 'free' | 'pro' | 'enterprise'
  createdAt: Date
  preferences: UserPreferences
}

export interface UserPreferences {
  theme: 'light' | 'dark' | 'system'
  language: 'en' | 'zh'
  notifications: boolean
  defaultTimeRange: TimeRange
}

export type TimeRange = '1M' | '3M' | '6M' | '1Y' | '3Y' | '5Y' | 'ALL'

export interface NavItem {
  label: string
  href: string
  icon?: string
  children?: NavItem[]
}

export interface Feature {
  id: string
  title: string
  description: string
  icon: string
}

export interface PricingPlan {
  id: string
  name: string
  price: number
  period: 'month' | 'year'
  features: string[]
  highlighted?: boolean
  cta: string
}

export interface FAQItem {
  question: string
  answer: string
}

export interface ChartDataPoint {
  date: string
  value: number
  label?: string
}

export interface ExportOptions {
  format: 'pdf' | 'excel' | 'csv'
  includeCharts: boolean
  dateRange: TimeRange
}
