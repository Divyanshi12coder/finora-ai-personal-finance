import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** Merge Tailwind classes, with later classes winning conflicts. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Chart and status colours, resolved from the brand palette. */
export const chartColors = {
  income: '#0B1F3A',
  incomeSoft: '#2C5282',
  expense: '#E63946',
  expenseSoft: '#F4766E',
  savings: '#132B4F',
  forecast: '#5C7C9A',
  neutral: '#64748B',
  grid: '#E2E8F0',
} as const

export const chartColorsDark = {
  income: '#60A5FA',
  incomeSoft: '#93C5FD',
  expense: '#FF4D5A',
  expenseSoft: '#FF8A94',
  savings: '#3B69A8',
  forecast: '#7C9BC4',
  neutral: '#94A3B8',
  grid: '#203A60',
} as const

/**
 * Budget utilisation colour: navy while healthy, shifting to red as the limit
 * approaches. Matches the brand rule that red means "expense / warning".
 */
export function utilizationColor(utilization: number): string {
  if (utilization >= 100) return '#E63946'
  if (utilization >= 90) return '#F4766E'
  if (utilization >= 75) return '#B4436C'
  return '#0B1F3A'
}

export function statusTone(status: string) {
  switch (status) {
    case 'exceeded':
    case 'critical':
      return { bg: 'bg-accent-soft', text: 'text-accent-strong', ring: 'ring-accent/30' }
    case 'at_risk':
    case 'warning':
      return { bg: 'bg-warning-soft', text: 'text-warning', ring: 'ring-warning/30' }
    case 'watch':
      return { bg: 'bg-navy-tint', text: 'text-navy', ring: 'ring-navy/20' }
    case 'positive':
      return { bg: 'bg-positive-soft', text: 'text-positive', ring: 'ring-positive/30' }
    default:
      return { bg: 'bg-navy-tint', text: 'text-navy', ring: 'ring-navy/20' }
  }
}

export function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** Stable pseudo-random colour for an uncategorised label. */
export function hashColor(text: string): string {
  const palette = ['#0B1F3A', '#132B4F', '#2C5282', '#3A7CA5', '#5C7C9A', '#64748B']
  let hash = 0
  for (let i = 0; i < text.length; i += 1) hash = (hash * 31 + text.charCodeAt(i)) | 0
  return palette[Math.abs(hash) % palette.length]
}
