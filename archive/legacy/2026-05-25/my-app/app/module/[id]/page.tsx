'use client'

import React, { useState } from 'react'
import { useParams } from 'next/navigation'
import { MainLayout } from '@/components/layout/MainLayout'
import { Sidebar } from '@/components/layout/Sidebar'
import { ModuleDetail } from '@/components/modules/ModuleDetail'
import { useModule } from '@/hooks/useScores'
import { ModuleId } from '@/types/modules'
import { cn } from '@/lib/utils'

const validModuleIds: ModuleId[] = [
  'labor-market',
  'inflation',
  'gdp-growth',
  'interest-rates',
  'housing-market',
  'consumer-sentiment',
  'manufacturing',
  'international-trade',
]

export default function ModulePage() {
  const params = useParams()
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  
  const moduleId = params.id as string
  const isValidModule = validModuleIds.includes(moduleId as ModuleId)
  
  const { module, isLoading } = useModule(isValidModule ? (moduleId as ModuleId) : 'labor-market')

  if (!isValidModule) {
    return (
      <MainLayout showFooter={false}>
        <div className="flex min-h-[calc(100vh-4rem)]">
          <Sidebar 
            isCollapsed={sidebarCollapsed} 
            onToggle={() => setSidebarCollapsed(!sidebarCollapsed)} 
          />
          <main 
            className={cn(
              'flex-1 transition-all duration-300 p-6',
              sidebarCollapsed ? 'ml-16' : 'ml-64'
            )}
          >
            <div className="max-w-4xl mx-auto text-center py-20">
              <h1 className="text-2xl font-bold mb-4">Module Not Found</h1>
              <p className="text-muted-foreground">
                The requested module does not exist.
              </p>
            </div>
          </main>
        </div>
      </MainLayout>
    )
  }

  return (
    <MainLayout showFooter={false}>
      <div className="flex min-h-[calc(100vh-4rem)]">
        <Sidebar 
          isCollapsed={sidebarCollapsed} 
          onToggle={() => setSidebarCollapsed(!sidebarCollapsed)} 
        />
        
        <main 
          className={cn(
            'flex-1 transition-all duration-300 p-6',
            sidebarCollapsed ? 'ml-16' : 'ml-64'
          )}
        >
          <div className="max-w-4xl mx-auto">
            {isLoading || !module ? (
              <div className="space-y-6">
                <div className="h-8 w-48 bg-muted animate-pulse rounded" />
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                  <div className="h-64 bg-muted animate-pulse rounded" />
                  <div className="lg:col-span-2 h-64 bg-muted animate-pulse rounded" />
                </div>
                <div className="h-96 bg-muted animate-pulse rounded" />
              </div>
            ) : (
              <ModuleDetail module={module} />
            )}
          </div>
        </main>
      </div>
    </MainLayout>
  )
}
