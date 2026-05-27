'use client'

import React from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { motion } from 'framer-motion'
import {
  LayoutDashboard,
  TrendingUp,
  TrendingDown,
  DollarSign,
  Home,
  Smile,
  Factory,
  Globe,
  Users,
  Settings,
  HelpCircle,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface SidebarProps {
  isCollapsed: boolean
  onToggle: () => void
}

const moduleItems = [
  { id: 'labor-market', label: 'Labor Market', icon: Users, href: '/module/labor-market/' },
  { id: 'inflation', label: 'Inflation', icon: TrendingUp, href: '/module/inflation/' },
  { id: 'gdp-growth', label: 'GDP Growth', icon: TrendingUp, href: '/module/gdp-growth/' },
  { id: 'interest-rates', label: 'Interest Rates', icon: DollarSign, href: '/module/interest-rates/' },
  { id: 'housing-market', label: 'Housing', icon: Home, href: '/module/housing-market/' },
  { id: 'consumer-sentiment', label: 'Consumer', icon: Smile, href: '/module/consumer-sentiment/' },
  { id: 'manufacturing', label: 'Manufacturing', icon: Factory, href: '/module/manufacturing/' },
  { id: 'international-trade', label: 'Trade', icon: Globe, href: '/module/international-trade/' },
]

const bottomItems = [
  { label: 'Settings', icon: Settings, href: '/profile/' },
  { label: 'Help', icon: HelpCircle, href: '/support/' },
]

export function Sidebar({ isCollapsed, onToggle }: SidebarProps) {
  const pathname = usePathname()

  const isActive = (href: string) => pathname === href

  return (
    <aside
      className={cn(
        'fixed left-0 top-16 h-[calc(100vh-4rem)] border-r bg-background transition-all duration-300 z-40',
        isCollapsed ? 'w-16' : 'w-64'
      )}
    >
      <div className="flex h-full flex-col">
        {/* Toggle Button */}
        <button
          onClick={onToggle}
          className="absolute -right-3 top-4 flex h-6 w-6 items-center justify-center rounded-full border bg-background shadow-sm hover:bg-accent"
        >
          {isCollapsed ? (
            <ChevronRight className="h-3 w-3" />
          ) : (
            <ChevronLeft className="h-3 w-3" />
          )}
        </button>

        {/* Dashboard Link */}
        <div className="p-3">
          <Link
            href="/dashboard/"
            className={cn(
              'flex items-center gap-3 rounded-md px-3 py-2 transition-colors',
              isActive('/dashboard/')
                ? 'bg-accent text-foreground'
                : 'text-muted-foreground hover:bg-accent hover:text-foreground'
            )}
          >
            <LayoutDashboard className="h-5 w-5 flex-shrink-0" />
            {!isCollapsed && <span className="text-sm font-medium">Dashboard</span>}
          </Link>
        </div>

        {/* Module Links */}
        <div className="flex-1 overflow-auto py-2">
          <div className={cn('px-3 pb-2', isCollapsed && 'px-2')}>
            {!isCollapsed && (
              <p className="px-3 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Modules
              </p>
            )}
          </div>
          <nav className="space-y-1 px-2">
            {moduleItems.map((item) => (
              <Link
                key={item.id}
                href={item.href}
                className={cn(
                  'flex items-center gap-3 rounded-md px-3 py-2 transition-colors relative',
                  isActive(item.href)
                    ? 'bg-accent text-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                )}
              >
                <item.icon className="h-5 w-5 flex-shrink-0" />
                {!isCollapsed && <span className="text-sm font-medium">{item.label}</span>}
                {isActive(item.href) && (
                  <motion.div
                    layoutId="sidebarActive"
                    className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-primary rounded-r-full"
                  />
                )}
              </Link>
            ))}
          </nav>
        </div>

        {/* Bottom Links */}
        <div className="border-t p-2">
          <nav className="space-y-1">
            {bottomItems.map((item) => (
              <Link
                key={item.label}
                href={item.href}
                className={cn(
                  'flex items-center gap-3 rounded-md px-3 py-2 transition-colors',
                  isActive(item.href)
                    ? 'bg-accent text-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-foreground'
                )}
              >
                <item.icon className="h-5 w-5 flex-shrink-0" />
                {!isCollapsed && <span className="text-sm font-medium">{item.label}</span>}
              </Link>
            ))}
          </nav>
        </div>
      </div>
    </aside>
  )
}
