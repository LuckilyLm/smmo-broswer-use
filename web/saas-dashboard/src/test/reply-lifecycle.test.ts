import { describe, expect, it, vi } from 'vitest'
import { QueryClient } from '@tanstack/react-query'

import { canApproveReplyPlan, invalidateReplyLifecycleQueries } from '../api/reply-tasks'

describe('reply lifecycle helpers', () => {
  it('prevents approval when a pending plan has no candidates', () => {
    expect(canApproveReplyPlan({ status: 'pending_approval', total_candidates: 0 })).toBe(false)
    expect(canApproveReplyPlan({ status: 'pending_approval', total_candidates: 1 })).toBe(true)
    expect(canApproveReplyPlan({ status: 'approved', total_candidates: 1 })).toBe(false)
  })

  it('invalidates every lifecycle query family after mutations', () => {
    const queryClient = new QueryClient()
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries')

    invalidateReplyLifecycleQueries(queryClient)

    expect(invalidate.mock.calls.map(([options]) => options?.queryKey)).toEqual([
      ['reply-plans'],
      ['reply-candidates'],
      ['reply-records'],
      ['reply-record'],
      ['executions'],
      ['dashboard'],
    ])
  })
})
