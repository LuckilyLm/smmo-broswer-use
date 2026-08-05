import { ExternalLink } from 'lucide-react'
import StatusBadge from '../../components/ui/StatusBadge'
import { campaignStatusLabel, executionStatusLabel } from '../campaignHelpers'
import type { VisibleCampaign } from './CampaignDetailModal'

interface CampaignListProps {
  campaigns: VisibleCampaign[]
  loading: boolean
  hasError: boolean
  renderActions: (campaign: VisibleCampaign, compact?: boolean) => React.ReactNode
  onOpenExecution: (id: string) => void
}

const platformColors: Record<string, string> = { Facebook: '#1877f2', Instagram: '#e1306c', TikTok: '#010101', X: '#1da1f2', YouTube: '#ff0000' }

export default function CampaignList({ campaigns, loading, hasError, renderActions, onOpenExecution }: CampaignListProps) {
  return <>
    <div className="hidden overflow-hidden rounded-xl border bg-white md:block" style={{ borderColor: 'var(--border)' }}>
      {loading && <div className="p-4 text-sm text-gray-500">正在加载活动...</div>}
      {hasError && <div className="p-4 text-sm text-red-500">活动加载失败，请稍后重试</div>}
      <div className="overflow-x-auto"><table className="w-full text-sm" style={{ minWidth: 980 }}><thead><tr className="border-b" style={{ borderColor: 'var(--border)', background: '#fafafa' }}>{['活动名称', '平台账号', '启用状态', '任务执行状态', '线索', '操作'].map((heading) => <th key={heading} className="whitespace-nowrap px-4 py-3 text-left text-xs font-semibold text-gray-500">{heading}</th>)}</tr></thead><tbody>{campaigns.map((campaign) => <tr key={campaign.id} className="border-b last:border-0 hover:bg-gray-50" style={{ borderColor: 'var(--border)' }}><td className="px-4 py-3"><div className="flex min-w-0 items-center gap-2"><div className="h-2 w-2 shrink-0 rounded-full" style={{ background: platformColors[campaign.platform] }} /><span className="min-w-0 max-w-[320px] truncate font-medium text-gray-800">{campaign.name}</span></div></td><td className="max-w-[240px] truncate px-4 py-3 text-xs text-gray-500">{campaign.account}</td><td className="px-4 py-3"><StatusBadge status={campaign.status} label={campaignStatusLabel(campaign.status)} variant="dot" /></td><td className="px-4 py-3">{campaign.execution ? <button type="button" className="group text-left" onClick={() => onOpenExecution(campaign.execution!.id)} title="查看执行详情" aria-label={`${campaign.name} 查看执行详情`}><span className="inline-flex items-center gap-1"><StatusBadge status={campaign.executionStatus!} label={executionStatusLabel(campaign.executionStatus)} variant="dot" /><ExternalLink size={11} className="text-gray-400 group-hover:text-blue-600" /></span>{(campaign.executionStatus === 'queued' || campaign.executionStatus === 'running') && <span className="mt-1 block text-[11px] text-blue-600">进度 {campaign.executionProgress}%</span>}</button> : <span className="text-xs text-gray-400">尚未执行</span>}</td><td className="px-4 py-3 font-medium text-gray-800">{campaign.leads}</td><td className="px-4 py-3">{renderActions(campaign)}</td></tr>)}</tbody></table></div>
    </div>
    <div className="flex flex-col gap-2 md:hidden">{campaigns.map((campaign) => <div key={campaign.id} className="rounded-xl border bg-white p-4" style={{ borderColor: 'var(--border)' }}><div className="flex items-start justify-between gap-2"><div className="flex min-w-0 items-center gap-2"><div className="h-2 w-2 shrink-0 rounded-full" style={{ background: platformColors[campaign.platform] }} /><span className="truncate font-medium text-gray-900">{campaign.name}</span></div><StatusBadge status={campaign.status} label={campaignStatusLabel(campaign.status)} variant="dot" /></div><div className="mt-2 truncate text-xs text-gray-500">{campaign.account}</div><div className="mt-3 flex items-center justify-between gap-2 border-t pt-3" style={{ borderColor: 'var(--border)' }}><span className="text-xs text-gray-400">任务执行状态</span>{campaign.execution ? <button type="button" className="flex items-center gap-1" onClick={() => onOpenExecution(campaign.execution!.id)} aria-label={`${campaign.name} 查看执行详情`}><StatusBadge status={campaign.executionStatus!} label={executionStatusLabel(campaign.executionStatus)} variant="dot" />{(campaign.executionStatus === 'queued' || campaign.executionStatus === 'running') && <span className="text-xs text-blue-600">{campaign.executionProgress}%</span>}<ExternalLink size={11} className="text-gray-400" /></button> : <span className="text-xs text-gray-400">尚未执行</span>}</div><div className="mt-3 flex items-center justify-between gap-3"><span className="shrink-0 text-xs text-gray-600">线索 <span className="font-semibold text-gray-900">{campaign.leads}</span></span><div className="min-w-0 flex-1">{renderActions(campaign, true)}</div></div></div>)}</div>
    {campaigns.length === 0 && <div className="flex flex-col items-center py-16 text-gray-400"><Megaphone size={32} className="mb-3 text-gray-200" /><div className="text-sm">暂无匹配的活动</div></div>}
  </>
}

function Megaphone({ size, className }: { size: number; className?: string }) { return <svg width={size} height={size} className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path d="M3 11l19-9-9 19-2-8-8-2z" /></svg> }
