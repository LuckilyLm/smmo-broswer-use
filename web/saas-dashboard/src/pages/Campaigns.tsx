import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Edit3, Eye, Pause, Play, Plus, Search, SlidersHorizontal, Trash2 } from 'lucide-react'
import StatusBadge from '../components/ui/StatusBadge'
import { getStatusLabel } from '../components/ui/statusBadgeHelpers'

import ConfirmModal from '../components/ui/ConfirmModal'
import { campaignStatusLabel, executionStatusLabel, latestExecutionsByCampaign } from './campaignHelpers'
import { useCampaign, useCampaigns, useDeleteCampaign, useRunCampaign, useUpdateCampaign } from '../api/campaigns'
import { useExecutions } from '../api/executions'
import CampaignDetailModal, { type VisibleCampaign } from './campaigns/CampaignDetailModal'
import CampaignList from './campaigns/CampaignList'

const platColors: Record<string, string> = {
  Facebook: '#1877f2', Instagram: '#e1306c', TikTok: '#010101', X: '#1da1f2', YouTube: '#ff0000',
}

function formatReplyMode(mode?: string) {
  if (mode === 'automatic') return '自动执行'
  if (mode === 'manual_approval') return '人工审批'
  if (mode === 'disabled') return '已关闭'
  return mode || '—'
}

function targetPolicyLabel(value?: string) {
  if (value === 'discovery_only') return '仅发现公开线索'
  if (value === 'owned_only') return '仅自有内容'
  if (value === 'allowlist') return '允许列表'
  return value || '—'
}

function detectionModeLabel(value?: string) {
  if (value === 'rules_only') return '规则判断'
  if (value === 'rules_with_llm') return '规则 + 大模型'
  return value || '—'
}

function languageLabel(value?: string) {
  if (!value || value === 'any') return '不限'
  if (value === 'zh-CN') return '中文'
  if (value === 'en-US' || value === 'en') return '英文'
  return value
}

function yesNo(value?: boolean) {
  if (value === true) return '启用'
  if (value === false) return '关闭'
  return '—'
}

interface CampaignsProps {
  onNavigate?: (page: string) => void
  onMenuOpen?: () => void
}


export default function Campaigns({ onNavigate }: CampaignsProps) {
  void onNavigate
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: campaigns = [], isLoading, error } = useCampaigns()
  const { data: executionsData } = useExecutions({ limit: 100, offset: 0 })
  const deleteCampaign = useDeleteCampaign()
  const updateCampaign = useUpdateCampaign()
  const runCampaign = useRunCampaign()
  const [startedExecutions, setStartedExecutions] = useState<Record<string, string>>({})
  const terminalExecutionIds = useRef<Set<string>>(null!)
  if (!terminalExecutionIds.current) terminalExecutionIds.current = new Set<string>()
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('全部')
  const [platformFilter, setPlatformFilter] = useState('全部')
  const [modeFilter, setModeFilter] = useState('全部')
  const [detailId, setDetailId] = useState<string | null>(null)
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const [filtersOpen, setFiltersOpen] = useState(false)
  const { data: detail, isLoading: detailLoading, error: detailError } = useCampaign(detailId || '')

  const latestByCampaign = useMemo(() => latestExecutionsByCampaign(executionsData?.items || []), [executionsData?.items])

  useEffect(() => {
    const terminal = new Set(['completed', 'partial', 'failed', 'cancelled'])
    Object.entries(startedExecutions).forEach(([campaignId, executionId]) => {
      const execution = latestByCampaign[campaignId]
      if (execution?.id === executionId && terminal.has(execution.status) && !terminalExecutionIds.current.has(executionId)) {
        terminalExecutionIds.current.add(executionId)
        void Promise.all([
          queryClient.invalidateQueries({ queryKey: ['campaigns'] }),
          queryClient.invalidateQueries({ queryKey: ['dashboard'] }),
          queryClient.invalidateQueries({ queryKey: ['reply-candidates'] }),
          queryClient.invalidateQueries({ queryKey: ['reply-plans'] }),
          queryClient.invalidateQueries({ queryKey: ['reply-records'] }),
        ])
      }
    })
  }, [latestByCampaign, queryClient, startedExecutions])

  const visibleCampaigns: VisibleCampaign[] = campaigns.map((c) => {
    const execution = latestByCampaign[c.id]
    return {
      id: c.id,
      name: c.name,
      platform: c.platform,
      account: c.platform_account_name,
      keywords: c.keywords_count,
      status: c.status,
      replyMode: formatReplyMode(c.reply_mode),
      leads: c.leads_count,
      pending: c.pending_replies,
      lastRun: c.last_run,
      nextRun: '—',
      owner: '—',
      execution,
      executionStatus: execution?.status,
      executionProgress: execution?.progress_percent ?? 0,
    }
  })

  const selectedCampaign = visibleCampaigns.find((campaign) => campaign.id === detailId) || null

  const filtered = visibleCampaigns.filter((c) => {
    if (search && !c.name.toLowerCase().includes(search.toLowerCase())) return false
    if (statusFilter !== '全部' && c.status !== statusFilter) return false
    if (platformFilter !== '全部' && c.platform !== platformFilter) return false
    if (modeFilter !== '全部' && c.replyMode !== modeFilter) return false
    return true
  })

  const handleDelete = (id: string) => {
    deleteCampaign.mutate(id)
    setDeleteId(null)
  }

  const handleToggle = (id: string, status: string) => {
    updateCampaign.mutate({ id, data: { status: status === 'active' ? 'paused' : 'active' } })
  }

  const handleRunOnce = (id: string) => {
    runCampaign.mutate(id, {
      onSuccess: ({ execution_id }) => {
        setStartedExecutions((current) => ({ ...current, [id]: execution_id }))
      },
    })
  }

  const openExecution = (executionId: string) => {
    navigate(`/executions?execution_id=${encodeURIComponent(executionId)}`)
  }

  const renderActions = (campaign: VisibleCampaign, compact = false) => (
    <div className={compact ? 'grid grid-cols-5 gap-1' : 'flex flex-wrap items-center gap-1.5'}>
      <ActionButton label="详情" title={`查看详情 ${campaign.name}`} compact={compact} onClick={() => setDetailId(campaign.id)}><Eye size={14} /></ActionButton>
      <ActionButton label="编辑" title={`编辑设置 ${campaign.name}`} compact={compact} onClick={() => navigate(`/campaigns/${campaign.id}`)}><Edit3 size={14} /></ActionButton>
      <ActionButton label="运行" title={`运行一次 ${campaign.name}`} compact={compact} disabled={runCampaign.isPending} onClick={() => handleRunOnce(campaign.id)}><Play size={14} /></ActionButton>
      <ActionButton label={campaign.status === 'active' ? '暂停' : '启用'} title={campaign.status === 'active' ? `暂停活动 ${campaign.name}` : `启用活动 ${campaign.name}`} compact={compact} onClick={() => handleToggle(campaign.id, campaign.status)}>
        {campaign.status === 'active' ? <Pause size={14} /> : <Play size={14} />}
      </ActionButton>
      <ActionButton label="删除" title={`删除 ${campaign.name}`} compact={compact} danger onClick={() => setDeleteId(campaign.id)}><Trash2 size={14} /></ActionButton>
    </div>
  )

  return (
    <div className="flex min-h-full flex-col">
      <div className="flex-1 p-4 md:p-6 flex flex-col gap-4">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h1 className="text-lg md:text-xl font-semibold text-gray-900">营销活动</h1>
            <p className="text-sm text-gray-500 mt-0.5 hidden md:block">管理并监控所有社媒获客活动</p>
          </div>
          <button
            type="button"
            className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg text-white hover:opacity-90 shrink-0"
            style={{ background: 'var(--primary)', minHeight: 44 }}
            onClick={() => navigate('/campaigns/new')}
          >
            <Plus size={14} />
            <span className="hidden sm:inline">新建活动</span>
            <span className="sm:hidden">新建</span>
          </button>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative flex-1 min-w-0 md:flex-none">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <label htmlFor="campaign-search" className="sr-only">搜索活动</label>
            <input
              id="campaign-search"
              type="text"
              placeholder="搜索活动..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 pr-3 py-2 text-sm border rounded-lg bg-white focus:outline-none w-full"
              style={{ borderColor: 'var(--border)', minHeight: 44 }}
            />
          </div>
          <div className="hidden md:flex items-center gap-2">
            {[
              { label: '全部平台', options: ['全部', 'Facebook', 'Instagram', 'TikTok', 'X', 'YouTube'].map((value) => ({ value, label: value })), value: platformFilter, onChange: setPlatformFilter },
              { label: '全部状态', options: [{ value: '全部', label: '全部状态' }, { value: 'active', label: getStatusLabel('active') }, { value: 'paused', label: getStatusLabel('paused') }, { value: 'draft', label: getStatusLabel('draft') }, { value: 'error', label: getStatusLabel('error') }], value: statusFilter, onChange: setStatusFilter },
              { label: '全部模式', options: ['全部', '已关闭', '人工审批', '自动执行'].map((value) => ({ value, label: value })), value: modeFilter, onChange: setModeFilter },
            ].map((f) => (
              <select key={f.label} aria-label={f.label} value={f.value} onChange={(e) => f.onChange(e.target.value)} className="px-3 py-2 text-sm border rounded-lg bg-white focus:outline-none" style={{ borderColor: 'var(--border)' }}>
                {f.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            ))}
          </div>
          <button
            type="button"
            className="md:hidden flex items-center gap-1.5 px-3 py-2 text-sm border rounded-lg hover:bg-gray-50 shrink-0"
            style={{ borderColor: 'var(--border)', minHeight: 44 }}
            onClick={() => setFiltersOpen(true)}
          >
            <SlidersHorizontal size={14} />
            筛选
          </button>
          <span className="ml-auto text-xs text-gray-400 shrink-0">{filtered.length} 个活动</span>
        </div>

        <CampaignList campaigns={filtered} loading={isLoading} hasError={Boolean(error)} renderActions={renderActions} onOpenExecution={openExecution} />
      </div>

      {filtersOpen && (
        <div className="fixed inset-0 z-50 flex flex-col justify-end md:hidden">
          <button type="button" className="absolute inset-0 bg-black/40" aria-label="关闭筛选" onClick={() => setFiltersOpen(false)} />
          <div className="relative bg-white rounded-t-2xl p-5 flex flex-col gap-4">
            <div className="w-8 h-1 rounded-full bg-gray-300 mx-auto mb-2" />
            <div className="text-sm font-semibold text-gray-900">筛选</div>
            {[
              { label: '平台', options: ['全部', 'Facebook', 'Instagram', 'TikTok', 'X', 'YouTube'].map((value) => ({ value, label: value })), value: platformFilter, onChange: setPlatformFilter },
              { label: '状态', options: [{ value: '全部', label: '全部状态' }, { value: 'active', label: getStatusLabel('active') }, { value: 'paused', label: getStatusLabel('paused') }, { value: 'draft', label: getStatusLabel('draft') }, { value: 'error', label: getStatusLabel('error') }], value: statusFilter, onChange: setStatusFilter },
              { label: '回复模式', options: ['全部', '已关闭', '人工审批', '自动执行'].map((value) => ({ value, label: value })), value: modeFilter, onChange: setModeFilter },
            ].map((f) => (
              <div key={f.label} className="flex flex-col gap-1.5">
                <label htmlFor={`campaign-filter-${f.label}`} className="text-xs font-medium text-gray-600">{f.label}</label>
                <select id={`campaign-filter-${f.label}`} value={f.value} onChange={(e) => f.onChange(e.target.value)} className="px-3 py-3 text-sm border rounded-xl bg-white focus:outline-none" style={{ borderColor: 'var(--border)', minHeight: 44 }}>
                  {f.options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </div>
            ))}
            <button
              type="button"
              className="w-full py-3 text-sm font-medium rounded-xl text-white mt-2"
              style={{ background: 'var(--primary)', minHeight: 44 }}
              onClick={() => setFiltersOpen(false)}
            >
              应用筛选
            </button>
          </div>
        </div>
      )}

      <CampaignDetailModal
        open={detailId !== null}
        campaign={selectedCampaign}
        detail={detail}
        loading={detailLoading}
        hasError={Boolean(detailError)}
        onClose={() => setDetailId(null)}
        onEdit={(id) => navigate(`/campaigns/${id}`)}
        onRun={handleRunOnce}
        onToggle={handleToggle}
        onDelete={(id) => setDeleteId(id)}
        onOpenExecution={openExecution}
        runPending={runCampaign.isPending}
      />

      <ConfirmModal
        open={deleteId !== null}
        title="确认删除活动"
        description="删除后该活动的所有配置、关键词和执行记录将被永久删除，此操作不可撤销。"
        confirmLabel="删除活动"
        destructive
        onConfirm={() => deleteId && handleDelete(deleteId)}
        onCancel={() => setDeleteId(null)}
      />
    </div>
  )
}

function ActionButton({
  children,
  label,
  title,
  compact,
  danger,
  disabled,
  onClick,
}: {
  children: React.ReactNode
  label: string
  title: string
  compact?: boolean
  danger?: boolean
  disabled?: boolean
  onClick: () => void
}) {
  const color = danger ? 'text-red-500 hover:bg-red-50' : 'text-gray-600 hover:bg-gray-100 hover:text-blue-600'
  return (
    <button
      type="button"
      className={`${compact ? 'px-1 py-2 text-[11px]' : 'px-2.5 py-1.5 text-xs'} inline-flex min-h-10 items-center justify-center gap-1 rounded-lg border bg-white font-medium disabled:opacity-50 ${color}`}
      style={{ borderColor: 'var(--border)' }}
      title={title}
      aria-label={title}
      disabled={disabled}
      onClick={(event) => {
        event.stopPropagation()
        onClick()
      }}
    >
      {children}
      <span className={compact ? 'hidden min-[420px]:inline' : ''}>{label}</span>
    </button>
  )
}