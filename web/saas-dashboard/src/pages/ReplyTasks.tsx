import { useMemo, useState } from 'react'
import { CheckCircle, ChevronDown, ChevronUp, Eye, Info, X, XCircle } from 'lucide-react'

import { useApproveCandidate, useApprovePlan, useCancelPlan, useRejectCandidate, useReplyCandidates, useReplyPlans, type ReplyCandidate, type ReplyPlan } from '../api/reply-tasks'
import StatusBadge from '../components/ui/StatusBadge'

const TABS = [
  { label: '待审批', value: 'pending_approval' },
  { label: '已批准', value: 'approved' },
  { label: '执行中', value: 'executing' },
  { label: '已完成', value: 'completed' },
  { label: '已失败', value: 'failed' },
  { label: '已取消', value: 'cancelled' },
]
const MAIN_TABS = ['回复计划', '回复候选']

function statusLabel(value?: string) {
  const map: Record<string, string> = {
    pending_approval: '待审批',
    approved: '已批准',
    rejected: '已拒绝',
    cancelled: '已取消',
    executing: '执行中',
    completed: '已完成',
    failed: '失败',
    sent: '已发送',
    blocked: '已阻断',
    manual_approval: '人工审批',
    disabled: '已关闭',
    automatic: '自动执行',
  }
  return map[value || ''] || value || '—'
}

function formatDate(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function PlanDrawer({ plan, candidates, onClose }: { plan: ReplyPlan; candidates: ReplyCandidate[]; onClose: () => void }) {
  const approveCandidate = useApproveCandidate()
  const rejectCandidate = useRejectCandidate()
  const approvePlan = useApprovePlan()
  const cancelPlan = useCancelPlan()
  const [expandedId, setExpandedId] = useState<string | null>(candidates[0]?.id || null)

  return (
    <div className="fixed inset-0 z-50 flex min-h-0 flex-col overflow-hidden bg-white shadow-xl md:inset-y-0 md:left-auto md:right-0 md:w-[580px] md:border-l" style={{ borderColor: 'var(--border)' }}>
      <div className="flex shrink-0 items-center justify-between border-b px-5 py-4" style={{ borderColor: 'var(--border)' }}>
        <div><h3 className="font-semibold text-gray-900">回复计划详情</h3><div className="mt-0.5 font-mono text-xs text-gray-400">{plan.id}</div></div>
        <button className="p-2 text-gray-400 hover:text-gray-600" onClick={onClose} style={{ minHeight: 44, minWidth: 44 }}><X size={16} /></button>
      </div>
      <div className="mx-4 mt-3 flex items-start gap-2 rounded-lg border px-3 py-2.5" style={{ background: '#fffbeb', borderColor: '#fcd34d' }}>
        <Info size={13} className="mt-0.5 shrink-0 text-amber-500" />
        <div className="text-xs text-amber-700">当前 SaaS 执行保持安全模式：批准只进入审批状态，不会绕过系统级发送开关。</div>
      </div>
      <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
        <div className="rounded-xl border p-4" style={{ borderColor: 'var(--border)' }}>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">计划信息</div>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <InfoCell label="活动 ID" value={plan.campaign_id} mono />
            <InfoCell label="执行 ID" value={plan.execution_id || '—'} mono />
            <InfoCell label="回复模式" value={statusLabel(plan.reply_mode)} />
            <InfoCell label="计划状态" value={statusLabel(plan.status)} />
            <InfoCell label="候选数量" value={String(plan.total_candidates)} />
            <InfoCell label="创建时间" value={formatDate(plan.created_at)} />
          </div>
        </div>
        <div>
          <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">候选回复</div>
          <div className="flex flex-col gap-2">
            {candidates.length === 0 && <div className="rounded-xl border p-6 text-center text-sm text-gray-400" style={{ borderColor: 'var(--border)' }}>暂无候选回复</div>}
            {candidates.map((c) => {
              const expanded = expandedId === c.id
              return (
                <div key={c.id} className="overflow-hidden rounded-xl border" style={{ borderColor: 'var(--border)' }}>
                  <div className="cursor-pointer bg-white p-3.5" onClick={() => setExpandedId(expanded ? null : c.id)}>
                    <div className="mb-1.5 flex items-center justify-between">
                      <span className="text-xs font-medium text-gray-800">{c.author_name || '未知作者'}</span>
                      <div className="flex items-center gap-2"><StatusBadge status={statusLabel(c.status)} />{expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}</div>
                    </div>
                    <div className="line-clamp-2 text-xs text-gray-500">{c.comment_text || '—'}</div>
                    <div className="mt-2 flex flex-wrap gap-1.5 text-[11px] text-gray-400"><span className="rounded bg-gray-100 px-1.5 py-0.5">规则：{c.matched_rule_name || c.matched_rule_id || '—'}</span><span className="rounded bg-gray-100 px-1.5 py-0.5">模板：{c.reply_template_id || '—'}</span></div>
                  </div>
                  {expanded && (
                    <div className="border-t p-3.5" style={{ borderColor: 'var(--border)', background: '#fafafa' }}>
                      <div className="mb-1.5 text-[11px] text-gray-500">渲染后回复内容</div>
                      <div className="text-xs leading-relaxed text-gray-700">{c.rendered_reply_text || '—'}</div>
                      {c.status === 'pending_approval' && <div className="mt-3 flex gap-2"><button className="flex flex-1 items-center justify-center gap-1 rounded-lg border px-3 py-2 text-xs text-red-500 hover:bg-red-50" style={{ borderColor: '#fca5a5', minHeight: 44 }} onClick={() => rejectCandidate.mutate({ id: c.id, reason: '人工拒绝' })}><XCircle size={12} />拒绝</button><button className="flex flex-1 items-center justify-center gap-1 rounded-lg px-3 py-2 text-xs text-white" style={{ background: 'var(--primary)', minHeight: 44 }} onClick={() => approveCandidate.mutate(c.id)}><CheckCircle size={12} />批准</button></div>}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>
      <div className="flex shrink-0 gap-2 border-t p-4" style={{ borderColor: 'var(--border)' }}>
        <button className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border px-3 py-2.5 text-sm font-medium text-red-500 hover:bg-red-50" style={{ borderColor: '#fca5a5', minHeight: 44 }} onClick={() => cancelPlan.mutate(plan.id)}><XCircle size={13} />取消计划</button>
        <button className="flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2.5 text-sm font-medium text-white disabled:opacity-50" style={{ background: 'var(--primary)', minHeight: 44 }} disabled={plan.status !== 'pending_approval'} onClick={() => approvePlan.mutate(plan.id)}><CheckCircle size={13} />批准计划</button>
      </div>
    </div>
  )
}

export default function ReplyTasks() {
  const [mainTab, setMainTab] = useState('回复计划')
  const [activeTab, setActiveTab] = useState('pending_approval')
  const [openPlanId, setOpenPlanId] = useState<string | null>(null)
  const { data: plansPage, isLoading: plansLoading, error: plansError } = useReplyPlans(activeTab)
  const { data: candidatesPage, isLoading: candidatesLoading, error: candidatesError } = useReplyCandidates(mainTab === '回复候选' ? activeTab : undefined)
  const { data: allCandidatesPage } = useReplyCandidates()
  const plans = plansPage?.items || []
  const candidates = candidatesPage?.items || []
  const allCandidates = allCandidatesPage?.items || []
  const openPlan = plans.find((p) => p.id === openPlanId) || null
  const candidatesByPlan = useMemo(() => {
    const map = new Map<string, ReplyCandidate[]>()
    for (const item of allCandidates) {
      if (!item.reply_plan_id) continue
      map.set(item.reply_plan_id, [...(map.get(item.reply_plan_id) || []), item])
    }
    return map
  }, [allCandidates])
  const metrics = [
    { label: '待审批计划', value: plansPage?.total ?? 0, color: '#f59e0b' },
    { label: '候选回复', value: allCandidatesPage?.total ?? 0, color: '#4338ca' },
    { label: '待审批候选', value: allCandidates.filter((c) => c.status === 'pending_approval').length, color: '#f59e0b' },
    { label: '已批准', value: allCandidates.filter((c) => c.status === 'approved').length, color: '#10b981' },
    { label: '失败', value: allCandidates.filter((c) => c.status === 'failed').length, color: '#ef4444' },
  ]

  return (
    <div className="flex min-h-full flex-col">
      <div className="flex flex-1 flex-col gap-4 p-4 md:p-6">
        <div><h1 className="text-lg font-semibold text-gray-900 md:text-xl">回复任务</h1><p className="mt-0.5 hidden text-sm text-gray-500 md:block">查看并审批真实执行产生的回复计划和候选回复</p></div>
        <div className="grid grid-cols-3 gap-2 md:grid-cols-5 md:gap-3">{metrics.map((m) => <div key={m.label} className="rounded-xl border bg-white px-3 py-3" style={{ borderColor: 'var(--border)' }}><div className="text-[11px] text-gray-400">{m.label}</div><div className="mt-1 text-2xl font-bold" style={{ color: m.color }}>{m.value}</div></div>)}</div>
        <div className="flex border-b" style={{ borderColor: 'var(--border)' }}>{MAIN_TABS.map((tab) => <button key={tab} className="border-b-2 px-4 py-2.5 text-sm font-medium" style={{ borderBottomColor: mainTab === tab ? 'var(--primary)' : 'transparent', color: mainTab === tab ? 'var(--primary)' : '#6b7280', minHeight: 44 }} onClick={() => setMainTab(tab)}>{tab}</button>)}</div>
        <div className="-mt-2 flex overflow-x-auto border-b" style={{ borderColor: 'var(--border)' }}>{TABS.map((tab) => <button key={tab.value} className="shrink-0 border-b-2 px-3 py-2 text-xs font-medium" style={{ borderBottomColor: activeTab === tab.value ? 'var(--primary)' : 'transparent', color: activeTab === tab.value ? 'var(--primary)' : '#6b7280', minHeight: 40 }} onClick={() => setActiveTab(tab.value)}>{tab.label}</button>)}</div>
        {(plansError || candidatesError) && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">回复任务加载失败，请刷新重试</div>}
        {mainTab === '回复计划' ? (
          <div className="overflow-hidden rounded-xl border bg-white" style={{ borderColor: 'var(--border)' }}>
            {plansLoading ? <div className="p-4 text-sm text-gray-500">正在加载回复计划...</div> : plans.length === 0 ? <div className="py-16 text-center text-sm text-gray-400">暂无{statusLabel(activeTab)}计划</div> : <div className="overflow-x-auto"><table className="w-full min-w-[820px] text-sm"><thead><tr className="border-b bg-gray-50" style={{ borderColor: 'var(--border)' }}>{['计划 ID', '活动', '执行', '回复模式', '候选', '已批准', '已发送', '失败', '状态', '创建时间', '操作'].map((h) => <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500">{h}</th>)}</tr></thead><tbody>{plans.map((p) => <tr key={p.id} className="border-b last:border-0 hover:bg-gray-50" style={{ borderColor: 'var(--border)' }}><td className="px-4 py-3 font-mono text-xs">{p.id}</td><td className="px-4 py-3 font-mono text-xs text-gray-500">{p.campaign_id}</td><td className="px-4 py-3 font-mono text-xs text-gray-500">{p.execution_id || '—'}</td><td className="px-4 py-3"><StatusBadge status={statusLabel(p.reply_mode)} /></td><td className="px-4 py-3 text-center">{p.total_candidates}</td><td className="px-4 py-3 text-center text-green-600">{p.approved_count}</td><td className="px-4 py-3 text-center">{p.sent_count}</td><td className="px-4 py-3 text-center text-red-500">{p.failed_count || '—'}</td><td className="px-4 py-3"><StatusBadge status={statusLabel(p.status)} variant="dot" /></td><td className="px-4 py-3 text-xs text-gray-400">{formatDate(p.created_at)}</td><td className="px-4 py-3"><button className="flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-xs text-indigo-600 hover:bg-gray-50" style={{ borderColor: 'var(--border)' }} onClick={() => setOpenPlanId(p.id)}><Eye size={11} />查看</button></td></tr>)}</tbody></table></div>}
          </div>
        ) : (
          <div className="flex flex-col gap-2">{candidatesLoading ? <div className="rounded-xl border bg-white p-4 text-sm text-gray-500" style={{ borderColor: 'var(--border)' }}>正在加载候选回复...</div> : candidates.length === 0 ? <div className="rounded-xl border bg-white py-16 text-center text-sm text-gray-400" style={{ borderColor: 'var(--border)' }}>暂无{statusLabel(activeTab)}候选</div> : candidates.map((c) => <div key={c.id} className="rounded-xl border bg-white p-4" style={{ borderColor: 'var(--border)' }}><div className="mb-2 flex items-start justify-between gap-2"><div className="font-medium text-gray-900">{c.author_name || '未知作者'}</div><StatusBadge status={statusLabel(c.status)} /></div><div className="mb-2 text-xs text-gray-500">{c.comment_text || '—'}</div><div className="mb-3 flex flex-wrap gap-1.5"><span className="rounded bg-gray-100 px-1.5 py-0.5 text-[11px] text-gray-500">规则：{c.matched_rule_name || c.matched_rule_id || '—'}</span><span className="rounded bg-gray-100 px-1.5 py-0.5 text-[11px] text-gray-500">计划：{c.reply_plan_id || '—'}</span></div><div className="border-t pt-2.5" style={{ borderColor: 'var(--border)' }}><div className="mb-1 text-[11px] text-gray-400">回复预览</div><div className="text-xs leading-relaxed text-gray-700">{c.rendered_reply_text || '—'}</div></div></div>)}</div>
        )}
      </div>
      {openPlan && <><div className="fixed inset-0 z-40 bg-black/20" onClick={() => setOpenPlanId(null)} /><PlanDrawer plan={openPlan} candidates={candidatesByPlan.get(openPlan.id) || []} onClose={() => setOpenPlanId(null)} /></>}
    </div>
  )
}

function InfoCell({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div className="min-w-0"><span className="text-xs text-gray-400">{label}</span><div className={`truncate text-sm font-medium text-gray-800 ${mono ? 'font-mono text-xs' : ''}`}>{value}</div></div>
}
