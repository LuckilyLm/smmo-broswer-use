import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle, Edit3, Plus, Search, Trash2, X, XCircle } from 'lucide-react'

import { useCampaigns } from '../api/campaigns'
import { useCreateMatchingRule, useDeleteMatchingRule, useMatchingRules, useTestMatchingRule, useUpdateMatchingRule, type MatchingRule } from '../api/matching-rules'
import { useReplyTemplates } from '../api/reply-templates'
import ConfirmModal from '../components/ui/ConfirmModal'
import StatusBadge from '../components/ui/StatusBadge'

const inp = "w-full rounded-lg border bg-white px-3 py-2.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500"

function RuleDrawer({ rule, defaultCampaignId, onClose }: { rule?: MatchingRule | null; defaultCampaignId: string; onClose: () => void }) {
  const { data: campaigns = [] } = useCampaigns()
  const { data: templates = [] } = useReplyTemplates()
  const createRule = useCreateMatchingRule()
  const updateRule = useUpdateMatchingRule()
  const testRule = useTestMatchingRule()
  const [name, setName] = useState(rule?.name || '新建匹配规则')
  const [campaignId, setCampaignId] = useState(rule?.campaign_id || defaultCampaignId)
  const [templateId, setTemplateId] = useState(rule?.template_id || '')
  const [pattern, setPattern] = useState(rule?.pattern || '')
  const [matchType, setMatchType] = useState<MatchingRule['match_type']>(rule?.match_type || 'contains')
  const [priority, setPriority] = useState(rule?.priority || 100)
  const [status, setStatus] = useState<MatchingRule['status']>(rule?.status || 'active')
  const [testComment, setTestComment] = useState('')

  useEffect(() => {
    if (!campaignId && campaigns[0]) setCampaignId(campaigns[0].id)
    if (!templateId && templates[0]) setTemplateId(templates[0].id)
  }, [campaignId, campaigns, templateId, templates])

  const save = async () => {
    const data = { campaign_id: campaignId, name, pattern, match_type: matchType, template_id: templateId, priority, status }
    if (rule) await updateRule.mutateAsync({ id: rule.id, data })
    else await createRule.mutateAsync(data)
    onClose()
  }

  const runTest = () => {
    if (!testComment || !pattern) return
    testRule.mutate({ pattern, match_type: matchType, comment_text: testComment })
  }

  return (
    <div className="fixed inset-0 z-40 flex min-h-0 flex-col overflow-hidden bg-white shadow-xl md:inset-y-0 md:left-auto md:right-0 md:w-[500px] md:border-l" style={{ borderColor: 'var(--border)' }}>
      <div className="flex shrink-0 items-center justify-between border-b px-4 py-3" style={{ borderColor: 'var(--border)' }}>
        <h3 className="font-semibold text-gray-900">{rule ? '编辑匹配规则' : '新建匹配规则'}</h3>
        <button className="p-2 text-gray-400 hover:text-gray-600" onClick={onClose} style={{ minHeight: 44, minWidth: 44 }}><X size={16} /></button>
      </div>
      <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="规则名称" span={2}><input value={name} onChange={(e) => setName(e.target.value)} className={inp} /></Field>
          <Field label="关联活动"><select value={campaignId} onChange={(e) => setCampaignId(e.target.value)} className={inp}>{campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></Field>
          <Field label="优先级"><input type="number" value={priority} min={1} onChange={(e) => setPriority(Number(e.target.value) || 100)} className={inp} /></Field>
          <Field label="回复模板" span={2}><select value={templateId} onChange={(e) => setTemplateId(e.target.value)} className={inp}>{templates.length === 0 && <option value="">请先创建回复模板</option>}{templates.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}</select></Field>
          <Field label="匹配类型"><select value={matchType} onChange={(e) => setMatchType(e.target.value as MatchingRule['match_type'])} className={inp}><option value="contains">包含任意关键词</option><option value="exact">精确文本</option><option value="regex">正则表达式</option></select></Field>
          <Field label="状态"><select value={status} onChange={(e) => setStatus(e.target.value as MatchingRule['status'])} className={inp}><option value="active">启用</option><option value="paused">停用</option></select></Field>
          <Field label="匹配内容" span={2}><input value={pattern} onChange={(e) => setPattern(e.target.value)} placeholder="price, quote, supplier" className={inp} /></Field>
        </div>
        <div className="rounded-xl border p-4" style={{ background: '#f8f9fb', borderColor: 'var(--border)' }}>
          <div className="mb-3 text-sm font-semibold text-gray-800">规则测试</div>
          <textarea value={testComment} onChange={(e) => setTestComment(e.target.value)} rows={3} placeholder="输入一段评论内容..." className={`${inp} resize-none`} />
          <button className="mt-3 w-full rounded-lg px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50" style={{ background: 'var(--primary)', minHeight: 44 }} disabled={!testComment || !pattern || testRule.isPending} onClick={runTest}>运行测试</button>
          {testRule.data && <div className="mt-3 flex items-center gap-2 rounded-lg p-3 text-sm font-medium" style={{ background: testRule.data.matched ? '#ecfdf5' : '#f3f4f6', color: testRule.data.matched ? '#15803d' : '#4b5563' }}>{testRule.data.matched ? <><CheckCircle size={14} /> 规则匹配</> : <><XCircle size={14} /> 未匹配</>}</div>}
        </div>
      </div>
      <div className="flex shrink-0 flex-col justify-end gap-2 border-t p-4 md:flex-row" style={{ borderColor: 'var(--border)' }}>
        <button className="rounded-xl border px-4 py-3 text-sm hover:bg-gray-50 md:rounded-lg md:py-2" style={{ borderColor: 'var(--border)', minHeight: 44 }} onClick={onClose}>取消</button>
        <button className="rounded-xl px-4 py-3 text-sm font-medium text-white disabled:opacity-50 md:rounded-lg md:py-2" style={{ background: 'var(--primary)', minHeight: 44 }} disabled={!campaignId || !templateId || !name || !pattern || createRule.isPending || updateRule.isPending} onClick={save}>保存规则</button>
      </div>
    </div>
  )
}

export default function MatchingRules() {
  const { data: campaigns = [] } = useCampaigns()
  const [campaignId, setCampaignId] = useState('')
  const { data: rules = [], isLoading, error } = useMatchingRules(campaignId || undefined)
  const deleteRule = useDeleteMatchingRule()
  const [drawerRule, setDrawerRule] = useState<MatchingRule | null | undefined>(undefined)
  const [search, setSearch] = useState('')
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const campaignById = useMemo(() => new Map(campaigns.map((c) => [c.id, c.name])), [campaigns])

  useEffect(() => {
    if (!campaignId && campaigns[0]) setCampaignId(campaigns[0].id)
  }, [campaignId, campaigns])

  const filtered = rules.filter((r) => !search || r.name.toLowerCase().includes(search.toLowerCase()) || r.pattern.toLowerCase().includes(search.toLowerCase()))

  return (
    <div className="flex min-h-full flex-col">
      <div className="flex flex-1 flex-col gap-4 p-4 md:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><h1 className="text-xl font-semibold text-gray-900">匹配规则</h1><p className="mt-0.5 hidden text-sm text-gray-500 md:block">通过真实规则筛选潜在线索，并绑定回复模板。</p></div>
          <button className="flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2.5 text-sm font-medium text-white" style={{ background: 'var(--primary)', minHeight: 44 }} onClick={() => setDrawerRule(null)}><Plus size={14} />新建规则</button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select value={campaignId} onChange={(e) => setCampaignId(e.target.value)} className={inp} style={{ maxWidth: 320, borderColor: 'var(--border)', minHeight: 44 }}>{campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
          <div className="relative" style={{ maxWidth: 280 }}>
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="搜索规则..." className="w-full rounded-lg border bg-white py-2.5 pl-8 pr-3 text-sm focus:outline-none" style={{ borderColor: 'var(--border)', minHeight: 44 }} />
          </div>
          <span className="ml-auto text-xs text-gray-400">{filtered.length} 条规则</span>
        </div>
        {error && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">规则加载失败，请刷新重试</div>}
        <div className="hidden overflow-hidden rounded-xl border bg-white md:block" style={{ borderColor: 'var(--border)' }}>
          {isLoading ? <div className="p-4 text-sm text-gray-500">正在加载规则...</div> : (
            <table className="w-full min-w-[760px] text-sm">
              <thead><tr className="border-b bg-gray-50 text-left" style={{ borderColor: 'var(--border)' }}>{['优先级', '规则名称', '关联活动', '匹配内容', '模板', '状态', '操作'].map((h) => <th key={h} className="px-4 py-3 text-xs font-semibold text-gray-500">{h}</th>)}</tr></thead>
              <tbody>{filtered.map((r) => <tr key={r.id} className="border-b last:border-0 hover:bg-gray-50" style={{ borderColor: 'var(--border)' }}>
                <td className="px-4 py-3 text-center font-mono text-gray-500">{r.priority}</td>
                <td className="px-4 py-3 font-medium text-gray-800">{r.name}</td>
                <td className="px-4 py-3 text-xs text-gray-500">{r.campaign_id ? campaignById.get(r.campaign_id) || r.campaign_id : '全部活动'}</td>
                <td className="max-w-[260px] truncate px-4 py-3 text-xs text-gray-500">{r.pattern || '—'}</td>
                <td className="px-4 py-3 font-mono text-xs text-gray-500">{r.template_id || '—'}</td>
                <td className="px-4 py-3"><StatusBadge status={r.status === 'active' ? '已启用' : '已停用'} /></td>
                <td className="px-4 py-3"><div className="flex gap-1"><button className="rounded-lg p-2 text-gray-400 hover:bg-indigo-50 hover:text-indigo-600" onClick={() => setDrawerRule(r)}><Edit3 size={13} /></button><button className="rounded-lg p-2 text-gray-400 hover:bg-red-50 hover:text-red-600" onClick={() => setDeleteId(r.id)}><Trash2 size={13} /></button></div></td>
              </tr>)}</tbody>
            </table>
          )}
          {!isLoading && filtered.length === 0 && <div className="p-8 text-center text-sm text-gray-400">暂无匹配规则</div>}
        </div>
        <div className="flex flex-col gap-3 md:hidden">
          {filtered.map((r) => <div key={r.id} className="rounded-xl border bg-white p-4" style={{ borderColor: 'var(--border)' }}><div className="flex justify-between gap-2"><div className="min-w-0"><div className="font-medium text-gray-800">{r.name}</div><div className="mt-1 truncate text-xs text-gray-500">{r.pattern || '—'}</div></div><StatusBadge status={r.status === 'active' ? '已启用' : '已停用'} /></div><div className="mt-3 flex gap-2"><button className="flex-1 rounded-xl border py-2.5 text-xs" style={{ borderColor: 'var(--border)' }} onClick={() => setDrawerRule(r)}>编辑</button><button className="flex-1 rounded-xl border py-2.5 text-xs text-red-500" style={{ borderColor: '#fca5a5' }} onClick={() => setDeleteId(r.id)}>删除</button></div></div>)}
        </div>
      </div>
      {drawerRule !== undefined && <><div className="fixed inset-0 z-30 bg-black/20" onClick={() => setDrawerRule(undefined)} /><RuleDrawer rule={drawerRule} defaultCampaignId={campaignId} onClose={() => setDrawerRule(undefined)} /></>}
      <ConfirmModal open={deleteId !== null} title="删除规则" description="删除后该规则不再参与回复候选匹配。" confirmLabel="删除" destructive onConfirm={() => { if (deleteId) deleteRule.mutate(deleteId); setDeleteId(null) }} onCancel={() => setDeleteId(null)} />
    </div>
  )
}

function Field({ label, children, span }: { label: string; children: React.ReactNode; span?: number }) {
  return <div className={`flex flex-col gap-1${span === 2 ? ' col-span-2' : ''}`}><label className="text-xs font-medium text-gray-600">{label}</label>{children}</div>
}
