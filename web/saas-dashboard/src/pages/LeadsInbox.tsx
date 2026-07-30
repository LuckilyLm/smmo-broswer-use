import { useEffect, useMemo, useState } from 'react'
import { ArrowLeft, CheckCircle, Search, XCircle } from 'lucide-react'

import { useLead, useLeads, useMarkLeadContacted, useMarkLeadInvalid, type Lead } from '../api/leads'
import StatusBadge from '../components/ui/StatusBadge'

function intentLabel(value?: string | null) {
  const map: Record<string, string> = { high: '高意向', medium: '中意向', low: '低意向', none: '无意向' }
  return map[value || ''] || value || '—'
}

function statusLabel(value?: string | null) {
  const map: Record<string, string> = { new: '未联系', assigned: '已分配', contacted: '已联系', invalid: '无效', blocked: '已阻止', qualified: '已确认' }
  return map[value || ''] || value || '—'
}

function formatDate(value?: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

export default function LeadsInbox() {
  const [intentFilter, setIntentFilter] = useState('')
  const [search, setSearch] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [mobileView, setMobileView] = useState<'list' | 'detail'>('list')
  const filters = useMemo(() => ({ intent_level: intentFilter || undefined, search: search || undefined }), [intentFilter, search])
  const { data, isLoading, error } = useLeads(filters)
  const leads = data?.items || []
  const { data: selected, isLoading: selectedLoading, error: selectedError } = useLead(selectedId || '')
  const contacted = useMarkLeadContacted()
  const invalid = useMarkLeadInvalid()

  useEffect(() => {
    if (!selectedId && leads[0]) setSelectedId(leads[0].id)
  }, [leads, selectedId])

  const choose = (id: string) => {
    setSelectedId(id)
    setMobileView('detail')
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      {mobileView === 'detail' && <div className="flex items-center gap-2 border-b bg-white px-4 py-2 md:hidden" style={{ borderColor: 'var(--border)' }}><button className="flex items-center gap-1.5 text-sm font-medium" style={{ color: 'var(--primary)', minHeight: 44 }} onClick={() => setMobileView('list')}><ArrowLeft size={16} />返回列表</button></div>}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <div className={`${mobileView === 'list' ? 'flex' : 'hidden'} w-full flex-col border-r md:flex md:w-[400px] md:shrink-0 xl:w-[420px]`} style={{ borderColor: 'var(--border)' }}>
          <div className="flex h-full w-full flex-col md:w-80">
            <div className="flex shrink-0 flex-col gap-2 border-b p-3" style={{ borderColor: 'var(--border)' }}>
              <div className="relative">
                <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
                <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="搜索线索..." className="w-full rounded-lg border py-2 pl-7 pr-3 text-xs focus:outline-none" style={{ borderColor: 'var(--border)', minHeight: 40 }} />
              </div>
              <div className="flex flex-wrap gap-1">
                {[['', '全部'], ['high', '高意向'], ['medium', '中意向'], ['low', '低意向'], ['none', '无意向']].map(([value, label]) => <button key={value} className="rounded-lg px-2.5 py-1.5 text-xs" style={{ background: intentFilter === value ? 'var(--primary)' : '#f3f4f6', color: intentFilter === value ? 'white' : '#6b7280', minHeight: 36 }} onClick={() => setIntentFilter(value)}>{label}</button>)}
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto">
              {isLoading && <div className="p-4 text-sm text-gray-500">正在加载线索...</div>}
              {error && <div className="m-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">线索加载失败</div>}
              {!isLoading && leads.length === 0 && <div className="py-16 text-center text-sm text-gray-400">暂无线索</div>}
              {leads.map((lead) => <LeadRow key={lead.id} lead={lead} active={lead.id === selectedId} onClick={() => choose(lead.id)} />)}
            </div>
          </div>
        </div>
        <div className={`${mobileView === 'detail' ? 'flex' : 'hidden'} min-w-0 flex-1 flex-col overflow-hidden bg-white md:flex`}>
          {selectedLoading ? <div className="flex flex-1 items-center justify-center text-sm text-gray-400">正在加载线索详情...</div> : selectedError ? <div className="flex flex-1 items-center justify-center p-6 text-sm text-red-500">线索详情加载失败，请重新选择左侧线索。</div> : !selected ? <div className="flex flex-1 items-center justify-center text-sm text-gray-400">请选择左侧线索查看详情</div> : (
            <>
              <div className="shrink-0 border-b p-4" style={{ borderColor: 'var(--border)' }}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0"><h1 className="truncate text-lg font-semibold text-gray-900">{selected.author_name || '未知作者'}</h1><p className="mt-1 text-xs text-gray-400">{selected.platform} · {formatDate(selected.created_at)}</p></div>
                  <div className="flex gap-2"><StatusBadge status={intentLabel(selected.final_intent_level)} /><StatusBadge status={statusLabel(selected.status)} /></div>
                </div>
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto p-4">
                <section className="rounded-xl border p-4" style={{ borderColor: 'var(--border)' }}>
                  <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">原始评论</div>
                  <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-800">{selected.comment_text || '—'}</p>
                  {selected.matched_search_keywords?.length > 0 && <div className="mt-3 flex flex-wrap gap-1.5">{selected.matched_search_keywords.map((kw) => <span key={kw} className="rounded bg-indigo-50 px-2 py-0.5 text-xs text-indigo-600">{kw}</span>)}</div>}
                </section>
                <section className="mt-4 rounded-xl border p-4" style={{ borderColor: 'var(--border)' }}>
                  <div className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">线索信息</div>
                  <div className="grid grid-cols-1 gap-3 text-sm md:grid-cols-2">
                    <Info label="活动 ID" value={selected.campaign_id} mono />
                    <Info label="平台" value={selected.platform} />
                    <Info label="系统意向" value={intentLabel(selected.final_intent_level)} />
                    <Info label="人工意向" value={intentLabel(selected.manual_intent_level)} />
                    <Info label="状态" value={statusLabel(selected.status)} />
                    <Info label="更新时间" value={formatDate(selected.updated_at)} />
                  </div>
                </section>
                <div className="mt-4 flex flex-wrap gap-2">
                  <button className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm text-white disabled:opacity-50" style={{ background: 'var(--primary)', minHeight: 44 }} disabled={contacted.isPending} onClick={() => contacted.mutate(selected.id)}><CheckCircle size={14} />标记已联系</button>
                  <button className="flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm text-red-500 disabled:opacity-50" style={{ borderColor: '#fca5a5', minHeight: 44 }} disabled={invalid.isPending} onClick={() => invalid.mutate({ id: selected.id, reason: '人工标记无效' })}><XCircle size={14} />标记无效</button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function LeadRow({ lead, active, onClick }: { lead: Lead; active: boolean; onClick: () => void }) {
  return <button className="w-full border-b p-3 text-left hover:bg-gray-50" style={{ borderColor: 'var(--border)', background: active ? 'var(--accent)' : 'white' }} onClick={onClick}><div className="flex items-start justify-between gap-2"><div className="min-w-0"><div className="truncate text-sm font-medium text-gray-900">{lead.author_name || '未知作者'}</div><div className="mt-1 line-clamp-2 text-xs text-gray-500">{lead.comment_text || '—'}</div></div><StatusBadge status={intentLabel(lead.final_intent_level)} /></div><div className="mt-2 flex items-center justify-between text-[11px] text-gray-400"><span>{lead.platform}</span><span>{formatDate(lead.created_at)}</span></div></button>
}

function Info({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div className="min-w-0"><div className="text-xs text-gray-400">{label}</div><div className={`mt-1 truncate text-sm text-gray-800 ${mono ? 'font-mono text-xs' : ''}`}>{value || '—'}</div></div>
}
