import { act, cleanup, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'
import { WorkspaceProvider } from '../workspace/WorkspaceProvider'
import { useWorkspace } from '../workspace/useWorkspace'
import type { Workspace } from '../workspace/WorkspaceContext'

const { apiGet, apiPost, useAuth } = vi.hoisted(() => ({
  apiGet: vi.fn(),
  apiPost: vi.fn(),
  useAuth: vi.fn(),
}))

vi.mock('../api/client', () => ({ apiGet, apiPost }))
vi.mock('../auth/AuthProvider', () => ({ useAuth }))

const tenant = { id: 'tenant-1', name: 'Primary', slug: 'primary', status: 'active' }
const workspace: Workspace = { ...tenant, created_at: '2026-01-01', updated_at: '2026-01-02' }
let auth: { status: 'authenticated' | 'unauthenticated'; tenant: typeof tenant | null } = { status: 'authenticated', tenant }
let latest: ReturnType<typeof useWorkspace> | null = null
let values: ReturnType<typeof useWorkspace>[] = []

function Probe() {
  latest = useWorkspace()
  values.push(latest)
  return null
}

function Harness({ children }: { children?: ReactNode }) {
  return <WorkspaceProvider><Probe />{children}</WorkspaceProvider>
}

describe('WorkspaceProvider', () => {
  beforeEach(() => {
    auth = { status: 'authenticated', tenant }
    useAuth.mockImplementation(() => auth)
    apiGet.mockResolvedValue([workspace])
    apiPost.mockResolvedValue({})
    latest = null
    values = []
  })

  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('loads tenants and keeps the context value stable across unrelated rerenders', async () => {
    const view = render(<Harness />)

    await waitFor(() => expect(latest?.currentTenant).toEqual(workspace))
    const settledValue = latest
    view.rerender(<Harness><span>unrelated</span></Harness>)

    expect(latest).toBe(settledValue)
    expect(latest?.availableTenants).toEqual([workspace])
    expect(apiGet).toHaveBeenCalledTimes(1)
  })

  it('clears tenants and loading when authentication is lost and ignores an in-flight refresh', async () => {
    const view = render(<Harness />)
    await waitFor(() => expect(latest?.currentTenant).toEqual(workspace))

    let resolveRefresh!: (value: Workspace[]) => void
    apiGet.mockReturnValueOnce(new Promise((resolve) => { resolveRefresh = resolve }))
    await act(async () => { void latest?.refreshTenants() })
    expect(latest?.isLoading).toBe(true)

    auth = { status: 'unauthenticated', tenant: null }
    view.rerender(<Harness />)

    await waitFor(() => {
      expect(latest?.currentTenant).toBeNull()
      expect(latest?.availableTenants).toEqual([])
      expect(latest?.isLoading).toBe(false)
    })

    await act(async () => { resolveRefresh([workspace]) })
    expect(latest?.currentTenant).toBeNull()
    expect(latest?.availableTenants).toEqual([])
    expect(latest?.isLoading).toBe(false)
  })

  it('preserves tenant switching through the switch endpoint', async () => {
    apiPost.mockImplementation(() => new Promise(() => {}))
    render(<Harness />)
    await waitFor(() => expect(latest?.currentTenant).toEqual(workspace))

    act(() => { void latest?.switchTenant('tenant-2') })

    expect(apiPost).toHaveBeenCalledWith('/api/tenants/tenant-2/switch', {})
    expect(latest?.isLoading).toBe(true)
  })
})
