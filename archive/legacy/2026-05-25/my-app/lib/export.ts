import jsPDF from 'jspdf'
import html2canvas from 'html2canvas'
import * as XLSX from 'xlsx'
import { ExportOptions } from '@/types/index'
import { ScoreBreakdown } from '@/types/scores'
import { Module } from '@/types/modules'
import { formatDate, formatNumber } from './utils'

// Export dashboard as PDF
export async function exportToPDF(
  elementId: string,
  filename: string = 'the-dial-report'
): Promise<void> {
  const element = document.getElementById(elementId)
  if (!element) {
    throw new Error(`Element with id '${elementId}' not found`)
  }

  try {
    const canvas = await html2canvas(element, {
      scale: 2,
      useCORS: true,
      logging: false,
      backgroundColor: '#ffffff',
    })

    const imgData = canvas.toDataURL('image/png')
    const pdf = new jsPDF({
      orientation: 'portrait',
      unit: 'mm',
      format: 'a4',
    })

    const imgWidth = 210 // A4 width in mm
    const pageHeight = 297 // A4 height in mm
    const imgHeight = (canvas.height * imgWidth) / canvas.width

    let heightLeft = imgHeight
    let position = 0

    // Add first page
    pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight)
    heightLeft -= pageHeight

    // Add additional pages if content overflows
    while (heightLeft > 0) {
      position = heightLeft - imgHeight
      pdf.addPage()
      pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight)
      heightLeft -= pageHeight
    }

    pdf.save(`${filename}-${formatDate(new Date(), 'short')}.pdf`)
  } catch (error) {
    console.error('Error exporting to PDF:', error)
    throw error
  }
}

// Export data to Excel
export function exportToExcel(
  modules: Module[],
  scoreBreakdown: ScoreBreakdown,
  filename: string = 'the-dial-data'
): void {
  const workbook = XLSX.utils.book_new()

  // Overall Score Sheet
  const overallData = [
    ['The Dial - Economic Dashboard Report'],
    ['Generated:', formatDate(new Date(), 'long')],
    [''],
    ['Overall Score', scoreBreakdown.overall],
    ['Status', getStatusText(scoreBreakdown.overall)],
    [''],
    ['Module Breakdown'],
    ['Module', 'Score', 'Weight', 'Contribution', 'Status'],
    ...scoreBreakdown.modules.map(m => [
      m.moduleName,
      m.score,
      m.weight,
      formatNumber(m.weightedContribution),
      m.status,
    ]),
  ]
  const overallSheet = XLSX.utils.aoa_to_sheet(overallData)
  XLSX.utils.book_append_sheet(workbook, overallSheet, 'Overall')

  // Individual Module Sheets
  modules.forEach(module => {
    const moduleData = [
      [`${module.name} - Detailed Analysis`],
      [''],
      ['Score', module.score],
      ['Previous Score', module.previousScore],
      ['Trend', module.trend],
      ['Status', module.status],
      ['Last Updated', formatDate(module.lastUpdated, 'long')],
      [''],
      ['Factors'],
      ['Factor', 'Value', 'Weight', 'Contribution', 'Change %', 'Status'],
      ...module.factors.map(f => [
        f.name,
        formatNumber(f.value),
        f.weight,
        formatNumber(f.contribution),
        formatNumber(f.changePercent),
        f.status,
      ]),
    ]
    const moduleSheet = XLSX.utils.aoa_to_sheet(moduleData)
    XLSX.utils.book_append_sheet(workbook, moduleSheet, module.shortName)
  })

  // Historical Data Sheet
  const historicalData: (string | number)[][] = [['Date', 'Overall Score']]
  modules.forEach(m => historicalData[0].push(m.name))
  
  // Add sample historical rows (in real app, this would come from actual data)
  for (let i = 6; i >= 0; i--) {
    const date = new Date()
    date.setMonth(date.getMonth() - i)
    const row: (string | number)[] = [formatDate(date, 'short'), scoreBreakdown.overall + (Math.random() - 0.5) * 10]
    modules.forEach(() => row.push(Math.round(50 + Math.random() * 50)))
    historicalData.push(row)
  }
  
  const historicalSheet = XLSX.utils.aoa_to_sheet(historicalData)
  XLSX.utils.book_append_sheet(workbook, historicalSheet, 'History')

  XLSX.writeFile(workbook, `${filename}-${formatDate(new Date(), 'short')}.xlsx`)
}

// Export data to CSV
export function exportToCSV(
  modules: Module[],
  scoreBreakdown: ScoreBreakdown,
  filename: string = 'the-dial-data'
): void {
  let csvContent = 'data:text/csv;charset=utf-8,'

  // Header
  csvContent += 'The Dial - Economic Dashboard Report\n'
  csvContent += `Generated: ${formatDate(new Date(), 'long')}\n\n`

  // Overall Score
  csvContent += `Overall Score,${scoreBreakdown.overline}\n`
  csvContent += `Status,${getStatusText(scoreBreakdown.overall)}\n\n`

  // Module Breakdown
  csvContent += 'Module Breakdown\n'
  csvContent += 'Module,Score,Weight,Contribution,Status\n'
  scoreBreakdown.modules.forEach(m => {
    csvContent += `${m.moduleName},${m.score},${m.weight},${formatNumber(m.weightedContribution)},${m.status}\n`
  })

  csvContent += '\n\nFactor Details\n'
  modules.forEach(module => {
    csvContent += `\n${module.name}\n`
    csvContent += 'Factor,Value,Weight,Contribution,Change %,Status\n'
    module.factors.forEach(f => {
      csvContent += `${f.name},${formatNumber(f.value)},${f.weight},${formatNumber(f.contribution)},${formatNumber(f.changePercent)},${f.status}\n`
    })
  })

  const encodedUri = encodeURI(csvContent)
  const link = document.createElement('a')
  link.setAttribute('href', encodedUri)
  link.setAttribute('download', `${filename}-${formatDate(new Date(), 'short')}.csv`)
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

// Helper function to get status text
function getStatusText(score: number): string {
  if (score >= 70) return 'Healthy'
  if (score >= 40) return 'Warning'
  return 'Critical'
}

// Main export function
export async function exportDashboard(
  options: ExportOptions,
  modules: Module[],
  scoreBreakdown: ScoreBreakdown,
  elementId?: string
): Promise<void> {
  const filename = `the-dial-report`

  switch (options.format) {
    case 'pdf':
      if (!elementId) {
        throw new Error('Element ID is required for PDF export')
      }
      await exportToPDF(elementId, filename)
      break
    case 'excel':
      exportToExcel(modules, scoreBreakdown, filename)
      break
    case 'csv':
      exportToCSV(modules, scoreBreakdown, filename)
      break
    default:
      throw new Error(`Unsupported export format: ${options.format}`)
  }
}

// Export chart data
export function exportChartData(
  data: Array<{ date: string; value: number; label?: string }>,
  filename: string = 'chart-data'
): void {
  const csvContent = [
    ['Date', 'Value', 'Label'],
    ...data.map(d => [d.date, d.value.toString(), d.label || '']),
  ]
    .map(row => row.join(','))
    .join('\n')

  const blob = new Blob([csvContent], { type: 'text/csv' })
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${filename}.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}
