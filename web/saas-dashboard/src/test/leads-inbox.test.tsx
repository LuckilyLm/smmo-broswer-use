import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import LeadsInbox from '../pages/LeadsInbox'

const mocks = vi.hoisted(() => {
  const leads = [
    {
      id: 'lead-a',
      campaign_id: 'campaign-1',
      platform: 'facebook',
      external_id: 'external-a',
      author_name: 'Alpha',
      comment_text: 'Alpha comment',
      final_intent_level: 'high',
      manual_intent_level: null,
      status: 'new',
      matched_search_keywords: [],
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-01T00:00:00Z',
    },
    {
      id: 'lead-b',
      campaign_id: 'campaign-1',
      platform: 'facebook',
      external_id: 'external-b',
      author_name: 'Beta',
      comment_text: 'Beta comment',
      final_intent_level: 'low',
      manual_intent_level: null,
      status: 'new',
      matched_search_keywords: [],
      created_at: '2026-08-02T00:00:00Z',
      updated_at: '2026-08-02T00:00:00Z',
    },
  ]

  return {
    leads,
    useLead: vi.fn((id: string) => ({ data: leads.find((lead) => lead.id === id), isLoading: false, error: null })),
  }
})

vi.mock('../api/leads', () => ({
  useLeads: (filters: { intent_level?: string }) => ({
    data: { items: filters.intent_level === 'high' ? mocks.leads.slice(0, 1) : mocks.leads },
    isLoading: false,
    error: null,
  }),
  useLead: mocks.useLead,
  useMarkLeadContacted: () => ({ isPending: false, mutate: vi.fn() }),
  useMarkLeadInvalid: () => ({ isPending: false, mutate: vi.fn() }),
}))

afterEach(() => {
  cleanup()
  mocks.useLead.mockClear()
})

describe('LeadsInbox selection', () => {
  it('derives the first visible lead without copying it into explicit selection state', () => {
    render(<LeadsInbox />)

    expect(screen.getByRole('heading', { name: 'Alpha' })).toBeInTheDocument()
    expect(mocks.useLead).toHaveBeenLastCalledWith('lead-a')
    expect(screen.getByRole('button', { name: /Alpha Alpha comment/ })).toHaveStyle({ background: 'var(--accent)' })
  })

  it('falls back while an explicit selection is hidden and restores it when visible again', () => {
    render(<LeadsInbox />)

    fireEvent.click(screen.getByRole('button', { name: /Beta Beta comment/ }))
    expect(screen.getByRole('heading', { name: 'Beta' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '返回列表' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '高意向' }))
    expect(screen.getByRole('heading', { name: 'Alpha' })).toBeInTheDocument()
    expect(mocks.useLead).toHaveBeenLastCalledWith('lead-a')

    fireEvent.click(screen.getByRole('button', { name: '全部' }))
    expect(screen.getByRole('heading', { name: 'Beta' })).toBeInTheDocument()
    expect(mocks.useLead).toHaveBeenLastCalledWith('lead-b')

    fireEvent.click(screen.getByRole('button', { name: '返回列表' }))
    expect(screen.queryByRole('button', { name: '返回列表' })).not.toBeInTheDocument()
  })
})
