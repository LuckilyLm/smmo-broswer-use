export function formatUsageDate(value: string | undefined, timezone: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { timeZone: timezone, month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export function usageDayKey(value: string, timezone: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('en-CA', { timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(date)
}
