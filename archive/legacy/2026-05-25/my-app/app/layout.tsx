import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import { QueryProvider } from '@/components/providers/QueryProvider'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'The Dial - Macroeconomic Dashboard',
  description: 'Track economic health with real-time macroeconomic indicators and intelligent scoring.',
  keywords: ['economy', 'macroeconomic', 'dashboard', 'FRED', 'indicators', 'finance'],
  authors: [{ name: 'The Dial Team' }],
  openGraph: {
    title: 'The Dial - Macroeconomic Dashboard',
    description: 'Track economic health with real-time macroeconomic indicators and intelligent scoring.',
    type: 'website',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        <QueryProvider>
          {children}
        </QueryProvider>
      </body>
    </html>
  )
}
