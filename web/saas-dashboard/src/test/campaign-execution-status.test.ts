import { describe, expect, it } from 'vitest'
import type { Execution } from '../api/executions'
import { campaignStatusLabel, executionStatusLabel, latestExecutionsByCampaign } from '../pages/Campaigns'

function execution(overrides: Partial<Execution>): Execution {
  return {
    id: 'exec-1',
    campaign_id: 'campaign-1',
    status: 'queued',
    total_keywords: 0,
    completed_keywords: 0,
    failed_keywords: 0,
    progress_percent: 0,
    scanned_contents: 0,
    scanned_comments: 0,
    lead_candidates: 0,
    eligible_count: 0,
    selected_count: 0,
    prompt_tokens: 0,
    completion_tokens: 0,
    total_tokens: 0,
    send_disabled: false,
    created_at: '2026-07-29T09:00:00Z',
    ...overrides,
  }
}

describe('campaign execution status presentation', () => {
  it('keeps campaign enabled status labels separate from execution labels', () => {
    expect(campaignStatusLabel('active')).toBe('已启用')
    expect(campaignStatusLabel('paused')).toBe('已暂停')
    expect(executionStatusLabel('queued')).toBe('排队中')
    expect(executionStatusLabel('running')).toBe('执行中')
    expect(executionStatusLabel()).toBe('尚未执行')
  })

  it('selects the newest execution for each campaign regardless of response order', () => {
    const latest = latestExecutionsByCampaign([
      execution({ id: 'new', status: 'running', created_at: '2026-07-29T10:00:00Z' }),
      execution({ id: 'old', status: 'completed', created_at: '2026-07-29T08:00:00Z' }),
      execution({ id: 'other', campaign_id: 'campaign-2', status: 'failed' }),
    ])

    expect(latest['campaign-1']).toMatchObject({ id: 'new', status: 'running' })
    expect(latest['campaign-2']).toMatchObject({ id: 'other', status: 'failed' })
  })
})
