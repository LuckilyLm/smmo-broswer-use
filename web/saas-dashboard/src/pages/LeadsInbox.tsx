import { useState } from 'react'
import { Search, ExternalLink, CheckCircle, XCircle, Edit3, ArrowLeft, MessageSquare, Clock } from 'lucide-react'
import TopBar from '../components/layout/TopBar'
import StatusBadge from '../components/ui/StatusBadge'

const leads = [
  { id: 1, author: '@zhangwei88', comment: '请问有没有针对中小企业的套餐价格，想了解一下合作方式...', intent: '高意向', campaign: '跨境电商引流', platform: 'Facebook', time: '15 分钟前', sourceUrl: 'https://fb.com/post/123', keywords: ['套餐价格', '合作'], matchReason: '价格意向强匹配规则命中 2 个关键词', confidence: 0.91, contactStatus: '未联系' },
  { id: 2, author: '@maria.santos', comment: 'How can I contact your sales team? I am interested in bulk orders.', intent: '高意向', campaign: '独立站获客', platform: 'Instagram', time: '28 分钟前', sourceUrl: '', keywords: ['contact', 'bulk', 'sales'], matchReason: '英文询盘规则命中 3 个关键词', confidence: 0.87, contactStatus: '已联系' },
  { id: 3, author: '@li_beauty', comment: '这个产品支持代购吗，我在海外', intent: '中意向', campaign: '跨境电商引流', platform: 'Facebook', time: '42 分钟前', sourceUrl: '', keywords: ['代购', '海外'], matchReason: '海外代购需求规则', confidence: 0.72, contactStatus: '未联系' },
  { id: 4, author: '@trade_wang', comment: '有没有批发价或者大客户折扣，量比较大', intent: '高意向', campaign: '海外招商合作', platform: 'YouTube', time: '1 小时前', sourceUrl: '', keywords: ['批发价', '折扣'], matchReason: '价格意向强匹配', confidence: 0.89, contactStatus: '未联系' },
  { id: 5, author: '@kenji.tanaka', comment: 'I am interested in your product pricing and international shipping', intent: '中意向', campaign: 'TikTok 品牌曝光', platform: 'TikTok', time: '2 小时前', sourceUrl: '', keywords: ['pricing', 'shipping'], matchReason: '英文询盘规则', confidence: 0.65, contactStatus: '未联系' },
  { id: 6, author: '@casual_user', comment: '看起来不错哦', intent: '低意向', campaign: '跨境电商引流', platform: 'Facebook', time: '3 小时前', sourceUrl: '', keywords: [], matchReason: '最低意向阈值匹配', confidence: 0.23, contactStatus: '未联系' },
]

const platColors: Record<string, string> = {
  Facebook: '#1877f2', Instagram: '#e1306c', TikTok: '#010101', X: '#1da1f2', YouTube: '#ff0000',
}

interface LeadsInboxProps {
  onMenuOpen?: () => void
}

export default function LeadsInbox({ onMenuOpen }: LeadsInboxProps) {
  const [selectedId, setSelectedId] = useState<number>(1)
  const [intentFilter, setIntentFilter] = useState('全部')
  const [search, setSearch] = useState('')
  const [notes, setNotes] = useState<Record<number, string>>({})
  const [activeRightTab, setActiveRightTab] = useState<'reply' | 'timeline'>('reply')
  const [mobileView, setMobileView] = useState<'list' | 'detail'>('list')

  const selected = leads.find((l) => l.id === selectedId)
  const filtered = leads.filter((l) => {
    if (intentFilter !== '全部' && l.intent !== intentFilter) return false
    if (search && !l.author.includes(search) && !l.comment.includes(search)) return false
    return true
  })

  const handleSelect = (id: number) => {
    setSelectedId(id)
    setMobileView('detail')
  }

  return (
    <div className="flex flex-col" style={{ height: '100vh', overflow: 'hidden' }}>
      <TopBar breadcrumbs={['获客管理', '线索收件箱']} pageTitle={mobileView === 'detail' ? selected?.author ?? '线索详情' : '线索收件箱'} onMenuOpen={mobileView === 'list' ? onMenuOpen : undefined} />

      {/* Mobile back button when in detail */}
      {mobileView === 'detail' && (
        <div className="md:hidden flex items-center gap-2 px-4 py-2 border-b bg-white" style={{ borderColor: 'var(--border)' }}>
          <button
            className="flex items-center gap-1.5 text-sm font-medium"
            style={{ color: 'var(--primary)', minHeight: 44 }}
            onClick={() => setMobileView('list')}
          >
            <ArrowLeft size={16} /> 返回列表
          </button>
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        {/* Left: filters + list */}
        <div
          className={`${mobileView === 'list' ? 'flex' : 'hidden'} md:flex flex-col border-r`}
          style={{ width: '100%', maxWidth: '100%', borderColor: 'var(--border)' }}
        >
          {/* On desktop, constrain width */}
          <div className="md:w-72 w-full flex flex-col h-full">
            <div className="p-3 border-b flex flex-col gap-2 shrink-0" style={{ borderColor: 'var(--border)' }}>
              <div className="relative">
                <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
                <input
                  type="text"
                  placeholder="搜索线索..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-7 pr-3 py-2 text-xs border rounded-lg w-full focus:outline-none"
                  style={{ borderColor: 'var(--border)', minHeight: 40 }}
                />
              </div>
              <div className="flex gap-1 flex-wrap">
                {['全部', '高意向', '中意向', '低意向'].map((f) => (
                  <button
                    key={f}
                    className="px-2.5 py-1.5 text-xs rounded-md transition-colors"
                    style={{
                      background: intentFilter === f ? 'var(--primary)' : 'var(--secondary)',
                      color: intentFilter === f ? 'white' : '#374151',
                      minHeight: 36,
                    }}
                    onClick={() => setIntentFilter(f)}
                  >
                    {f}
                  </button>
                ))}
              </div>
            </div>
            <div className="flex-1 overflow-y-auto">
              {filtered.map((lead) => (
                <div
                  key={lead.id}
                  className="p-3 border-b cursor-pointer transition-colors"
                  style={{
                    borderColor: 'var(--border)',
                    background: selectedId === lead.id && mobileView !== 'list' ? 'var(--accent)' : 'white',
                    borderLeft: selectedId === lead.id ? '3px solid var(--primary)' : '3px solid transparent',
                    minHeight: 72,
                  }}
                  onClick={() => handleSelect(lead.id)}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-semibold text-gray-800">{lead.author}</span>
                    <StatusBadge status={lead.intent} />
                  </div>
                  <div className="text-[11px] text-gray-500 line-clamp-2 leading-relaxed">{lead.comment}</div>
                  <div className="flex items-center gap-2 mt-1 text-[11px] text-gray-400">
                    <span style={{ color: platColors[lead.platform] }}>{lead.platform}</span>
                    <span>·</span>
                    <span>{lead.time}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Center: detail (hidden on mobile when in list view) */}
        {selected && (
          <div
            className={`${mobileView === 'detail' ? 'flex' : 'hidden'} md:flex flex-1 overflow-y-auto flex-col`}
          >
            <div className="p-4 md:p-6 flex flex-col gap-4">
              <div>
                <div className="flex items-center gap-3 mb-1 flex-wrap">
                  <h2 className="text-base font-semibold text-gray-900">{selected.author}</h2>
                  <StatusBadge status={selected.intent} />
                  <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-500">{selected.platform}</span>
                </div>
                <div className="text-xs text-gray-400">{selected.campaign} · {selected.time}</div>
              </div>

              <div className="bg-white border rounded-xl p-4" style={{ borderColor: 'var(--border)' }}>
                <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">原始评论</div>
                <div className="text-sm text-gray-800 leading-relaxed">{selected.comment}</div>
                {selected.sourceUrl && (
                  <a href={selected.sourceUrl} target="_blank" rel="noreferrer" className="mt-2 flex items-center gap-1 text-xs text-indigo-600 hover:underline break-all" style={{ minHeight: 44 }}>
                    <ExternalLink size={11} className="shrink-0" />
                    查看原始帖子
                  </a>
                )}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="bg-white border rounded-xl p-4" style={{ borderColor: 'var(--border)' }}>
                  <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">匹配详情</div>
                  <div className="text-sm text-gray-700 mb-2">{selected.matchReason}</div>
                  <div className="flex flex-wrap gap-1 mb-2">
                    {selected.keywords.map((k) => (
                      <span key={k} className="px-2 py-0.5 bg-indigo-50 border border-indigo-100 rounded text-xs text-indigo-600">{k}</span>
                    ))}
                  </div>
                  <div className="flex items-center gap-2 mt-2">
                    <div className="text-xs text-gray-500">意向置信度</div>
                    <div className="flex-1 h-1.5 rounded-full bg-gray-100 overflow-hidden">
                      <div className="h-full rounded-full" style={{ width: `${selected.confidence * 100}%`, background: selected.confidence > 0.8 ? '#10b981' : selected.confidence > 0.5 ? '#f59e0b' : '#d1d5db' }} />
                    </div>
                    <div className="text-xs font-medium text-gray-700">{Math.round(selected.confidence * 100)}%</div>
                  </div>
                </div>
                <div className="bg-white border rounded-xl p-4" style={{ borderColor: 'var(--border)' }}>
                  <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">备注</div>
                  <textarea
                    rows={3}
                    placeholder="添加内部备注..."
                    value={notes[selected.id] ?? ''}
                    onChange={(e) => setNotes({ ...notes, [selected.id]: e.target.value })}
                    className="w-full px-2.5 py-2 text-xs border rounded-lg resize-none focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    style={{ borderColor: 'var(--border)' }}
                  />
                </div>
              </div>

              {/* Mobile: show reply candidate inline */}
              <div className="md:hidden">
                <div className="flex border-b mb-3" style={{ borderColor: 'var(--border)' }}>
                  {(['reply', 'timeline'] as const).map((tab) => (
                    <button
                      key={tab}
                      onClick={() => setActiveRightTab(tab)}
                      className="flex-1 py-2.5 text-sm font-medium border-b-2 transition-colors"
                      style={{
                        borderBottomColor: activeRightTab === tab ? 'var(--primary)' : 'transparent',
                        color: activeRightTab === tab ? 'var(--primary)' : '#6b7280',
                        minHeight: 44,
                      }}
                    >
                      {tab === 'reply' ? '回复候选' : '活动时间线'}
                    </button>
                  ))}
                </div>
                {activeRightTab === 'reply' && <ReplyPanel author={selected.author} />}
                {activeRightTab === 'timeline' && <TimelinePanel />}
              </div>
            </div>
          </div>
        )}

        {/* Right: reply panel (desktop only) */}
        {selected && (
          <div
            className="hidden md:flex flex-col border-l"
            style={{ width: 272, minWidth: 272, borderColor: 'var(--border)' }}
          >
            <div className="p-4 border-b" style={{ borderColor: 'var(--border)' }}>
              <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">回复候选</div>
              <ReplyPanel author={selected.author} />
            </div>
            <div className="flex-1 overflow-y-auto p-4">
              <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">活动时间线</div>
              <TimelinePanel />
            </div>
          </div>
        )}
      </div>

      {/* Mobile bottom action bar when in detail */}
      {mobileView === 'detail' && selected && (
        <div
          className="md:hidden border-t bg-white flex gap-2 px-4 py-3 shrink-0"
          style={{ borderColor: 'var(--border)', paddingBottom: 'max(12px, env(safe-area-inset-bottom))' }}
        >
          <button className="flex-1 py-2.5 text-sm border rounded-xl text-red-500 flex items-center justify-center gap-1.5" style={{ borderColor: '#fca5a5', minHeight: 44 }}>
            <XCircle size={13} /> 标为无效
          </button>
          <button className="flex-1 py-2.5 text-sm rounded-xl text-white flex items-center justify-center gap-1.5" style={{ background: 'var(--primary)', minHeight: 44 }}>
            <CheckCircle size={13} /> 标为已联系
          </button>
        </div>
      )}
    </div>
  )
}

function ReplyPanel({ author }: { author: string }) {
  return (
    <div>
      <div className="text-xs text-gray-700 bg-gray-50 rounded-lg p-3 leading-relaxed border" style={{ borderColor: 'var(--border)' }}>
        您好 {author.replace('@', '')}，感谢您的留言！<br /><br />
        我们有适合您需求的方案，欢迎通过以下方式联系：<br />
        📱 WhatsApp：+86 138 xxxx xxxx<br />
        🌐 官网：https://company.com
      </div>
      <div className="flex items-center gap-1.5 mt-2 text-[11px] text-gray-400">
        <span>模板：标准获客模板</span>
      </div>
      <div className="flex gap-2 mt-3">
        <button className="flex-1 px-2.5 py-2.5 text-xs border rounded-lg hover:bg-gray-50 flex items-center justify-center gap-1" style={{ borderColor: 'var(--border)', color: '#ef4444', minHeight: 44 }}>
          <XCircle size={11} /> 拒绝
        </button>
        <button className="flex-1 px-2.5 py-2.5 text-xs rounded-lg text-white hover:opacity-90 flex items-center justify-center gap-1" style={{ background: 'var(--primary)', minHeight: 44 }}>
          <CheckCircle size={11} /> 审批
        </button>
      </div>
      <button className="mt-1.5 w-full px-2.5 py-2.5 text-xs border rounded-lg hover:bg-gray-50 flex items-center justify-center gap-1" style={{ borderColor: 'var(--border)', minHeight: 44 }}>
        <Edit3 size={11} /> 编辑回复
      </button>
    </div>
  )
}

function TimelinePanel() {
  return (
    <div className="flex flex-col gap-0">
      {[
        { time: '10:15', event: '线索识别', desc: '价格意向规则命中' },
        { time: '10:15', event: '候选生成', desc: '使用标准获客模板' },
        { time: '10:16', event: '计划创建', desc: 'RP-1047 已创建' },
        { time: '—', event: '等待审批', desc: '待人工审批' },
      ].map((item, i, arr) => (
        <div key={i} className="flex gap-3">
          <div className="flex flex-col items-center">
            <div className="w-2 h-2 rounded-full border-2 shrink-0 mt-0.5" style={{ borderColor: 'var(--primary)', background: i === arr.length - 1 ? 'white' : 'var(--primary)' }} />
            {i < arr.length - 1 && <div className="w-px flex-1 my-1" style={{ background: '#e5e7eb', minHeight: 16 }} />}
          </div>
          <div className="pb-3">
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-medium text-gray-700">{item.event}</span>
              <span className="text-[11px] text-gray-400">{item.time}</span>
            </div>
            <div className="text-[11px] text-gray-400">{item.desc}</div>
          </div>
        </div>
      ))}
    </div>
  )
}
