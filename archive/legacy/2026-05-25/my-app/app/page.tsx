'use client'

import { MainLayout } from '@/components/layout/MainLayout'
import { Hero } from '@/components/landing/Hero'
import { Features } from '@/components/landing/Features'
import { Modules } from '@/components/landing/Modules'
import { HowItWorks } from '@/components/landing/HowItWorks'
import { Pricing } from '@/components/landing/Pricing'
import { FAQ } from '@/components/landing/FAQ'

export default function HomePage() {
  return (
    <MainLayout>
      <Hero />
      <Features />
      <Modules />
      <HowItWorks />
      <Pricing />
      <FAQ />
    </MainLayout>
  )
}
