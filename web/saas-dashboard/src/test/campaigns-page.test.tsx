import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Campaigns from '../pages/Campaigns'

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }))

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<MemoryRouter><QueryClientProvider client={client}><Campaigns /></QueryClientProvider></MemoryRouter>)
}

describe('campaigns page', () => {
  beforeEach(() => {
    vi.stubGlobal('crypto', { randomUUID: () => 'request-id' })
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      if (path.endsWith('/api/campaigns/camp-1')) {
        return json({
          campaign: {
            id: 'camp-1',
            name: 'Solar Camping Lantern Supplier Smoke',
            platform: 'Facebook',
            platform_account_id: 'plat-1',
            platform_account_name: 'Facebook Acceptance Account',
            status: 'active',
            target_policy: 'discovery_only',
            max_contents: 2,
            max_comments: 30,
            min_confidence: 0.75,
            max_leads: 5,
            daily_limit: 5,
            llm_enabled: true,
            lead_detection_mode: 'rules_with_llm',
            reply_mode: 'manual_approval',
            reply_daily_limit: 30,
            reply_per_minute_limit: 1,
            reply_per_hour_limit: 10,
            reply_min_interval_seconds: 60,
            content_language: 'any',
            keyword_count: 1,
            lead_count: 2,
            pending_reply_count: 1,
            last_execution_at: '2026-07-30T03:58:14Z',
            created_at: '2026-07-30T03:57:35Z',
            updated_at: '2026-07-30T03:57:35Z',
          },
          keywords: [{ id: 'kw-1', keyword: 'solar camping lantern supplier' }],
        })
      }
      if (path.endsWith('/api/campaigns')) {
        return json([
          {
            id: 'camp-1',
            name: 'Solar Camping Lantern Supplier Smoke',
            platform: 'Facebook',
            platform_account_id: 'plat-1',
            platform_account_name: 'Facebook Acceptance Account',
            status: 'active',
            target_policy: 'discovery_only',
            max_contents: 2,
            max_comments: 30,
            min_confidence: 0.75,
            max_leads: 5,
            daily_limit: 5,
            llm_enabled: true,
            lead_detection_mode: 'rules_with_llm',
            reply_mode: 'manual_approval',
            reply_daily_limit: 30,
            reply_per_minute_limit: 1,
            reply_per_hour_limit: 10,
            reply_min_interval_seconds: 60,
            content_language: 'any',
            keyword_count: 1,
            lead_count: 2,
            pending_reply_count: 1,
            last_execution_at: '2026-07-30T03:58:14Z',
            created_at: '2026-07-30T03:57:35Z',
            updated_at: '2026-07-30T03:57:35Z',
          },
        ])
      }
      if (path.startsWith('/api/executions?')) {
        return json({ items: [{ id: 'exec-1', campaign_id: 'camp-1', status: 'completed', progress_percent: 100, created_at: '2026-07-30T03:58:14Z' }], total: 1, limit: 100, offset: 0 })
      }
      return json({})
    }))
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('keeps the list compact and moves detailed fields into the details modal', async () => {
    renderPage()

    expect(await screen.findAllByText('Solar Camping Lantern Supplier Smoke')).not.toHaveLength(0)
    expect(screen.queryByRole('columnheader', { name: '关键词' })).not.toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: '回复模式' })).not.toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /查看详情 Solar Camping Lantern Supplier Smoke/ }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: /编辑设置 Solar Camping Lantern Supplier Smoke/ }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: /运行一次 Solar Camping Lantern Supplier Smoke/ }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: /暂停活动 Solar Camping Lantern Supplier Smoke/ }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: /删除 Solar Camping Lantern Supplier Smoke/ }).length).toBeGreaterThan(0)

    fireEvent.click(screen.getAllByRole('button', { name: /查看详情 Solar Camping Lantern Supplier Smoke/ })[0])

    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument())
    expect(await screen.findByText('执行配置')).toBeInTheDocument()
    expect(screen.getByText('回复配置')).toBeInTheDocument()
    expect(screen.getByText('仅发现公开线索')).toBeInTheDocument()
    expect(screen.getByText('规则 + 大模型')).toBeInTheDocument()
    expect(screen.getByText('solar camping lantern supplier')).toBeInTheDocument()
  })
})
