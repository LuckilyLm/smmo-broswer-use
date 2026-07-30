import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Members from '../pages/Members'
import { AuthProvider } from '../auth/AuthProvider'

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }))
const emptyPage = { items: [], limit: 50, offset: 0, total: 0 }

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}><AuthProvider><Members /></AuthProvider></QueryClientProvider>)
}

describe('members page', () => {
  beforeEach(() => {
    vi.stubGlobal('crypto', { randomUUID: () => 'request-id' })
  })
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('loads real members and invitations and creates invitations through the invitation endpoint', async () => {
    const calls: Array<[string, RequestInit | undefined]> = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input)
      calls.push([path, init])
      if (path.endsWith('/api/auth/session')) return json({ user: { id: 'u-owner', email: 'owner@test.com' }, tenant: { id: 't1', name: 'Test', slug: 'test', status: 'active' }, role: 'owner', permissions: [] })
      if (path.endsWith('/api/tenant/members')) return json({ items: [{ id: 'm1', user_id: 'u2', email: 'alice@test.com', display_name: 'Alice', role: 'member', status: 'active', created_at: '2026-07-01T00:00:00Z' }], limit: 50, offset: 0, total: 1 })
      if (path.endsWith('/api/tenant/invitations') && init?.method === 'POST') return json({ id: 'i2', email: 'new@test.com', role: 'member', status: 'pending', expires_at: '2026-08-01T00:00:00Z' })
      if (path.endsWith('/api/tenant/invitations')) return json({ items: [{ id: 'i1', email: 'pending@test.com', role: 'viewer', status: 'pending', created_at: '2026-07-20T00:00:00Z', expires_at: '2026-08-01T00:00:00Z' }], limit: 50, offset: 0, total: 1 })
      return json({})
    }))

    renderPage()
    expect(await screen.findAllByText('Alice')).not.toHaveLength(0)
    expect(screen.getByText('pending@test.com')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '邀请成员' }))
    fireEvent.change(screen.getByPlaceholderText('member@company.com'), { target: { value: 'new@test.com' } })
    fireEvent.click(screen.getByRole('button', { name: /发送邀请/ }))

    await waitFor(() => expect(calls.some(([path, init]) => path.endsWith('/api/tenant/invitations') && init?.method === 'POST')).toBe(true))
    expect(calls.some(([path, init]) => path.endsWith('/api/tenant/members') && init?.method === 'POST')).toBe(false)
  })

  it('hides management actions for a viewer and shows the successful empty state', async () => {
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL) => {
      const path = String(input)
      if (path.endsWith('/api/auth/session')) return json({ user: { id: 'u-viewer', email: 'viewer@test.com' }, tenant: { id: 't1', name: 'Test', slug: 'test', status: 'active' }, role: 'viewer', permissions: [] })
      return json(emptyPage)
    }))
    renderPage()
    expect(await screen.findByText('暂无成员')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '邀请成员' })).not.toBeInTheDocument()
  })

  it('supports role update, remove, resend, and revoke using backend endpoints', async () => {
    const calls: Array<[string, RequestInit | undefined]> = []
    vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input); calls.push([path, init])
      if (path.endsWith('/api/auth/session')) return json({ user: { id: 'u-owner', email: 'owner@test.com' }, tenant: { id: 't1', name: 'Test', slug: 'test', status: 'active' }, role: 'owner', permissions: [] })
      if (path.endsWith('/api/tenant/members')) return json({ items: [{ id: 'm1', user_id: 'u2', email: 'alice@test.com', display_name: 'Alice', role: 'member', status: 'active', created_at: '2026-07-01T00:00:00Z' }], limit: 50, offset: 0, total: 1 })
      if (path.endsWith('/api/tenant/invitations')) return json({ items: [{ id: 'i1', email: 'pending@test.com', role: 'viewer', status: 'pending', created_at: '2026-07-20T00:00:00Z', expires_at: '2026-08-01T00:00:00Z' }], limit: 50, offset: 0, total: 1 })
      return init?.method === 'DELETE' ? Promise.resolve(new Response(null, { status: 204 })) : json({})
    }))
    renderPage()
    const roleSelect = (await screen.findAllByRole('combobox', { name: '更改 Alice 的角色' }))[0]
    fireEvent.change(roleSelect, { target: { value: 'viewer' } })
    fireEvent.click(screen.getByRole('button', { name: '重发 pending@test.com 的邀请' }))
    await waitFor(() => expect(calls.some(([path]) => path.endsWith('/api/tenant/invitations/i1/resend'))).toBe(true))
    fireEvent.click(screen.getByRole('button', { name: '撤销 pending@test.com 的邀请' }))
    fireEvent.click((await screen.findAllByRole('button', { name: '移除 Alice' }))[0])
    fireEvent.click(screen.getByRole('button', { name: '移除' }))

    await waitFor(() => {
      expect(calls.some(([path, init]) => path.endsWith('/api/tenant/members/m1') && init?.method === 'PATCH')).toBe(true)
      expect(calls.some(([path, init]) => path.endsWith('/api/tenant/invitations/i1') && init?.method === 'DELETE')).toBe(true)
      expect(calls.some(([path, init]) => path.endsWith('/api/tenant/members/m1') && init?.method === 'DELETE')).toBe(true)
    })
  })
})
