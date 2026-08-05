import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const pages = ['CampaignSettings.tsx', 'campaign-settings/CampaignSettingsSections.tsx', 'Keywords.tsx', 'MatchingRules.tsx', 'ReplyTemplates.tsx', 'AuditLog.tsx']
const source = (page: string) => readFileSync(resolve(__dirname, `../pages/${page}`), 'utf8')

describe('React Doctor batch 1', () => {
  it.each(pages)('%s gives every button an explicit type', (page) => {
    expect(source(page).match(/<button\b(?![^>]*\btype=)[^>]*>/gs)).toBeNull()
  })

  it.each(pages)('%s avoids transition-all', (page) => {
    expect(source(page)).not.toContain('transition-all')
  })

  it('keeps editable campaign keyword rows stable and payload values unchanged', () => {
    const campaign = source('CampaignSettings.tsx')
    const sections = source('campaign-settings/CampaignSettingsSections.tsx')
    expect(sections).toContain('key={keyword.id}')
    expect(campaign).toContain('keywords.flatMap(({ value }) => {')
  })

  it('uses finite valueAsNumber parsing for matching-rule priority', () => {
    const rules = source('MatchingRules.tsx')
    expect(rules).toContain('e.target.valueAsNumber')
    expect(rules).toContain('Number.isFinite(value)')
  })

  it('provides keyboard semantics for clickable audit rows', () => {
    const audit = source('AuditLog.tsx')
    expect(audit).toContain('tabIndex={0}')
    expect(audit).toContain("event.key === 'Enter' || event.key === ' '")
  })
})
