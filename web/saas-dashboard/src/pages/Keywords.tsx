import { useEffect, useMemo, useState } from 'react'
import { ChevronDown, ChevronUp, Plus, Search, Tag, Trash2, X } from 'lucide-react'

import { useCampaigns } from '../api/campaigns'
import { useBulkCreateKeywords, useDeleteKeyword, useKeywords, useUpdateKeyword, type Keyword } from '../api/keywords'
import ConfirmModal from '../components/ui/ConfirmModal'

const inp = "w-full px-3 py-2 text-sm border rounded-lg bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"

interface BatchDrawerProps {
  campaignId: string
  onClose: () => void
  onSave: (campaignId: string, kws: string[]) => void
}

function BatchDrawer({ campaignId, onClose, onSave }: BatchDrawerProps) {
  const [text, setText] = useState('')
  const raw = text.split(/[\n,]/).map((s) => s.trim()).filter(Boolean)
  const unique = [...new Set(raw)]
  const invalids = unique.filter((k) => k.length < 1 || k.length > 255)
  const valid = unique.filter((k) => !invalids.includes(k))

  return (
    <div className="fixed inset-0 z-50 flex min-h-0 flex-col overflow-hidden bg-white shadow-xl md:inset-y-0 md:left-auto md:right-0 md:w-[440px] md:border-l" style={{ borderColor: 'var(--border)' }}>
      <div className="flex shrink-0 items-center justify-between border-b px-5 py-4" style={{ borderColor: 'var(--border)' }}>
        <h3 className="font-semibold text-gray-900">批量添加关键词</h3>
        <button className="p-2 text-gray-400 hover:text-gray-600" onClick={onClose} style={{ minHeight: 44, minWidth: 44 }}><X size={16} /></button>
      </div>
      <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-5">
        <div className="text-xs text-gray-500">关键词会添加到当前选择的营销活动中。每行一个，或用英文逗号分隔。</div>
        <textarea rows={12} value={text} onChange={(e) => setText(e.target.value)} placeholder="aluminum extrusion supplier&#10;steel pipe supplier" className="resize-none rounded-lg border px-3 py-2.5 font-mono text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500" style={{ borderColor: 'var(--border)' }} />
        {text && (
          <div className="rounded-xl border p-4" style={{ background: '#f8f9fb', borderColor: 'var(--border)' }}>
            <div className="mb-2 text-xs font-semibold text-gray-500">预览</div>
            <div className="flex flex-wrap gap-1.5">
              {valid.map((k) => <span key={k} className="rounded bg-green-100 px-2 py-0.5 text-xs text-green-700">{k}</span>)}
              {invalids.map((k) => <span key={k} className="rounded bg-red-100 px-2 py-0.5 text-xs text-red-600">{k}</span>)}
            </div>
            <div className="mt-2 text-xs text-gray-500">有效 {valid.length} 个，重复会自动去除。</div>
          </div>
        )}
      </div>
      <div className="flex shrink-0 gap-2 border-t p-4" style={{ borderColor: 'var(--border)' }}>
        <button className="flex-1 rounded-lg border px-4 py-2.5 text-sm hover:bg-gray-50" style={{ borderColor: 'var(--border)', minHeight: 44 }} onClick={onClose}>取消</button>
        <button className="flex-1 rounded-lg px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50" style={{ background: 'var(--primary)', minHeight: 44 }} disabled={!campaignId || valid.length === 0} onClick={() => onSave(campaignId, valid)}>添加 {valid.length || ''} 个</button>
      </div>
    </div>
  )
}

export default function Keywords() {
  const { data: campaigns = [], isLoading: campaignsLoading } = useCampaigns()
  const [campaignId, setCampaignId] = useState('')
  const { data: keywords = [], isLoading, error } = useKeywords(campaignId)
  const updateKeyword = useUpdateKeyword()
  const deleteKeyword = useDeleteKeyword()
  const bulkCreate = useBulkCreateKeywords()
  const [search, setSearch] = useState('')
  const [batchOpen, setBatchOpen] = useState(false)
  const [deleteId, setDeleteId] = useState<string | null>(null)

  useEffect(() => {
    if (!campaignId && campaigns.length > 0) setCampaignId(campaigns[0].id)
  }, [campaignId, campaigns])

  const campaignById = useMemo(() => new Map(campaigns.map((c) => [c.id, c])), [campaigns])
  const filtered = keywords.filter((k) => !search || k.keyword.toLowerCase().includes(search.toLowerCase()))

  const changePriority = (item: Keyword, delta: number) => {
    updateKeyword.mutate({ id: item.id, data: { priority: Math.max(1, item.priority + delta) } })
  }

  return (
    <div className="flex min-h-full flex-col">
      <div className="flex flex-1 flex-col gap-4 p-4 md:p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h1 className="text-lg font-semibold text-gray-900 md:text-xl">关键词</h1>
            <p className="mt-0.5 hidden text-sm text-gray-500 md:block">管理真实营销活动的搜索关键词</p>
          </div>
          <button className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-white disabled:opacity-50" style={{ background: 'var(--primary)', minHeight: 44 }} disabled={!campaignId} onClick={() => setBatchOpen(true)}>
            <Plus size={14} /> 添加关键词
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <select value={campaignId} onChange={(e) => setCampaignId(e.target.value)} className={inp} style={{ maxWidth: 320, borderColor: 'var(--border)', minHeight: 44 }}>
            {campaignsLoading && <option>正在加载活动...</option>}
            {campaigns.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
          <div className="relative min-w-0 flex-1 md:flex-none">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="搜索关键词..." className="w-full rounded-lg border bg-white py-2 pl-8 pr-3 text-sm focus:outline-none md:w-64" style={{ borderColor: 'var(--border)', minHeight: 44 }} />
          </div>
          <span className="ml-auto text-xs text-gray-400">{filtered.length} 个关键词</span>
        </div>

        {error && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">关键词加载失败，请刷新重试</div>}

        <div className="hidden overflow-hidden rounded-xl border bg-white md:block" style={{ borderColor: 'var(--border)' }}>
          {isLoading ? <div className="p-4 text-sm text-gray-500">正在加载关键词...</div> : (
            <table className="w-full text-sm">
              <thead><tr className="border-b bg-gray-50" style={{ borderColor: 'var(--border)' }}>{['优先级', '关键词', '关联活动', '启用', '更新时间', '操作'].map((h) => <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500">{h}</th>)}</tr></thead>
              <tbody>
                {filtered.map((k) => (
                  <tr key={k.id} className="border-b last:border-0 hover:bg-gray-50" style={{ borderColor: 'var(--border)' }}>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <button className="rounded p-1 text-gray-400 hover:bg-gray-200" onClick={() => changePriority(k, -1)}><ChevronUp size={12} /></button>
                        <span className="w-8 text-center font-mono text-xs text-gray-600">{k.priority}</span>
                        <button className="rounded p-1 text-gray-400 hover:bg-gray-200" onClick={() => changePriority(k, 1)}><ChevronDown size={12} /></button>
                      </div>
                    </td>
                    <td className="px-4 py-3 font-medium text-gray-800">{k.keyword}</td>
                    <td className="px-4 py-3 text-xs text-gray-500">{campaignById.get(k.campaign_id)?.name || k.campaign_id}</td>
                    <td className="px-4 py-3"><Switch checked={k.enabled} onClick={() => updateKeyword.mutate({ id: k.id, data: { enabled: !k.enabled } })} /></td>
                    <td className="px-4 py-3 text-xs text-gray-400">{formatDate(k.updated_at)}</td>
                    <td className="px-4 py-3">
                      <button className="rounded p-2 text-gray-400 hover:bg-red-50 hover:text-red-500" onClick={() => setDeleteId(k.id)}><Trash2 size={14} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {!isLoading && filtered.length === 0 && <Empty />}
        </div>

        <div className="flex flex-col gap-2 md:hidden">
          {filtered.map((k) => (
            <div key={k.id} className="rounded-xl border bg-white p-4" style={{ borderColor: 'var(--border)' }}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate font-medium text-gray-900">{k.keyword}</div>
                  <div className="mt-0.5 text-xs text-gray-500">{campaignById.get(k.campaign_id)?.name || k.campaign_id}</div>
                </div>
                <Switch checked={k.enabled} onClick={() => updateKeyword.mutate({ id: k.id, data: { enabled: !k.enabled } })} />
              </div>
              <div className="mt-3 flex items-center justify-between text-xs text-gray-400">
                <span>优先级 {k.priority} · {formatDate(k.updated_at)}</span>
                <button className="rounded-lg p-2 text-red-500 hover:bg-red-50" onClick={() => setDeleteId(k.id)}><Trash2 size={14} /></button>
              </div>
            </div>
          ))}
          {!isLoading && filtered.length === 0 && <Empty />}
        </div>
      </div>

      {batchOpen && <BatchDrawer campaignId={campaignId} onClose={() => setBatchOpen(false)} onSave={(id, kws) => bulkCreate.mutate({ campaignId: id, keywords: kws }, { onSuccess: () => setBatchOpen(false) })} />}
      {batchOpen && <div className="fixed inset-0 z-40 hidden bg-black/20 md:block" onClick={() => setBatchOpen(false)} />}
      <ConfirmModal open={deleteId !== null} title="确认删除关键词" description="删除后该关键词将不再参与活动搜索。" confirmLabel="删除" destructive onConfirm={() => { if (deleteId) deleteKeyword.mutate(deleteId); setDeleteId(null) }} onCancel={() => setDeleteId(null)} />
    </div>
  )
}

function Switch({ checked, onClick }: { checked: boolean; onClick: () => void }) {
  return <button className="relative h-5 w-9 rounded-full transition-colors" style={{ background: checked ? 'var(--primary)' : '#d1d5db' }} onClick={onClick}><span className="absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all" style={{ left: checked ? 18 : 2 }} /></button>
}

function Empty() {
  return <div className="flex flex-col items-center py-16 text-gray-400"><Tag size={32} className="mb-3 text-gray-200" /><div className="text-sm">暂无关键词</div></div>
}

function formatDate(value?: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
