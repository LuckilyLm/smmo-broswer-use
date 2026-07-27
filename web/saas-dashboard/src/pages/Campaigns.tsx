import { useState } from 'react'
import { Plus, Search, SlidersHorizontal, MoreHorizontal, Play, Pause, Settings2, Trash2, AlertTriangle, Copy, Calendar } from 'lucide-react'
import StatusBadge from '../components/ui/StatusBadge'
import TopBar from '../components/layout/TopBar'
import ConfirmModal from '../components/ui/ConfirmModal'

const initialCampaigns = [
  { id: 1, name: '跨境电商引流 – 全渠道', platform: 'Facebook', account: '@smmo_business', keywords: 5, status: '运行中', replyMode: '人工审批', leads: 312, pending: 5, lastRun: '10 分钟前', nextRun: '50 分钟后', owner: '王小明' },
  { id: 2, name: '独立站流量获取', platform: 'Instagram', account: '@smmo_official', keywords: 3, status: '运行中', replyMode: '人工审批', leads: 198, pending: 4, lastRun: '25 分钟前', nextRun: '35 分钟后', owner: '李美华' },
  { id: 3, name: '海外招商合作', platform: 'YouTube', account: '@smmo_channel', keywords: 7, status: '已暂停', replyMode: '已关闭', leads: 87, pending: 0, lastRun: '3 小时前', nextRun: '—', owner: '王小明' },
  { id: 4, name: 'TikTok 品牌曝光', platform: 'TikTok', account: '@smmo_tiktok', keywords: 4, status: '运行中', replyMode: '人工审批', leads: 143, pending: 2, lastRun: '1 小时前', nextRun: '2 小时后', owner: '张伟国' },
  { id: 5, name: 'X 高净值目标用户', platform: 'X', account: '@smmo_x', keywords: 6, status: '异常', replyMode: '已关闭', leads: 62, pending: 0, lastRun: '昨天', nextRun: '—', owner: '李美华' },
  { id: 6, name: '东南亚市场扩展', platform: 'Facebook', account: '@smmo_business', keywords: 9, status: '草稿', replyMode: '人工审批', leads: 0, pending: 0, lastRun: '—', nextRun: '—', owner: '王小明' },
]

const platColors: Record<string, string> = {
  Facebook: '#1877f2', Instagram: '#e1306c', TikTok: '#010101', X: '#1da1f2', YouTube: '#ff0000',
}

interface CampaignsProps {
  onNavigate: (page: string) => void
  onMenuOpen?: () => void
}

export default function Campaigns({ onNavigate, onMenuOpen }: CampaignsProps) {
  const [campaigns, setCampaigns] = useState(initialCampaigns)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('全部')
  const [platformFilter, setPlatformFilter] = useState('全部')
  const [modeFilter, setModeFilter] = useState('全部')
  const [openMenu, setOpenMenu] = useState<number | null>(null)
  const [deleteId, setDeleteId] = useState<number | null>(null)
  const [filtersOpen, setFiltersOpen] = useState(false)

  const filtered = campaigns.filter((c) => {
    if (search && !c.name.toLowerCase().includes(search.toLowerCase())) return false
    if (statusFilter !== '全部' && c.status !== statusFilter) return false
    if (platformFilter !== '全部' && c.platform !== platformFilter) return false
    if (modeFilter !== '全部' && c.replyMode !== modeFilter) return false
    return true
  })

  const handleDelete = (id: number) => {
    setCampaigns((prev) => prev.filter((c) => c.id !== id))
    setDeleteId(null)
  }

  const handleToggle = (id: number) => {
    setCampaigns((prev) => prev.map((c) =>
      c.id === id ? { ...c, status: c.status === '运行中' ? '已暂停' : '运行中' } : c
    ))
    setOpenMenu(null)
  }

  return (
    <div className="flex flex-col min-h-screen">
      <TopBar breadcrumbs={['获客管理', '营销活动']} pageTitle="营销活动" onMenuOpen={onMenuOpen} />
      <div className="flex-1 p-4 md:p-6 flex flex-col gap-4">
        <div className="flex items-center justify-between gap-2">
          <div>
            <h1 className="text-lg md:text-xl font-semibold text-gray-900">营销活动</h1>
            <p className="text-sm text-gray-500 mt-0.5 hidden md:block">管理并监控所有社媒获客活动</p>
          </div>
          <button
            className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg text-white hover:opacity-90 shrink-0"
            style={{ background: 'var(--primary)', minHeight: 44 }}
            onClick={() => onNavigate('campaign-settings')}
          >
            <Plus size={14} />
            <span className="hidden sm:inline">新建活动</span>
            <span className="sm:hidden">新建</span>
          </button>
        </div>

        {/* Toolbar */}
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative flex-1 min-w-0 md:flex-none">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="搜索活动..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 pr-3 py-2 text-sm border rounded-lg bg-white focus:outline-none w-full"
              style={{ borderColor: 'var(--border)', minHeight: 44 }}
            />
          </div>
          {/* Desktop filters */}
          <div className="hidden md:flex items-center gap-2">
            {[
              { label: '全部平台', options: ['全部', 'Facebook', 'Instagram', 'TikTok', 'X', 'YouTube'], value: platformFilter, onChange: setPlatformFilter },
              { label: '全部状态', options: ['全部', '运行中', '已暂停', '草稿', '异常'], value: statusFilter, onChange: setStatusFilter },
              { label: '全部模式', options: ['全部', '已关闭', '人工审批', '自动执行'], value: modeFilter, onChange: setModeFilter },
            ].map((f) => (
              <select key={f.label} value={f.value} onChange={(e) => f.onChange(e.target.value)} className="px-3 py-2 text-sm border rounded-lg bg-white focus:outline-none" style={{ borderColor: 'var(--border)' }}>
                {f.options.map((o) => <option key={o}>{o}</option>)}
              </select>
            ))}
          </div>
          {/* Mobile filter button */}
          <button
            className="md:hidden flex items-center gap-1.5 px-3 py-2 text-sm border rounded-lg hover:bg-gray-50 shrink-0"
            style={{ borderColor: 'var(--border)', minHeight: 44 }}
            onClick={() => setFiltersOpen(true)}
          >
            <SlidersHorizontal size={14} />
            筛选
          </button>
          <span className="ml-auto text-xs text-gray-400 shrink-0">{filtered.length} 个活动</span>
        </div>

        {/* Desktop table */}
        <div className="hidden md:block bg-white border rounded-xl overflow-hidden" style={{ borderColor: 'var(--border)' }}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" style={{ minWidth: 900 }}>
              <thead>
                <tr className="border-b" style={{ borderColor: 'var(--border)', background: '#fafafa' }}>
                  {['活动名称', '平台账号', '关键词', '状态', '回复模式', '线索', '待审批', '最近执行', '下次执行', '负责人', ''].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-gray-500 whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((c) => (
                  <tr
                    key={c.id}
                    className="border-b last:border-0 hover:bg-gray-50 cursor-pointer"
                    style={{ borderColor: 'var(--border)' }}
                    onClick={() => onNavigate('campaign-settings')}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full shrink-0" style={{ background: platColors[c.platform] }} />
                        <span className="font-medium text-gray-800 truncate max-w-[200px]">{c.name}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-500 text-xs whitespace-nowrap">{c.account}</td>
                    <td className="px-4 py-3 text-gray-600 text-center">{c.keywords}</td>
                    <td className="px-4 py-3"><StatusBadge status={c.status} variant="dot" /></td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        {c.replyMode === '自动执行' && <AlertTriangle size={11} className="text-amber-500" />}
                        <StatusBadge status={c.replyMode} />
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right font-medium text-gray-800">{c.leads}</td>
                    <td className="px-4 py-3 text-right">
                      {c.pending > 0 ? <span className="font-semibold text-amber-600">{c.pending}</span> : <span className="text-gray-300">—</span>}
                    </td>
                    <td className="px-4 py-3 text-gray-400 text-xs whitespace-nowrap">{c.lastRun}</td>
                    <td className="px-4 py-3 text-gray-400 text-xs whitespace-nowrap">{c.nextRun}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{c.owner}</td>
                    <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                      <div className="relative">
                        <button
                          className="p-1.5 rounded hover:bg-gray-100 text-gray-400"
                          onClick={() => setOpenMenu(openMenu === c.id ? null : c.id)}
                          style={{ minHeight: 32, minWidth: 32 }}
                        >
                          <MoreHorizontal size={14} />
                        </button>
                        {openMenu === c.id && (
                          <>
                            <div className="fixed inset-0 z-10" onClick={() => setOpenMenu(null)} />
                            <div className="absolute right-0 top-full mt-1 w-36 bg-white border rounded-lg shadow-lg z-20 py-1" style={{ borderColor: 'var(--border)' }}>
                              <button className="w-full text-left px-3 py-2 text-xs hover:bg-gray-50 flex items-center gap-2" onClick={() => { setOpenMenu(null); onNavigate('campaign-settings') }}><Settings2 size={12} /> 编辑设置</button>
                              <button className="w-full text-left px-3 py-2 text-xs hover:bg-gray-50 flex items-center gap-2" onClick={() => handleToggle(c.id)}>
                                {c.status === '运行中' ? <><Pause size={12} /> 暂停</> : <><Play size={12} /> 启动</>}
                              </button>
                              <button className="w-full text-left px-3 py-2 text-xs hover:bg-gray-50 flex items-center gap-2"><Copy size={12} /> 复制</button>
                              <div className="my-1 border-t" style={{ borderColor: 'var(--border)' }} />
                              <button className="w-full text-left px-3 py-2 text-xs hover:bg-red-50 flex items-center gap-2 text-red-500" onClick={() => { setDeleteId(c.id); setOpenMenu(null) }}><Trash2 size={12} /> 删除</button>
                            </div>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Mobile cards */}
        <div className="md:hidden flex flex-col gap-2">
          {filtered.map((c) => (
            <div
              key={c.id}
              className="bg-white border rounded-xl p-4 cursor-pointer"
              style={{ borderColor: 'var(--border)' }}
              onClick={() => onNavigate('campaign-settings')}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <div className="w-2 h-2 rounded-full shrink-0" style={{ background: platColors[c.platform] }} />
                  <span className="font-medium text-gray-900 truncate">{c.name}</span>
                </div>
                <StatusBadge status={c.status} variant="dot" />
              </div>
              <div className="flex items-center gap-3 mt-2 text-xs text-gray-500 flex-wrap">
                <span>{c.account}</span>
                <StatusBadge status={c.replyMode} />
              </div>
              <div className="flex items-center justify-between mt-3">
                <div className="flex gap-4 text-xs">
                  <span className="text-gray-600">线索 <span className="font-semibold text-gray-900">{c.leads}</span></span>
                  {c.pending > 0 && <span className="text-amber-600 font-medium">待审批 {c.pending}</span>}
                </div>
                <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
                  <button className="p-2 rounded-lg hover:bg-gray-100 text-gray-400" style={{ minHeight: 44, minWidth: 44 }} onClick={() => handleToggle(c.id)}>
                    {c.status === '运行中' ? <Pause size={14} /> : <Play size={14} />}
                  </button>
                  <button className="p-2 rounded-lg hover:bg-red-50 text-gray-400 hover:text-red-400" style={{ minHeight: 44, minWidth: 44 }} onClick={() => setDeleteId(c.id)}>
                    <Trash2 size={14} />
                  </button>
                </div>
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

      {/* Mobile filter drawer */}
      {filtersOpen && (
        <div className="fixed inset-0 z-50 flex flex-col justify-end md:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setFiltersOpen(false)} />
          <div className="relative bg-white rounded-t-2xl p-5 flex flex-col gap-4">
            <div className="w-8 h-1 rounded-full bg-gray-300 mx-auto mb-2" />
            <div className="text-sm font-semibold text-gray-900">筛选</div>
            {[
              { label: '平台', options: ['全部', 'Facebook', 'Instagram', 'TikTok', 'X', 'YouTube'], value: platformFilter, onChange: setPlatformFilter },
              { label: '状态', options: ['全部', '运行中', '已暂停', '草稿', '异常'], value: statusFilter, onChange: setStatusFilter },
              { label: '回复模式', options: ['全部', '已关闭', '人工审批', '自动执行'], value: modeFilter, onChange: setModeFilter },
            ].map((f) => (
              <div key={f.label} className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-gray-600">{f.label}</label>
                <select value={f.value} onChange={(e) => f.onChange(e.target.value)} className="px-3 py-3 text-sm border rounded-xl bg-white focus:outline-none" style={{ borderColor: 'var(--border)', minHeight: 44 }}>
                  {f.options.map((o) => <option key={o}>{o}</option>)}
                </select>
              </div>
            ))}
            <button
              className="w-full py-3 text-sm font-medium rounded-xl text-white mt-2"
              style={{ background: 'var(--primary)', minHeight: 44 }}
              onClick={() => setFiltersOpen(false)}
            >
              应用筛选
            </button>
          </div>
        </div>
      )}

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

function Megaphone({ size, className }: { size: number; className?: string }) {
  return <svg width={size} height={size} className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}><path d="M3 11l19-9-9 19-2-8-8-2z" /></svg>
}
