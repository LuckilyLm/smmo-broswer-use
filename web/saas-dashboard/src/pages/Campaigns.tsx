import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { Edit3, Eye, ExternalLink, Pause, Play, Plus, Search, Settings2, SlidersHorizontal, Trash2, X } from 'lucide-react'
import StatusBadge, { getStatusLabel } from '../components/ui/StatusBadge'

import ConfirmModal from '../components/ui/ConfirmModal'
import { useCampaign, useCampaigns, useDeleteCampaign, useRunCampaign, useUpdateCampaign, type CampaignDetail } from '../api/campaigns'
import { useExecutions, type Execution } from '../api/executions'

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

export function campaignStatusLabel(status: string) {
  return ({ active: '已启用', paused: '已暂停', draft: '草稿', archived: '已归档', error: '异常' } as Record<string, string>)[status] || status
}

export function executionStatusLabel(status?: string) {
  if (!status) return '尚未执行'
  return ({ queued: '排队中', running: '执行中', completed: '已完成', partial: '部分完成', failed: '失败', cancelled: '已取消' } as Record<string, string>)[status] || status
}

export function latestExecutionsByCampaign(executions: Execution[]) {
  return executions.reduce<Record<string, Execution>>((latest, execution) => {
    const previous = latest[execution.campaign_id]
    const timestamp = Date.parse(execution.created_at || execution.started_at || '') || 0
    const previousTimestamp = previous ? Date.parse(previous.created_at || previous.started_at || '') || 0 : -1
    if (!previous || timestamp > previousTimestamp) latest[execution.campaign_id] = execution
    return latest
  }, {})
}

interface CampaignsProps {
  onNavigate?: (page: string) => void
  onMenuOpen?: () => void
}

type VisibleCampaign = {
  id: string
  name: string
  platform: string
  account: string
  keywords: number
  status: string
  replyMode: string
  leads: number
  pending: number
  lastRun: string
  nextRun: string
  owner: string
  execution?: Execution
  executionStatus?: string
  executionProgress: number
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
  const terminalExecutions = useRef(new Set<string>())
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
      if (execution?.id === executionId && terminal.has(execution.status) && !terminalExecutions.current.has(executionId)) {
        terminalExecutions.current.add(executionId)
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

        <div className="hidden md:block bg-white border rounded-xl overflow-hidden" style={{ borderColor: 'var(--border)' }}>
          {isLoading && <div className="p-4 text-sm text-gray-500">正在加载活动...</div>}
          {error && <div className="p-4 text-sm text-red-500">活动加载失败，请稍后重试</div>}
          <div className="overflow-x-auto">
            <table className="w-full text-sm" style={{ minWidth: 980 }}>
              <thead>
                <tr className="border-b" style={{ borderColor: 'var(--border)', background: '#fafafa' }}>
                  {['活动名称', '平台账号', '启用状态', '任务执行状态', '线索', '操作'].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-gray-500 whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((c) => (
                  <tr
                    key={c.id}
                    className="border-b last:border-0 hover:bg-gray-50"
                    style={{ borderColor: 'var(--border)' }}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2 min-w-0">
                        <div className="w-2 h-2 rounded-full shrink-0" style={{ background: platColors[c.platform] }} />
                        <span className="min-w-0 max-w-[320px] truncate font-medium text-gray-800">{c.name}</span>
                      </div>
                    </td>
                    <td className="max-w-[240px] truncate px-4 py-3 text-xs text-gray-500">{c.account}</td>
                    <td className="px-4 py-3"><StatusBadge status={c.status} label={campaignStatusLabel(c.status)} variant="dot" /></td>
                    <td className="px-4 py-3">
                      {c.execution ? (
                        <button type="button" className="group text-left" onClick={(event) => { event.stopPropagation(); openExecution(c.execution!.id) }} title="查看执行详情" aria-label={`${c.name} 查看执行详情`}>
                          <span className="inline-flex items-center gap-1"><StatusBadge status={c.executionStatus!} label={executionStatusLabel(c.executionStatus)} variant="dot" /><ExternalLink size={11} className="text-gray-400 group-hover:text-blue-600" /></span>
                          {(c.executionStatus === 'queued' || c.executionStatus === 'running') && <span className="mt-1 block text-[11px] text-blue-600">进度 {c.executionProgress}%</span>}
                        </button>
                      ) : <span className="text-xs text-gray-400">尚未执行</span>}
                    </td>
                    <td className="px-4 py-3 font-medium text-gray-800">{c.leads}</td>
                    <td className="px-4 py-3">{renderActions(c)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="md:hidden flex flex-col gap-2">
          {filtered.map((c) => (
            <div
              key={c.id}
              className="bg-white border rounded-xl p-4"
              style={{ borderColor: 'var(--border)' }}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <div className="w-2 h-2 rounded-full shrink-0" style={{ background: platColors[c.platform] }} />
                  <span className="font-medium text-gray-900 truncate">{c.name}</span>
                </div>
                <StatusBadge status={c.status} label={campaignStatusLabel(c.status)} variant="dot" />
              </div>
              <div className="mt-2 text-xs text-gray-500 truncate">{c.account}</div>
              <div className="mt-3 flex items-center justify-between gap-2 border-t pt-3" style={{ borderColor: 'var(--border)' }}>
                <span className="text-xs text-gray-400">任务执行状态</span>
                {c.execution ? (
                  <button type="button" className="flex items-center gap-1" onClick={(event) => { event.stopPropagation(); openExecution(c.execution!.id) }} aria-label={`${c.name} 查看执行详情`}>
                    <StatusBadge status={c.executionStatus!} label={executionStatusLabel(c.executionStatus)} variant="dot" />
                    {(c.executionStatus === 'queued' || c.executionStatus === 'running') && <span className="text-xs text-blue-600">{c.executionProgress}%</span>}
                    <ExternalLink size={11} className="text-gray-400" />
                  </button>
                ) : <span className="text-xs text-gray-400">尚未执行</span>}
              </div>
              <div className="mt-3 flex items-center justify-between gap-3">
                <span className="shrink-0 text-xs text-gray-600">线索 <span className="font-semibold text-gray-900">{c.leads}</span></span>
                <div className="min-w-0 flex-1">{renderActions(c, true)}</div>
              </div>
            </div>
          ))}
        </div>

        {filtered.length === 0 && (
          <div className="flex flex-col items-center py-16 text-gray-400">
            <Megaphone size={32} className="mb-3 text-gray-200" />
            <div className="text-sm">暂无匹配的活动</div>
          </div>
        )}
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

function CampaignDetailModal({
  open,
  campaign,
  detail,
  loading,
  hasError,
  runPending,
  onClose,
  onEdit,
  onRun,
  onToggle,
  onDelete,
  onOpenExecution,
}: {
  open: boolean
  campaign: VisibleCampaign | null
  detail?: CampaignDetail
  loading: boolean
  hasError: boolean
  runPending: boolean
  onClose: () => void
  onEdit: (id: string) => void
  onRun: (id: string) => void
  onToggle: (id: string, status: string) => void
  onDelete: (id: string) => void
  onOpenExecution: (id: string) => void
}) {
  if (!open || !campaign) return null
  const keywords = (detail?.keywords || []).reduce<string[]>((items, item) => {
    const keyword = item.keyword || item.name || String(item)
    if (keyword) items.push(keyword)
    return items
  }, [])
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center md:items-center">
      <button type="button" className="absolute inset-0 bg-black/35" aria-label="关闭详情" onClick={onClose} />
      <div
        className="relative flex max-h-[92vh] w-full flex-col rounded-t-2xl border bg-white shadow-xl md:w-[760px] md:rounded-xl"
        style={{ borderColor: 'var(--border)' }}
        role="dialog"
        aria-modal="true"
        aria-labelledby="campaign-detail-title"
      >
        <div className="flex items-start justify-between gap-4 border-b p-5" style={{ borderColor: 'var(--border)' }}>
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <StatusBadge status={campaign.status} label={campaignStatusLabel(campaign.status)} variant="dot" />
              <span className="text-xs text-gray-400">{campaign.account}</span>
            </div>
            <h2 id="campaign-detail-title" className="truncate text-lg font-semibold text-gray-900">{campaign.name}</h2>
          </div>
          <button type="button" className="rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600" style={{ minHeight: 44, minWidth: 44 }} onClick={onClose} aria-label="关闭详情">
            <X size={18} />
          </button>
        </div>
        <div className="overflow-y-auto p-5">
          {loading ? (
            <div className="py-10 text-center text-sm text-gray-400">正在加载活动详情...</div>
          ) : hasError ? (
            <div className="py-10 text-center text-sm text-red-500">活动详情加载失败，请稍后重试。</div>
          ) : (
            <div className="flex flex-col gap-5">
              <DetailSection title="基础信息">
                <Info label="平台" value={campaign.platform} />
                <Info label="关键词数" value={campaign.keywords} />
                <Info label="线索数" value={campaign.leads} />
                <Info label="待审批" value={campaign.pending || '—'} />
                <Info label="最近执行" value={campaign.lastRun} />
                <Info label="下次执行" value={campaign.nextRun} />
                <Info label="负责人" value={campaign.owner} />
                <Info label="回复模式" value={campaign.replyMode} />
              </DetailSection>
              <DetailSection title="执行配置">
                <Info label="目标策略" value={targetPolicyLabel(detail?.target_policy)} />
                <Info label="内容上限" value={detail?.max_contents ?? '—'} />
                <Info label="评论上限" value={detail?.max_comments ?? '—'} />
                <Info label="置信度阈值" value={detail?.min_confidence ?? '—'} />
                <Info label="线索上限" value={detail?.max_leads ?? '—'} />
                <Info label="每日上限" value={detail?.daily_limit ?? '—'} />
                <Info label="大模型识别" value={yesNo(detail?.llm_enabled)} />
                <Info label="识别模式" value={detectionModeLabel(detail?.lead_detection_mode)} />
                <Info label="内容语言" value={languageLabel(detail?.content_language)} />
              </DetailSection>
              <DetailSection title="回复配置">
                <Info label="每日回复上限" value={detail?.reply_daily_limit ?? '—'} />
                <Info label="每分钟上限" value={detail?.reply_per_minute_limit ?? '—'} />
                <Info label="每小时上限" value={detail?.reply_per_hour_limit ?? '—'} />
                <Info label="最小间隔" value={detail?.reply_min_interval_seconds ? `${detail.reply_min_interval_seconds} 秒` : '—'} />
                <Info label="默认 WhatsApp" value={detail?.default_whatsapp || '—'} />
                <Info label="默认邮箱" value={detail?.default_email || '—'} />
                <Info label="默认网站" value={detail?.default_website || '—'} />
              </DetailSection>
              <section>
                <h3 className="mb-2 text-sm font-semibold text-gray-900">关键词</h3>
                {keywords.length ? (
                  <div className="flex flex-wrap gap-2">{keywords.map((keyword) => <span key={keyword} className="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-700">{keyword}</span>)}</div>
                ) : (
                  <div className="text-sm text-gray-400">暂无关键词明细</div>
                )}
              </section>
              <section>
                <h3 className="mb-2 text-sm font-semibold text-gray-900">最近执行</h3>
                {campaign.execution ? (
                  <button type="button" className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm text-blue-600 hover:bg-blue-50" style={{ borderColor: 'var(--border)' }} onClick={() => onOpenExecution(campaign.execution!.id)}>
                    <ExternalLink size={14} />
                    查看执行详情
                  </button>
                ) : (
                  <div className="text-sm text-gray-400">尚未执行</div>
                )}
              </section>
            </div>
          )}
        </div>
        <div className="flex flex-col gap-2 border-t p-4 md:flex-row md:justify-end" style={{ borderColor: 'var(--border)' }}>
          <button type="button" className="inline-flex min-h-11 items-center justify-center gap-1 rounded-lg border px-3 text-sm hover:bg-gray-50" style={{ borderColor: 'var(--border)' }} onClick={() => onEdit(campaign.id)}><Settings2 size={14} />编辑设置</button>
          <button type="button" className="inline-flex min-h-11 items-center justify-center gap-1 rounded-lg border px-3 text-sm hover:bg-gray-50 disabled:opacity-50" style={{ borderColor: 'var(--border)' }} disabled={runPending} onClick={() => onRun(campaign.id)}><Play size={14} />运行一次</button>
          <button type="button" className="inline-flex min-h-11 items-center justify-center gap-1 rounded-lg border px-3 text-sm hover:bg-gray-50" style={{ borderColor: 'var(--border)' }} onClick={() => onToggle(campaign.id, campaign.status)}>{campaign.status === 'active' ? <Pause size={14} /> : <Play size={14} />}{campaign.status === 'active' ? '暂停' : '启用'}</button>
          <button type="button" className="inline-flex min-h-11 items-center justify-center gap-1 rounded-lg border px-3 text-sm text-red-500 hover:bg-red-50" style={{ borderColor: 'var(--border)' }} onClick={() => onDelete(campaign.id)}><Trash2 size={14} />删除</button>
        </div>
      </div>
    </div>
  )
}

function DetailSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-3 text-sm font-semibold text-gray-900">{title}</h3>
      <dl className="grid grid-cols-2 gap-3 md:grid-cols-3">{children}</dl>
    </section>
  )
}

function Info({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="min-w-0 rounded-lg border bg-gray-50 px-3 py-2" style={{ borderColor: 'var(--border)' }}>
      <dt className="text-xs text-gray-400">{label}</dt>
      <dd className="mt-1 truncate text-sm font-medium text-gray-800">{value}</dd>
    </div>
  )
}

function Megaphone({ size, className }: { size: number; className?: string }) {
  return <svg width={size} height={size} className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path d="M3 11l19-9-9 19-2-8-8-2z" /></svg>
}
