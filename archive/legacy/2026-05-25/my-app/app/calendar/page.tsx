'use client'

import React, { useState } from 'react'
import { motion } from 'framer-motion'
import { Calendar as CalendarIcon, Clock, AlertCircle, TrendingUp, TrendingDown } from 'lucide-react'
import { MainLayout } from '@/components/layout/MainLayout'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

const upcomingReleases = [
  {
    date: '2024-01-15',
    time: '8:30 AM ET',
    indicator: 'CPI (Consumer Price Index)',
    category: 'inflation',
    importance: 'high',
    previous: '3.1%',
    forecast: '3.2%',
  },
  {
    date: '2024-01-17',
    time: '8:30 AM ET',
    indicator: 'Retail Sales',
    category: 'consumer',
    importance: 'medium',
    previous: '0.3%',
    forecast: '0.4%',
  },
  {
    date: '2024-01-18',
    time: '8:30 AM ET',
    indicator: 'Initial Jobless Claims',
    category: 'labor',
    importance: 'medium',
    previous: '212K',
    forecast: '210K',
  },
  {
    date: '2024-01-19',
    time: '10:00 AM ET',
    indicator: 'Housing Starts',
    category: 'housing',
    importance: 'medium',
    previous: '1.56M',
    forecast: '1.52M',
  },
  {
    date: '2024-01-24',
    time: '2:00 PM ET',
    indicator: 'FOMC Meeting Minutes',
    category: 'monetary',
    importance: 'high',
    previous: '-',
    forecast: '-',
  },
  {
    date: '2024-01-25',
    time: '8:30 AM ET',
    indicator: 'GDP (Q4 Advance)',
    category: 'gdp',
    importance: 'high',
    previous: '4.9%',
    forecast: '2.0%',
  },
  {
    date: '2024-01-26',
    time: '8:30 AM ET',
    indicator: 'Core PCE Price Index',
    category: 'inflation',
    importance: 'high',
    previous: '3.2%',
    forecast: '3.1%',
  },
  {
    date: '2024-01-29',
    time: '10:00 AM ET',
    indicator: 'Pending Home Sales',
    category: 'housing',
    importance: 'low',
    previous: '0.0%',
    forecast: '0.5%',
  },
]

const recentReleases = [
  {
    date: '2024-01-12',
    indicator: 'PPI (Producer Price Index)',
    actual: '0.1%',
    forecast: '0.2%',
    previous: '0.0%',
    impact: 'positive',
  },
  {
    date: '2024-01-11',
    indicator: 'CPI (Consumer Price Index)',
    actual: '3.4%',
    forecast: '3.2%',
    previous: '3.1%',
    impact: 'negative',
  },
  {
    date: '2024-01-10',
    indicator: 'Wholesale Inventories',
    actual: '-0.2%',
    forecast: '-0.1%',
    previous: '-0.1%',
    impact: 'neutral',
  },
  {
    date: '2024-01-09',
    indicator: 'Trade Balance',
    actual: '-$63.2B',
    forecast: '-$65.0B',
    previous: '-$64.2B',
    impact: 'positive',
  },
]

export default function CalendarPage() {
  const [selectedMonth, setSelectedMonth] = useState('January 2024')

  return (
    <MainLayout>
      <div className="container mx-auto px-4 py-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
            <div>
              <h1 className="text-3xl font-bold mb-2">Economic Calendar</h1>
              <p className="text-muted-foreground">
                Track upcoming economic data releases and their impact
              </p>
            </div>
            <select
              value={selectedMonth}
              onChange={(e) => setSelectedMonth(e.target.value)}
              className="rounded-md border px-4 py-2 text-sm"
            >
              <option>January 2024</option>
              <option>February 2024</option>
              <option>March 2024</option>
            </select>
          </div>

          <Tabs defaultValue="upcoming" className="space-y-6">
            <TabsList>
              <TabsTrigger value="upcoming">Upcoming Releases</TabsTrigger>
              <TabsTrigger value="recent">Recent Releases</TabsTrigger>
            </TabsList>

            <TabsContent value="upcoming">
              <div className="grid gap-4">
                {upcomingReleases.map((release, index) => (
                  <motion.div
                    key={release.indicator + release.date}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: index * 0.05 }}
                  >
                    <Card>
                      <CardContent className="p-4">
                        <div className="flex flex-col sm:flex-row sm:items-center gap-4">
                          {/* Date */}
                          <div className="flex items-center gap-3 sm:w-40">
                            <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center">
                              <CalendarIcon className="h-5 w-5 text-primary" />
                            </div>
                            <div>
                              <p className="font-medium">{release.date}</p>
                              <p className="text-xs text-muted-foreground flex items-center gap-1">
                                <Clock className="h-3 w-3" />
                                {release.time}
                              </p>
                            </div>
                          </div>

                          {/* Indicator */}
                          <div className="flex-1">
                            <div className="flex items-center gap-2">
                              <p className="font-medium">{release.indicator}</p>
                              <Badge
                                variant={release.importance === 'high' ? 'default' : 'secondary'}
                              >
                                {release.importance}
                              </Badge>
                            </div>
                            <p className="text-sm text-muted-foreground capitalize">
                              {release.category}
                            </p>
                          </div>

                          {/* Forecast */}
                          <div className="flex gap-6 sm:w-48">
                            <div>
                              <p className="text-xs text-muted-foreground">Previous</p>
                              <p className="font-mono font-medium">{release.previous}</p>
                            </div>
                            <div>
                              <p className="text-xs text-muted-foreground">Forecast</p>
                              <p className="font-mono font-medium">{release.forecast}</p>
                            </div>
                          </div>

                          {/* Alert */}
                          <button className="p-2 rounded-lg hover:bg-muted transition-colors">
                            <AlertCircle className="h-5 w-5 text-muted-foreground" />
                          </button>
                        </div>
                      </CardContent>
                    </Card>
                  </motion.div>
                ))}
              </div>
            </TabsContent>

            <TabsContent value="recent">
              <div className="grid gap-4">
                {recentReleases.map((release, index) => (
                  <motion.div
                    key={release.indicator + release.date}
                    initial={{ opacity: 0, x: -20 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: index * 0.05 }}
                  >
                    <Card>
                      <CardContent className="p-4">
                        <div className="flex flex-col sm:flex-row sm:items-center gap-4">
                          {/* Date */}
                          <div className="sm:w-32">
                            <p className="font-medium">{release.date}</p>
                          </div>

                          {/* Indicator */}
                          <div className="flex-1">
                            <p className="font-medium">{release.indicator}</p>
                          </div>

                          {/* Values */}
                          <div className="flex gap-6">
                            <div>
                              <p className="text-xs text-muted-foreground">Actual</p>
                              <p className="font-mono font-medium">{release.actual}</p>
                            </div>
                            <div>
                              <p className="text-xs text-muted-foreground">Forecast</p>
                              <p className="font-mono font-medium">{release.forecast}</p>
                            </div>
                            <div>
                              <p className="text-xs text-muted-foreground">Previous</p>
                              <p className="font-mono font-medium">{release.previous}</p>
                            </div>
                          </div>

                          {/* Impact */}
                          <div className="flex items-center gap-2">
                            {release.impact === 'positive' && (
                              <>
                                <TrendingUp className="h-4 w-4 text-score-green" />
                                <span className="text-sm text-score-green">Beat</span>
                              </>
                            )}
                            {release.impact === 'negative' && (
                              <>
                                <TrendingDown className="h-4 w-4 text-score-red" />
                                <span className="text-sm text-score-red">Miss</span>
                              </>
                            )}
                            {release.impact === 'neutral' && (
                              <span className="text-sm text-muted-foreground">In-line</span>
                            )}
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  </motion.div>
                ))}
              </div>
            </TabsContent>
          </Tabs>
        </motion.div>
      </div>
    </MainLayout>
  )
}
