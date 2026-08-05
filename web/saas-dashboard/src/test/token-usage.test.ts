import { describe, expect, it } from 'vitest'

import { formatUsageDate, usageDayKey } from '../utils/token-usage'

describe('token usage date helpers', () => {
  it('formats and groups timestamps in the tenant timezone', () => {
    const value = '2026-01-02T00:30:00.000Z'
    expect(formatUsageDate(value, 'America/Los_Angeles')).toContain('01/01')
    expect(usageDayKey(value, 'America/Los_Angeles')).toBe('2026-01-01')
    expect(usageDayKey(value, 'Asia/Shanghai')).toBe('2026-01-02')
  })

  it('preserves invalid and missing values', () => {
    expect(formatUsageDate(undefined, 'UTC')).toBe('—')
    expect(formatUsageDate('not-a-date', 'UTC')).toBe('not-a-date')
    expect(usageDayKey('not-a-date', 'UTC')).toBe('not-a-date')
  })
})
