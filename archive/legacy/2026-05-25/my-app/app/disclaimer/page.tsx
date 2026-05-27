'use client'

import React from 'react'
import { motion } from 'framer-motion'
import { AlertTriangle } from 'lucide-react'
import { MainLayout } from '@/components/layout/MainLayout'
import { Card, CardContent } from '@/components/ui/card'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'

export default function DisclaimerPage() {
  return (
    <MainLayout>
      <div className="container mx-auto px-4 py-12">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="max-w-3xl mx-auto"
        >
          <h1 className="text-3xl font-bold mb-6">Disclaimer</h1>
          <p className="text-muted-foreground mb-8">
            Last updated: January 1, 2024
          </p>

          <Alert className="mb-8 border-score-yellow bg-score-yellow/10">
            <AlertTriangle className="h-5 w-5 text-score-yellow" />
            <AlertTitle className="text-score-yellow">Important Notice</AlertTitle>
            <AlertDescription className="text-score-yellow/80">
              Please read this disclaimer carefully before using The Dial. By using our 
              service, you acknowledge and agree to the terms outlined below.
            </AlertDescription>
          </Alert>

          <div className="space-y-6">
            <Card>
              <CardContent className="p-6">
                <h2 className="text-xl font-semibold mb-4">Not Financial Advice</h2>
                <p className="text-muted-foreground">
                  The information provided on The Dial is for informational and educational 
                  purposes only. It should not be construed as financial, investment, legal, 
                  or tax advice. We strongly recommend consulting with qualified professionals 
                  before making any financial decisions.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-6">
                <h2 className="text-xl font-semibold mb-4">Data Accuracy</h2>
                <p className="text-muted-foreground">
                  While we strive to provide accurate and up-to-date information, we make no 
                  representations or warranties of any kind, express or implied, about the 
                  completeness, accuracy, reliability, suitability, or availability of the 
                  data presented. Economic data is subject to revision and may change over time.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-6">
                <h2 className="text-xl font-semibold mb-4">Third-Party Data Sources</h2>
                <p className="text-muted-foreground">
                  The Dial sources economic data from third-party providers, including the 
                  Federal Reserve Economic Data (FRED). We are not responsible for the accuracy, 
                  timeliness, or completeness of data provided by these third parties.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-6">
                <h2 className="text-xl font-semibold mb-4">Scoring Methodology</h2>
                <p className="text-muted-foreground">
                  The economic health scores provided by The Dial are based on our proprietary 
                  algorithm and methodology. These scores represent our interpretation of economic 
                  conditions and should not be considered definitive assessments. Different 
                  methodologies may yield different results.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-6">
                <h2 className="text-xl font-semibold mb-4">Past Performance</h2>
                <p className="text-muted-foreground">
                  Past economic performance and trends shown on The Dial do not guarantee future 
                  results. Economic conditions can change rapidly and unpredictably.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-6">
                <h2 className="text-xl font-semibold mb-4">Risk Acknowledgment</h2>
                <p className="text-muted-foreground">
                  All investments and financial decisions involve risk. Users of The Dial 
                  acknowledge that they are solely responsible for any decisions made based 
                  on information obtained through our service.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-6">
                <h2 className="text-xl font-semibold mb-4">Service Availability</h2>
                <p className="text-muted-foreground">
                  We do not guarantee that our service will be available at all times or that 
                  access will be uninterrupted. We reserve the right to modify, suspend, or 
                  discontinue any aspect of the service at any time.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="p-6">
                <h2 className="text-xl font-semibold mb-4">Contact</h2>
                <p className="text-muted-foreground">
                  If you have any questions about this disclaimer, please contact us at{' '}
                  <a href="mailto:legal@thedial.com" className="text-primary hover:underline">
                    legal@thedial.com
                  </a>
                </p>
              </CardContent>
            </Card>
          </div>
        </motion.div>
      </div>
    </MainLayout>
  )
}

// Need to import Alert components
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
