'use client'

import React from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ChevronDown } from 'lucide-react'
import { ScrollReveal } from '@/components/shared/ScrollReveal'

const faqs = [
  {
    question: 'What is The Dial?',
    answer: 'The Dial is a macroeconomic intelligence dashboard that aggregates key economic indicators into a single, easy-to-understand score. It helps investors, businesses, and policymakers track economic health in real-time.',
  },
  {
    question: 'Where does the data come from?',
    answer: 'All our data comes from FRED (Federal Reserve Economic Data), a trusted source maintained by the Federal Reserve Bank of St. Louis. We source data directly from official government agencies including the Bureau of Labor Statistics, Bureau of Economic Analysis, and the Federal Reserve.',
  },
  {
    question: 'How is the overall score calculated?',
    answer: 'The overall score is calculated using a weighted average of individual module scores. Each module score is derived from percentile rankings of key indicators compared to their historical values. Higher percentiles indicate better economic conditions.',
  },
  {
    question: 'How often is the data updated?',
    answer: 'Data update frequency varies by indicator. Most indicators are updated monthly, while some (like interest rates) update daily. Our dashboard automatically refreshes when new data becomes available.',
  },
  {
    question: 'Can I export the data?',
    answer: 'Yes! Pro and Enterprise users can export data in multiple formats including PDF, Excel, and CSV. Free users can view all data within the dashboard but cannot export.',
  },
  {
    question: 'Is there an API available?',
    answer: 'Yes, Enterprise customers have full access to our REST API, allowing you to integrate economic data directly into your own applications and workflows.',
  },
  {
    question: 'Can I set up custom alerts?',
    answer: 'Absolutely! Pro users can set up to 10 custom alerts, while Enterprise users have unlimited alerts. Get notified when indicators cross thresholds or when significant changes occur.',
  },
  {
    question: 'How do I cancel my subscription?',
    answer: 'You can cancel your subscription at any time from your account settings. Your access will continue until the end of your current billing period.',
  },
]

function FAQItem({ faq, isOpen, onToggle }: { 
  faq: typeof faqs[0]
  isOpen: boolean
  onToggle: () => void 
}) {
  return (
    <div className="border-b last:border-b-0">
      <button
        onClick={onToggle}
        className="flex w-full items-center justify-between py-4 text-left"
      >
        <span className="font-medium pr-4">{faq.question}</span>
        <motion.div
          animate={{ rotate: isOpen ? 180 : 0 }}
          transition={{ duration: 0.2 }}
        >
          <ChevronDown className="h-5 w-5 text-muted-foreground flex-shrink-0" />
        </motion.div>
      </button>
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <p className="pb-4 text-muted-foreground">{faq.answer}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

export function FAQ() {
  const [openIndex, setOpenIndex] = React.useState<number | null>(0)

  return (
    <section className="py-20 bg-muted/30">
      <div className="container mx-auto px-4 sm:px-6 lg:px-8">
        <ScrollReveal>
          <div className="text-center mb-16">
            <h2 className="text-3xl sm:text-4xl font-bold mb-4">
              Frequently Asked Questions
            </h2>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Got questions? We have got answers.
            </p>
          </div>
        </ScrollReveal>

        <div className="max-w-3xl mx-auto">
          <ScrollReveal>
            <div className="bg-card border rounded-lg px-6">
              {faqs.map((faq, index) => (
                <FAQItem
                  key={index}
                  faq={faq}
                  isOpen={openIndex === index}
                  onToggle={() => setOpenIndex(openIndex === index ? null : index)}
                />
              ))}
            </div>
          </ScrollReveal>
        </div>
      </div>
    </section>
  )
}
