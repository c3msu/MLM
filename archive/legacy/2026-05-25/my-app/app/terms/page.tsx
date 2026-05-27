'use client'

import React from 'react'
import { motion } from 'framer-motion'
import { MainLayout } from '@/components/layout/MainLayout'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export default function TermsPage() {
  return (
    <MainLayout>
      <div className="container mx-auto px-4 py-12">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="max-w-3xl mx-auto"
        >
          <h1 className="text-3xl font-bold mb-6">Terms of Service</h1>
          <p className="text-muted-foreground mb-8">
            Last updated: January 1, 2024
          </p>

          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>1. Acceptance of Terms</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-muted-foreground">
                  By accessing and using The Dial, you accept and agree to be bound by the terms 
                  and provisions of this agreement. If you do not agree to abide by the above, 
                  please do not use this service.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>2. Description of Service</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-muted-foreground">
                  The Dial provides users with access to macroeconomic data, analysis, and scoring 
                  through our web-based dashboard. The service includes real-time and historical 
                  economic indicator data sourced from third-party providers.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>3. User Accounts</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-muted-foreground">
                  To access certain features of the service, you must register for an account. 
                  You agree to provide accurate, current, and complete information during the 
                  registration process and to update such information to keep it accurate, 
                  current, and complete.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>4. Subscription and Payments</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-muted-foreground">
                  Some features of the service require a paid subscription. By subscribing, you 
                  agree to pay all fees associated with your selected plan. Subscriptions will 
                  automatically renew unless cancelled before the renewal date.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>5. Data Disclaimer</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-muted-foreground">
                  The economic data provided through The Dial is sourced from third parties and 
                  is for informational purposes only. We make no warranties about the accuracy, 
                  reliability, or timeliness of the data. Users should not rely solely on this 
                  information for making financial decisions.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>6. Limitation of Liability</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-muted-foreground">
                  The Dial and its affiliates shall not be liable for any indirect, incidental, 
                  special, consequential, or punitive damages resulting from your use of or 
                  inability to use the service.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>7. Changes to Terms</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-muted-foreground">
                  We reserve the right to modify these terms at any time. We will notify users 
                  of any material changes via email or through the service. Continued use of 
                  the service after changes constitutes acceptance of the new terms.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>8. Contact</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-muted-foreground">
                  If you have any questions about these Terms of Service, please contact us at{' '}
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
