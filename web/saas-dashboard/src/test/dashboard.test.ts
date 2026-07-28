import { describe, expect, it } from 'vitest'
import { normalizeDashboardData } from '../api/dashboard'

describe('normalizeDashboardData', () => {
  it('keeps successful empty responses empty without mock fallbacks', () => {
    const result = normalizeDashboardData({
      active_campaigns: 0,
      lead_trend: [],
      intent_distribution: [],
      campaign_performance: [],
      recent_executions: [],
      pending_reply_items: [],
      platform_status: [],
    })

    expect(result.active_campaigns).toBe(0)
    expect(result.lead_trend).toEqual([])
    expect(result.intent_distribution).toEqual([])
    expect(result.campaign_performance).toEqual([])
    expect(result.recent_executions).toEqual([])
    expect(result.pending_replies_list).toEqual([])
    expect(result.platform_status).toEqual([])
  })

  it('maps the actual backend dashboard field names', () => {
    const result = normalizeDashboardData({
      connected_platform_accounts: 2,
      failed_tasks_today: 3,
      tokens_today: 120,
      tokens_this_month: 500,
      lead_trend: [{ date: '2026-07-27', leads: 4, comments_scanned: 18 }],
      pending_reply_items: [{ id: 'reply-1', author_name: 'Alice', comment_text: 'Hello', matched_rule_name: 'Pricing', rendered_reply_text: 'Hi', campaign_id: 'campaign-1234', created_at: '2026-07-27T10:00:00Z' }],
      recent_executions: [{ id: 'exec-1', campaign_id: 'campaign-1234', status: 'completed', scanned_comments: 20, lead_candidates: 2 }],
      platform_status: [{ account_id: 'acc-1', platform: 'facebook', display_name: 'Facebook Main', connection_status: 'connected', login_status: 'logged_in', runtime_status: 'running' }],
    })

    expect(result.connected_accounts).toBe(2)
    expect(result.failed_tasks_today).toBe(3)
    expect(result.lead_trend).toEqual([{ day: '2026-07-27', leads: 4, scanned: 18 }])
    expect(result.pending_replies_list[0]).toMatchObject({ id: 'reply-1', author: 'Alice', comment: 'Hello' })
    expect(result.recent_executions[0]).toMatchObject({ id: 'exec-1', comments: 20, leads: 2 })
    expect(result.platform_status[0]).toMatchObject({ displayName: 'Facebook Main', loginStatus: 'logged_in' })
    expect(result.tokens_today).toBe(120)
    expect(result.tokens_this_month).toBe(500)
  })
})
