import { ExternalLink, Pause, Play, Settings2, Trash2, X } from 'lucide-react'
import type { CampaignDetail } from '../../api/campaigns'
import type { Execution } from '../../api/executions'
import StatusBadge from '../../components/ui/StatusBadge'
import { ModalDialog } from '../../components/ui/ConfirmModal'
import { campaignStatusLabel, executionStatusLabel } from '../campaignHelpers'

export type VisibleCampaign = {
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

interface CampaignDetailModalProps {
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
}

export default function CampaignDetailModal({ open, campaign, detail, loading, hasError, runPending, onClose, onEdit, onRun, onToggle, onDelete, onOpenExecution }: CampaignDetailModalProps) {
  if (!open || !campaign) return null
  const keywords = (detail?.keywords || []).reduce<string[]>((items, item) => {
    const keyword = item.keyword || item.name || String(item)
    if (keyword) items.push(keyword)
    return items
  }, [])
  return (
    <ModalDialog open={open} onClose={onClose} labelledBy="campaign-detail-title" className="flex items-end justify-center backdrop:bg-black/35 md:items-center" panelClassName="relative flex max-h-[92vh] w-full flex-col rounded-t-2xl border bg-white shadow-xl md:w-[760px] md:rounded-xl" panelStyle={{ borderColor: 'var(--border)' }}>
      <div className="flex items-start justify-between gap-4 border-b p-5" style={{ borderColor: 'var(--border)' }}>
        <div className="min-w-0"><div className="mb-2 flex flex-wrap items-center gap-2"><StatusBadge status={campaign.status} label={campaignStatusLabel(campaign.status)} variant="dot" /><span className="text-xs text-gray-400">{campaign.account}</span></div><h2 id="campaign-detail-title" className="truncate text-lg font-semibold text-gray-900">{campaign.name}</h2></div>
        <button type="button" className="rounded-lg p-2 text-gray-400 hover:bg-gray-100 hover:text-gray-600" style={{ minHeight: 44, minWidth: 44 }} onClick={onClose} aria-label="关闭详情"><X size={18} /></button>
      </div>
      <div className="overflow-y-auto p-5">
        {loading ? <div className="py-10 text-center text-sm text-gray-400">正在加载活动详情...</div> : hasError ? <div className="py-10 text-center text-sm text-red-500">活动详情加载失败，请稍后重试。</div> : (
          <div className="flex flex-col gap-5">
            <DetailSection title="基础信息"><Info label="平台" value={campaign.platform} /><Info label="关键词数" value={campaign.keywords} /><Info label="线索数" value={campaign.leads} /><Info label="待审批" value={campaign.pending || '—'} /><Info label="最近执行" value={campaign.lastRun} /><Info label="下次执行" value={campaign.nextRun} /><Info label="负责人" value={campaign.owner} /><Info label="回复模式" value={campaign.replyMode} /></DetailSection>
            <DetailSection title="执行配置"><Info label="目标策略" value={targetPolicyLabel(detail?.target_policy)} /><Info label="内容上限" value={detail?.max_contents ?? '—'} /><Info label="评论上限" value={detail?.max_comments ?? '—'} /><Info label="置信度阈值" value={detail?.min_confidence ?? '—'} /><Info label="线索上限" value={detail?.max_leads ?? '—'} /><Info label="每日上限" value={detail?.daily_limit ?? '—'} /><Info label="大模型识别" value={yesNo(detail?.llm_enabled)} /><Info label="识别模式" value={detectionModeLabel(detail?.lead_detection_mode)} /><Info label="内容语言" value={languageLabel(detail?.content_language)} /></DetailSection>
            <DetailSection title="回复配置"><Info label="每日回复上限" value={detail?.reply_daily_limit ?? '—'} /><Info label="每分钟上限" value={detail?.reply_per_minute_limit ?? '—'} /><Info label="每小时上限" value={detail?.reply_per_hour_limit ?? '—'} /><Info label="最小间隔" value={detail?.reply_min_interval_seconds ? `${detail.reply_min_interval_seconds} 秒` : '—'} /><Info label="默认 WhatsApp" value={detail?.default_whatsapp || '—'} /><Info label="默认邮箱" value={detail?.default_email || '—'} /><Info label="默认网站" value={detail?.default_website || '—'} /></DetailSection>
            <section><h3 className="mb-2 text-sm font-semibold text-gray-900">关键词</h3>{keywords.length ? <div className="flex flex-wrap gap-2">{keywords.map((keyword) => <span key={keyword} className="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-700">{keyword}</span>)}</div> : <div className="text-sm text-gray-400">暂无关键词明细</div>}</section>
            <section><h3 className="mb-2 text-sm font-semibold text-gray-900">最近执行</h3>{campaign.execution ? <button type="button" className="inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm text-blue-600 hover:bg-blue-50" style={{ borderColor: 'var(--border)' }} onClick={() => onOpenExecution(campaign.execution!.id)}><ExternalLink size={14} />查看执行详情</button> : <div className="text-sm text-gray-400">尚未执行</div>}</section>
          </div>
        )}
      </div>
      <div className="flex flex-col gap-2 border-t p-4 md:flex-row md:justify-end" style={{ borderColor: 'var(--border)' }}><button type="button" className="inline-flex min-h-11 items-center justify-center gap-1 rounded-lg border px-3 text-sm hover:bg-gray-50" style={{ borderColor: 'var(--border)' }} onClick={() => onEdit(campaign.id)}><Settings2 size={14} />编辑设置</button><button type="button" className="inline-flex min-h-11 items-center justify-center gap-1 rounded-lg border px-3 text-sm hover:bg-gray-50 disabled:opacity-50" style={{ borderColor: 'var(--border)' }} disabled={runPending} onClick={() => onRun(campaign.id)}><Play size={14} />运行一次</button><button type="button" className="inline-flex min-h-11 items-center justify-center gap-1 rounded-lg border px-3 text-sm hover:bg-gray-50" style={{ borderColor: 'var(--border)' }} onClick={() => onToggle(campaign.id, campaign.status)}>{campaign.status === 'active' ? <Pause size={14} /> : <Play size={14} />}{campaign.status === 'active' ? '暂停' : '启用'}</button><button type="button" className="inline-flex min-h-11 items-center justify-center gap-1 rounded-lg border px-3 text-sm text-red-500 hover:bg-red-50" style={{ borderColor: 'var(--border)' }} onClick={() => onDelete(campaign.id)}><Trash2 size={14} />删除</button></div>
    </ModalDialog>
  )
}

function targetPolicyLabel(value?: string) { if (value === 'discovery_only') return '仅发现公开线索'; if (value === 'owned_only') return '仅自有内容'; if (value === 'allowlist') return '允许列表'; return value || '—' }
function detectionModeLabel(value?: string) { if (value === 'rules_only') return '规则判断'; if (value === 'rules_with_llm') return '规则 + 大模型'; return value || '—' }
function languageLabel(value?: string) { if (!value || value === 'any') return '不限'; if (value === 'zh-CN') return '中文'; if (value === 'en-US' || value === 'en') return '英文'; return value }
function yesNo(value?: boolean) { if (value === true) return '启用'; if (value === false) return '关闭'; return '—' }
function DetailSection({ title, children }: { title: string; children: React.ReactNode }) { return <section><h3 className="mb-3 text-sm font-semibold text-gray-900">{title}</h3><dl className="grid grid-cols-2 gap-3 md:grid-cols-3">{children}</dl></section> }
function Info({ label, value }: { label: string; value: React.ReactNode }) { return <div className="min-w-0 rounded-lg border bg-gray-50 px-3 py-2" style={{ borderColor: 'var(--border)' }}><dt className="text-xs text-gray-400">{label}</dt><dd className="mt-1 truncate text-sm font-medium text-gray-800">{value}</dd></div> }
