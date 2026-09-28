/**
 * Display formatting.
 *
 * Money arrives from the API as a decimal string. It is parsed here, at the
 * display boundary only — no arithmetic on money happens in the frontend, which
 * is the backend's job.
 */

import type { Money } from '@/types'

const INR = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
})

const INR_PRECISE = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const currencyCache = new Map<string, Intl.NumberFormat>()

function formatter(currency: string, precise: boolean): Intl.NumberFormat {
  if (currency === 'INR') return precise ? INR_PRECISE : INR
  const key = `${currency}:${precise}`
  let cached = currencyCache.get(key)
  if (!cached) {
    cached = new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency,
      minimumFractionDigits: precise ? 2 : 0,
      maximumFractionDigits: precise ? 2 : 0,
    })
    currencyCache.set(key, cached)
  }
  return cached
}

export function toNumber(value: Money | number | null | undefined): number {
  if (value === null || value === undefined) return 0
  const parsed = typeof value === 'number' ? value : Number.parseFloat(value)
  return Number.isFinite(parsed) ? parsed : 0
}

export function formatMoney(
  value: Money | number | null | undefined,
  options: { currency?: string; precise?: boolean; signed?: boolean } = {},
): string {
  const { currency = 'INR', precise = false, signed = false } = options
  const amount = toNumber(value)
  const text = formatter(currency, precise).format(Math.abs(amount))
  if (signed && amount !== 0) return `${amount > 0 ? '+' : '−'}${text}`
  return amount < 0 ? `−${text}` : text
}

/** Compact form for chart axes: ₹1.2L, ₹45K. Uses Indian units. */
export function formatCompact(value: Money | number | null | undefined): string {
  const amount = toNumber(value)
  const absolute = Math.abs(amount)
  const sign = amount < 0 ? '−' : ''

  if (absolute >= 10_000_000) return `${sign}₹${(absolute / 10_000_000).toFixed(1)}Cr`
  if (absolute >= 100_000) return `${sign}₹${(absolute / 100_000).toFixed(1)}L`
  if (absolute >= 1_000) return `${sign}₹${(absolute / 1_000).toFixed(absolute >= 10_000 ? 0 : 1)}K`
  return `${sign}₹${Math.round(absolute)}`
}

export function formatPercent(
  value: number | null | undefined,
  options: { decimals?: number; signed?: boolean } = {},
): string {
  const { decimals = 1, signed = false } = options
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  const text = `${Math.abs(value).toFixed(decimals)}%`
  if (signed && value !== 0) return `${value > 0 ? '+' : '−'}${text}`
  return value < 0 ? `−${text}` : text
}

export function formatDate(
  value: string | Date | null | undefined,
  style: 'short' | 'medium' | 'long' | 'month' = 'medium',
): string {
  if (!value) return '—'
  const date = typeof value === 'string' ? new Date(value) : value
  if (Number.isNaN(date.getTime())) return '—'

  const options: Intl.DateTimeFormatOptions =
    style === 'short'
      ? { day: '2-digit', month: 'short' }
      : style === 'long'
        ? { day: 'numeric', month: 'long', year: 'numeric' }
        : style === 'month'
          ? { month: 'long', year: 'numeric' }
          : { day: '2-digit', month: 'short', year: 'numeric' }

  return new Intl.DateTimeFormat('en-IN', options).format(date)
}

export function formatRelative(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'

  const diffMs = Date.now() - date.getTime()
  const diffDays = Math.floor(diffMs / 86_400_000)

  if (diffDays === 0) return 'Today'
  if (diffDays === 1) return 'Yesterday'
  if (diffDays === -1) return 'Tomorrow'
  if (diffDays > 1 && diffDays < 7) return `${diffDays} days ago`
  if (diffDays < -1 && diffDays > -7) return `in ${Math.abs(diffDays)} days`
  return formatDate(date, 'medium')
}

/** "2026-09-28" — the format every date input and API field expects. */
export function toISODate(date: Date = new Date()): string {
  const year = date.getFullYear()
  const month = `${date.getMonth() + 1}`.padStart(2, '0')
  const day = `${date.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

/** "2026-09" — the month key budgets are addressed by. */
export function toMonthKey(date: Date = new Date()): string {
  return toISODate(date).slice(0, 7)
}

export function monthLabel(monthKey: string): string {
  const [year, month] = monthKey.split('-').map(Number)
  if (!year || !month) return monthKey
  return formatDate(new Date(year, month - 1, 1), 'month')
}

export function initials(name: string): string {
  return name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? '')
    .join('')
}

export function truncate(text: string, length = 48): string {
  return text.length <= length ? text : `${text.slice(0, length - 1)}…`
}

/** Human-readable file size for the receipt uploader. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
