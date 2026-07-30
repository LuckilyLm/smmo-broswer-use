import { describe, expect, it } from 'vitest'
import { buildReplyPreflightWarnings } from '../pages/CampaignSettings'
import { getStatusLabel } from '../components/ui/StatusBadge'

describe('campaign demo workflow helpers', () => {
  it('warns when replies are enabled without a send-ready configuration', () => {
    const warnings = buildReplyPreflightWarnings({
      replyMode: 'manual',
      targetPolicy: 'discovery_only',
      selectedTemplateId: '',
      selectedAccount: {
        connection_status: 'not_connected',
        login_status: 'login_required',
        runtime_status: 'stopped',
      },
      keywordCount: 0,
      enabledRuleCount: 0,
    })

    expect(warnings).toHaveLength(6)
    expect(warnings.join(' ')).toContain('仅发现')
    expect(warnings.join(' ')).toContain('回复模板')
    expect(warnings.join(' ')).toContain('匹配规则')
    expect(warnings.join(' ')).toContain('搜索关键词')
    expect(warnings.join(' ')).toContain('连接并登录')
    expect(warnings.join(' ')).toContain('运行时未运行')
  })

  it('does not show reply preflight warnings while replies are closed', () => {
    expect(buildReplyPreflightWarnings({
      replyMode: 'off',
      targetPolicy: 'discovery_only',
      selectedTemplateId: '',
      keywordCount: 0,
      enabledRuleCount: 0,
    })).toEqual([])
  })

  it('renders known status enums as Chinese labels', () => {
    expect(getStatusLabel('active')).toBe('运行中')
    expect(getStatusLabel('login_required')).toBe('需要登录')
    expect(getStatusLabel('retry_waiting')).toBe('等待重试')
  })
})
