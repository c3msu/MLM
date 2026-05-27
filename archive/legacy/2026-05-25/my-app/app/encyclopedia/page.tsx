'use client'

import React, { useState } from 'react'
import { motion } from 'framer-motion'
import { Search, BookOpen, ChevronRight, BarChart3, TrendingUp, Users, DollarSign } from 'lucide-react'
import { MainLayout } from '@/components/layout/MainLayout'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

const economicTerms = [
  {
    term: 'GDP (Gross Domestic Product)',
    category: 'economic-indicators',
    definition: 'The total monetary value of all finished goods and services produced within a country\'s borders in a specific time period.',
    importance: 'high',
    related: ['Real GDP', 'Nominal GDP', 'GDP Growth Rate'],
  },
  {
    term: 'Unemployment Rate',
    category: 'labor-market',
    definition: 'The percentage of the total labor force that is unemployed but actively seeking employment and willing to work.',
    importance: 'high',
    related: ['Labor Force Participation', 'Nonfarm Payrolls', 'Jobless Claims'],
  },
  {
    term: 'Consumer Price Index (CPI)',
    category: 'inflation',
    definition: 'A measure that examines the weighted average of prices of a basket of consumer goods and services, such as transportation, food, and medical care.',
    importance: 'high',
    related: ['Core CPI', 'PPI', 'Inflation Rate'],
  },
  {
    term: 'Federal Funds Rate',
    category: 'interest-rates',
    definition: 'The interest rate at which depository institutions trade federal funds with each other overnight.',
    importance: 'high',
    related: ['Discount Rate', 'Treasury Yields', 'Prime Rate'],
  },
  {
    term: 'Housing Starts',
    category: 'housing',
    definition: 'The number of new residential construction projects that have begun during any particular month.',
    importance: 'medium',
    related: ['Building Permits', 'Home Sales', 'Construction Spending'],
  },
  {
    term: 'Consumer Confidence Index',
    category: 'consumer',
    definition: 'A survey by the Conference Board that measures how optimistic or pessimistic consumers are regarding their expected financial situation.',
    importance: 'medium',
    related: ['Consumer Sentiment', 'Retail Sales', 'Personal Spending'],
  },
  {
    term: 'Industrial Production',
    category: 'manufacturing',
    definition: 'A measure of output of the industrial sector of the economy, including manufacturing, mining, and utilities.',
    importance: 'medium',
    related: ['Capacity Utilization', 'PMI', 'Factory Orders'],
  },
  {
    term: 'Trade Balance',
    category: 'trade',
    definition: 'The difference between the value of a country\'s exports and imports for a given period.',
    importance: 'medium',
    related: ['Exports', 'Imports', 'Current Account'],
  },
]

const categories = [
  { id: 'all', label: 'All Terms' },
  { id: 'economic-indicators', label: 'Economic Indicators' },
  { id: 'labor-market', label: 'Labor Market' },
  { id: 'inflation', label: 'Inflation' },
  { id: 'interest-rates', label: 'Interest Rates' },
  { id: 'housing', label: 'Housing' },
  { id: 'consumer', label: 'Consumer' },
  { id: 'manufacturing', label: 'Manufacturing' },
  { id: 'trade', label: 'Trade' },
]

export default function EncyclopediaPage() {
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedCategory, setSelectedCategory] = useState('all')

  const filteredTerms = economicTerms.filter((term) => {
    const matchesSearch = term.term.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         term.definition.toLowerCase().includes(searchQuery.toLowerCase())
    const matchesCategory = selectedCategory === 'all' || term.category === selectedCategory
    return matchesSearch && matchesCategory
  })

  return (
    <MainLayout>
      <div className="container mx-auto px-4 py-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          {/* Header */}
          <div className="text-center mb-12">
            <h1 className="text-3xl sm:text-4xl font-bold mb-4">
              Economic Encyclopedia
            </h1>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Learn about key economic indicators and terms used in The Dial dashboard.
            </p>
          </div>

          {/* Search */}
          <div className="max-w-xl mx-auto mb-8">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
              <Input
                placeholder="Search economic terms..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10 h-12"
              />
            </div>
          </div>

          {/* Categories */}
          <div className="flex flex-wrap justify-center gap-2 mb-8">
            {categories.map((category) => (
              <button
                key={category.id}
                onClick={() => setSelectedCategory(category.id)}
                className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
                  selectedCategory === category.id
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted text-muted-foreground hover:bg-muted/80'
                }`}
              >
                {category.label}
              </button>
            ))}
          </div>

          {/* Terms Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {filteredTerms.map((term, index) => (
              <motion.div
                key={term.term}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.05 }}
              >
                <Card className="h-full hover:shadow-lg transition-shadow">
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between">
                      <CardTitle className="text-lg">{term.term}</CardTitle>
                      <Badge
                        variant={term.importance === 'high' ? 'default' : 'secondary'}
                      >
                        {term.importance}
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <p className="text-muted-foreground mb-4">{term.definition}</p>
                    <div className="flex flex-wrap gap-2">
                      {term.related.map((related) => (
                        <span
                          key={related}
                          className="text-xs px-2 py-1 rounded-full bg-muted text-muted-foreground"
                        >
                          {related}
                        </span>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              </motion.div>
            ))}
          </div>

          {filteredTerms.length === 0 && (
            <div className="text-center py-12">
              <BookOpen className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
              <p className="text-muted-foreground">No terms found matching your search.</p>
            </div>
          )}
        </motion.div>
      </div>
    </MainLayout>
  )
}
