import { describe, expect, it } from 'vitest'

import {
  formatBytes,
  formatCompact,
  formatDate,
  formatMoney,
  formatPercent,
  initials,
  monthLabel,
  toISODate,
  toMonthKey,
  toNumber,
  truncate,
} from './format'

describe('toNumber', () => {
  it('parses decimal strings from the API', () => {
    expect(toNumber('1234.56')).toBe(1234.56)
    expect(toNumber('0.00')).toBe(0)
  })

  it('returns 0 for null, undefined and rubbish', () => {
    expect(toNumber(null)).toBe(0)
    expect(toNumber(undefined)).toBe(0)
    expect(toNumber('not a number')).toBe(0)
  })
})

describe('formatMoney', () => {
  it('formats INR with Indian digit grouping', () => {
    // 1,23,456 rather than 123,456 — the lakh/crore system.
    expect(formatMoney('123456')).toContain('1,23,456')
  })

  it('omits paise by default and includes them when precise', () => {
    expect(formatMoney('1234.56')).not.toContain('.56')
    expect(formatMoney('1234.56', { precise: true })).toContain('.56')
  })

  it('renders negatives with a minus sign, not parentheses', () => {
    const result = formatMoney('-500')
    expect(result).toContain('−')
    expect(result).not.toContain('(')
  })

  it('adds an explicit plus when signed', () => {
    expect(formatMoney('500', { signed: true })).toContain('+')
  })

  it('handles zero without a sign', () => {
    const result = formatMoney('0', { signed: true })
    expect(result).not.toContain('+')
    expect(result).not.toContain('−')
  })
})

describe('formatCompact', () => {
  it('uses Indian units for large numbers', () => {
    expect(formatCompact(45000)).toBe('₹45K')
    expect(formatCompact(250000)).toBe('₹2.5L')
    expect(formatCompact(15000000)).toBe('₹1.5Cr')
  })

  it('leaves small numbers alone', () => {
    expect(formatCompact(450)).toBe('₹450')
  })

  it('handles negatives', () => {
    expect(formatCompact(-45000)).toBe('−₹45K')
  })
})

describe('formatPercent', () => {
  it('formats with a sign when asked', () => {
    expect(formatPercent(24.5, { signed: true })).toBe('+24.5%')
    expect(formatPercent(-12.3, { signed: true })).toBe('−12.3%')
  })

  it('renders an em dash for missing values', () => {
    // "New" vs "0%" matters: a null change means there was no previous period.
    expect(formatPercent(null)).toBe('—')
    expect(formatPercent(undefined)).toBe('—')
  })
})

describe('formatDate', () => {
  it('formats in the requested style', () => {
    // The month abbreviation varies by ICU build ("Sep" vs "Sept"), so
    // assert on the parts that are stable.
    expect(formatDate('2026-09-28', 'short')).toMatch(/^28 Sept?$/)
    expect(formatDate('2026-09-28', 'medium')).toMatch(/^28 Sept? 2026$/)
    expect(formatDate('2026-09-28', 'month')).toMatch(/September 2026/)
  })

  it('handles missing and invalid values', () => {
    expect(formatDate(null)).toBe('—')
    expect(formatDate('nonsense')).toBe('—')
  })
})

describe('date keys', () => {
  it('produces ISO dates without timezone drift', () => {
    expect(toISODate(new Date(2026, 8, 28))).toBe('2026-09-28')
  })

  it('produces month keys the budget API expects', () => {
    expect(toMonthKey(new Date(2026, 8, 28))).toBe('2026-09')
  })

  it('labels a month key readably', () => {
    expect(monthLabel('2026-09')).toMatch(/September 2026/)
  })
})

describe('initials', () => {
  it('takes at most two initials', () => {
    expect(initials('Divyanshi Sharma')).toBe('DS')
    expect(initials('Divyanshi Kumar Sharma')).toBe('DK')
    expect(initials('Divyanshi')).toBe('D')
  })
})

describe('truncate', () => {
  it('only truncates when needed', () => {
    expect(truncate('short', 10)).toBe('short')
    expect(truncate('a'.repeat(20), 10)).toHaveLength(10)
  })
})

describe('formatBytes', () => {
  it('scales the unit', () => {
    expect(formatBytes(500)).toBe('500 B')
    expect(formatBytes(2048)).toBe('2 KB')
    expect(formatBytes(3 * 1024 * 1024)).toBe('3.0 MB')
  })
})
