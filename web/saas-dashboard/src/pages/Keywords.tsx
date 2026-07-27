import { useState } from 'react'
import { Plus, Search, Trash2, Edit3, ChevronUp, ChevronDown, X, AlertCircle, CheckCircle } from 'lucide-react'
import TopBar from '../components/layout/TopBar'
import StatusBadge from '../components/ui/StatusBadge'
import ConfirmModal from '../components/ui/ConfirmModal'

const initialKeywords = [
  { id: 1, keyword: '跨境电商', campaign: '跨境电商引流', priority: 1, enabled: true, matchCount: 312, updated: '2025-07-20' },
  { id: 2, keyword: '代购', campaign: '跨境电商引流', priority: 2, enabled: true, matchCount: 198, updated: '2025-07-20' },
  { id: 3, keyword: '海淘', campaign: '跨境电商引流', priority: 3, enabled: true, matchCount: 87, updated: '2025-07-18' },
  { id: 4, keyword: 'independent site', campaign: '独立站获客', priority: 1, enabled: true, matchCount: 143, updated: '2025-07-15' },
  { id: 5, keyword: 'dropshipping', campaign: '独立站获客', priority: 2, enabled: false, matchCount: 62, updated: '2025-07-10' },
  { id: 6, keyword: '合作', campaign: '海外招商合作', priority: 1, enabled: true, matchCount: 201, updated: '2025-07-12' },
  { id: 7, keyword: '批发', campaign: '海外招商合作', priority: 2, enabled: true, matchCount: 156, updated: '2025-07-08' },
]

interface BatchDrawerProps {
  onClose: () => void
  onSave: (kws: string[]) => void
}

function BatchDrawer({ onClose, onSave }: BatchDrawerProps) {
  const [text, setText] = useState('')
  const [campaign, setCampaign] = useState('跨境电商引流')

  const raw = text.split(/[\n,]/).map((s) => s.trim()).filter(Boolean)
  const unique = [...new Set(raw)]
  const dups = raw.filter((k, i) => raw.indexOf(k) !== i)
  const invalids = unique.filter((k) => k.length < 2 || k.length > 50)
  const valid = unique.filter((k) => !invalids.includes(k))

  return (
    <div
      className="fixed inset-0 md:inset-y-0 md:right-0 md:left-auto z-50 flex flex-col bg-white md:w-[440px] shadow-xl border-l"
      style={{ borderColor: 'var(--border)' }}
    >
      <div className="flex items-center justify-between px-5 py-4 border-b shrink-0" style={{ borderColor: 'var(--border)' }}>
        <h3 className="font-semibold text-gray-900">批量添加关键词</h3>
        <button className="p-2 text-gray-400 hover:text-gray-600" onClick={onClose} style={{ minHeight: 44, minWidth: 44 }}>
          <X size={16} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium text-gray-700">关联活动</label>
          <select className={inp} value={campaign} onChange={(e) => setCampaign(e.target.value)}>
            {['跨境电商引流', '独立站获客', '海外招商合作', '全部活动'].map((c) => <option key={c}>{c}</option>)}
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium text-gray-700">关键词列表</label>
          <p className="text-xs text-gray-400">每行一个，或用英文逗号分隔</p>
          <textarea
            rows={10}
            placeholder="跨境电商&#10;代购&#10;海淘&#10;dropshipping"
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="px-3 py-2.5 text-sm border rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-none font-mono"
            style={{ borderColor: 'var(--border)' }}
          />
        </div>
        {text && (
          <div className="border rounded-xl p-4 flex flex-col gap-2" style={{ background: '#f8f9fb', borderColor: 'var(--border)' }}>
            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider">预览</div>
            <div className="flex flex-wrap gap-1.5">
              {valid.map((k) => (
                <span key={k} className="px-2 py-0.5 rounded text-xs" style={{ background: '#dcfce7', color: '#15803d' }}>{k}</span>
              ))}
              {invalids.map((k) => (
                <span key={k} className="px-2 py-0.5 rounded text-xs" style={{ background: '#fee2e2', color: '#dc2626' }}>{k}</span>
              ))}
            </div>
            <div className="text-xs text-gray-500 mt-1 flex gap-3">
              <span><span className="font-medium text-gray-800">{valid.length}</span> 个有效</span>
              {dups.length > 0 && <span className="text-amber-600">{dups.length} 个重复已去除</span>}
              {invalids.length > 0 && <span className="text-red-500">{invalids.length} 个无效</span>}
            </div>
          </div>
        )}
      </div>
      <div className="border-t p-4 flex gap-2 shrink-0" style={{ borderColor: 'var(--border)' }}>
        <button className="flex-1 px-4 py-2.5 text-sm border rounded-lg hover:bg-gray-50" style={{ borderColor: 'var(--border)', minHeight: 44 }} onClick={onClose}>
          取消
        </button>
        <button
          className="flex-1 px-4 py-2.5 text-sm font-medium rounded-lg text-white hover:opacity-90 disabled:opacity-50"
          style={{ background: 'var(--primary)', minHeight: 44 }}
          disabled={valid.length === 0}
          onClick={() => { onSave(valid); onClose() }}
        >
          添加 {valid.length > 0 ? `${valid.length} 个` : ''}关键词
        </button>
      </div>
    </div>
  )
}

const inp = "w-full px-3 py-2 text-sm border rounded-lg bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"

export default function Keywords({ onMenuOpen }: { onMenuOpen?: () => void }) {
  const [keywords, setKeywords] = useState(initialKeywords)
  const [search, setSearch] = useState('')
  const [campaignFilter, setCampaignFilter] = useState('全部')
  const [batchOpen, setBatchOpen] = useState(false)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const filtered = keywords.filter((k) => {
    if (search && !k.keyword.toLowerCase().includes(search.toLowerCase())) return false
    if (campaignFilter !== '全部' && k.campaign !== campaignFilter) return false
    return true
  })

  const handleDelete = (id: number) => {
    setKeywords((prev) => prev.filter((k) => k.id !== id))
    setDeleteId(null)
  }

  const handleBatchSave = (kws: string[]) => {
    const newKws = kws.map((k, i) => ({
      id: Date.now() + i,
      keyword: k,
      campaign: '跨境电商引流',
      priority: keywords.length + i + 1,
      enabled: true,
      matchCount: 0,
      updated: new Date().toISOString().slice(0, 10),
    }))
    setKeywords((prev) => [...prev, ...newKws])
  }

  const toggleEnabled = (id: number) => {
    setKeywords((prev) => prev.map((k) => k.id === id ? { ...k, enabled: !k.enabled } : k))
  }

  return (
    <div className="flex flex-col min-h-screen">
      <TopBar breadcrumbs={['获客管理', '关键词']} pageTitle="关键词" onMenuOpen={onMenuOpen} />
      <div className="flex-1 p-4 md:p-6 flex flex-col gap-4">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div>
            <h1 className="text-lg md:text-xl font-semibold text-gray-900">关键词</h1>
            <p className="text-sm text-gray-500 mt-0.5 hidden md:block">管理用于搜索和匹配社媒内容的关键词列表</p>
          </div>
          <div className="flex gap-2">
            <button
              className="flex items-center gap-1.5 px-3 py-2 text-sm border rounded-lg hover:bg-gray-50"
              style={{ borderColor: 'var(--border)', minHeight: 44 }}
              onClick={() => setBatchOpen(true)}
            >
              <Plus size={14} />
              批量添加
            </button>
            <button
              className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg text-white hover:opacity-90"
              style={{ background: 'var(--primary)', minHeight: 44 }}
              onClick={() => setBatchOpen(true)}
            >
              <Plus size={14} />
              添加关键词
            </button>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative flex-1 min-w-0 md:flex-none">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="搜索关键词..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 pr-3 py-2 text-sm border rounded-lg bg-white focus:outline-none w-full"
              style={{ borderColor: 'var(--border)', minHeight: 44 }}
            />
          </div>
          <select
            value={campaignFilter}
            onChange={(e) => setCampaignFilter(e.target.value)}
            className="px-3 py-2 text-sm border rounded-lg bg-white focus:outline-none"
            style={{ borderColor: 'var(--border)', minHeight: 44 }}
          >
            {['全部', '跨境电商引流', '独立站获客', '海外招商合作'].map((c) => <option key={c}>{c}</option>)}
          </select>
        </div>

        {/* Desktop table */}
        <div className="hidden md:block bg-white border rounded-xl overflow-hidden" style={{ borderColor: 'var(--border)' }}>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b" style={{ borderColor: 'var(--border)', background: '#fafafa' }}>
                {['优先级', '关键词', '关联活动', '启用', '命中次数', '更新时间', '操作'].map((h) => (
                  <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-gray-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((k) => (
                <tr key={k.id} className="border-b last:border-0 hover:bg-gray-50" style={{ borderColor: 'var(--border)' }}>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <button className="p-0.5 rounded hover:bg-gray-200 text-gray-400"><ChevronUp size={11} /></button>
                      <span className="text-xs font-mono text-gray-600 w-4 text-center">{k.priority}</span>
                      <button className="p-0.5 rounded hover:bg-gray-200 text-gray-400"><ChevronDown size={11} /></button>
                    </div>
                  </td>
                  <td className="px-4 py-3 font-medium text-gray-800">{k.keyword}</td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{k.campaign}</td>
                  <td className="px-4 py-3">
                    <div
                      className="w-9 h-5 rounded-full relative cursor-pointer transition-colors"
                      style={{ background: k.enabled ? 'var(--primary)' : '#d1d5db' }}
                      onClick={() => toggleEnabled(k.id)}
                    >
                      <div className="absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all" style={{ left: k.enabled ? 20 : 2 }} />
                    </div>
                  </td>
                  <td className="px-4 py-3 text-gray-600 font-medium">{k.matchCount}</td>
                  <td className="px-4 py-3 text-gray-400 text-xs">{k.updated}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <button className="p-1.5 rounded hover:bg-gray-100 text-gray-400"><Edit3 size={13} /></button>
                      <button className="p-1.5 rounded hover:bg-red-50 text-gray-400 hover:text-red-400" onClick={() => setDeleteId(k.id)}>
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Mobile cards */}
        <div className="md:hidden flex flex-col gap-2">
          {filtered.map((k) => (
            <div key={k.id} className="bg-white border rounded-xl p-4" style={{ borderColor: 'var(--border)' }}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="font-medium text-gray-900 truncate">{k.keyword}</div>
                  <div className="text-xs text-gray-500 mt-0.5">{k.campaign}</div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <div
                    className="w-9 h-5 rounded-full relative cursor-pointer"
                    style={{ background: k.enabled ? 'var(--primary)' : '#d1d5db' }}
                    onClick={() => toggleEnabled(k.id)}
                  >
                    <div className="absolute top-0.5 w-4 h-4 rounded-full bg-white" style={{ left: k.enabled ? 20 : 2 }} />
                  </div>
                </div>
              </div>
              <div className="flex items-center justify-between mt-3">
                <div className="text-xs text-gray-400">命中 {k.matchCount} 次 · 优先级 {k.priority}</div>
                <div className="flex gap-1">
                  <button className="p-2 rounded-lg hover:bg-gray-100 text-gray-400" style={{ minHeight: 44, minWidth: 44 }}><Edit3 size={14} /></button>
                  <button className="p-2 rounded-lg hover:bg-red-50 text-gray-400 hover:text-red-400" style={{ minHeight: 44, minWidth: 44 }} onClick={() => setDeleteId(k.id)}>
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            </div>
          ))}
          {filtered.length === 0 && (
            <div className="flex flex-col items-center py-16 text-gray-400">
              <Tag size={32} className="mb-3 text-gray-200" />
              <div className="text-sm">暂无关键词</div>
            </div>
          )}
        </div>
      </div>

      {batchOpen && <BatchDrawer onClose={() => setBatchOpen(false)} onSave={handleBatchSave} />}
      {batchOpen && <div className="fixed inset-0 bg-black/20 z-40 hidden md:block" onClick={() => setBatchOpen(false)} />}

      <ConfirmModal
        open={deleteId !== null}
        title="确认删除关键词"
        description="删除后该关键词将不再参与活动匹配，此操作不可撤销。"
        confirmLabel="删除"
        destructive
        onConfirm={() => deleteId && handleDelete(deleteId)}
        onCancel={() => setDeleteId(null)}
      />
    </div>
  )
}

function Tag({ size, className }: { size: number; className?: string }) {
  return <svg width={size} height={size} className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" /><line x1="7" y1="7" x2="7.01" y2="7" /></svg>
}
