import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

const pages = ['Settings', 'Dashboard', 'Keywords', 'MatchingRules', 'ReplyTemplates', 'AuditLog', 'NotificationCenter', 'SystemAdmin']
const source = (page: string) => readFileSync(join(process.cwd(), 'src', 'pages', `${page}.tsx`), 'utf8')
const campaignSettingsSections = readFileSync(join(process.cwd(), 'src', 'pages', 'campaign-settings', 'CampaignSettingsSections.tsx'), 'utf8')

describe('accessibility and correctness regressions', () => {
  it('keeps icon-only and navigation controls labelled and typed', () => {
    expect(source('Dashboard')).toContain('aria-label="仪表盘时间范围"')
    expect(source('Keywords')).toContain('aria-label="搜索关键词"')
    expect(source('MatchingRules')).toContain('aria-label="搜索规则"')
    expect(source('ReplyTemplates')).toContain('aria-label="搜索模板"')
    expect(source('AuditLog')).toContain('aria-label="搜索审计日志"')
    expect(source('NotificationCenter')).toContain('<button type="button"')
    expect(source('SystemAdmin')).toContain('<button type="button"')
  })

  it('associates field labels and guards numeric input parsing', () => {
    expect(source('MatchingRules')).toContain('<label htmlFor={id}')
    expect(source('ReplyTemplates')).toContain('<label htmlFor={id}')
    expect(source('Settings')).toContain('event.target.valueAsNumber')
    expect(source('Settings')).toContain('if (!Number.isNaN(value))')
  })

  it('uses semantic audit-log actions and labelled switches', () => {
    expect(source('AuditLog')).toContain('<button type="button"')
    expect(source('AuditLog')).toContain('aria-label="关闭审计详情"')
    expect(source('Keywords')).toContain('role="switch"')
    expect(source('Keywords')).toContain('aria-checked={checked}')
    expect(source('Keywords')).toContain('aria-label={label}')
    expect(campaignSettingsSections).toContain('aria-label="启用 AI 增强回复"')
  })
})
