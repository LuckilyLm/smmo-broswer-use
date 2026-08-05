import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

function source(relativePath: string) {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), 'utf8')
}

describe('lazy chart modules', () => {
  it.each(['../pages/Dashboard.tsx', '../pages/TokenUsage.tsx'])('%s does not eagerly import Recharts', (page) => {
    const pageSource = source(page)

    expect(pageSource).not.toMatch(/from ['"]recharts['"]/)
    expect(pageSource).toContain("lazy(() => import('../components/charts/")
  })

  it('keeps fixed-height loading placeholders for each chart', () => {
    const dashboard = source('../pages/Dashboard.tsx')
    const tokenUsage = source('../pages/TokenUsage.tsx')

    expect(dashboard).toContain('heightClass="h-[180px]"')
    expect(dashboard).toContain('heightClass="h-[120px]"')
    expect(tokenUsage).toContain('className="h-[180px] w-full')
  })

  it('isolates Recharts imports in the lazy chart implementations', () => {
    expect(source('../components/charts/DashboardCharts.tsx')).toMatch(/from ['"]recharts['"]/)
    expect(source('../components/charts/TokenUsageCharts.tsx')).toMatch(/from ['"]recharts['"]/)
  })
})
