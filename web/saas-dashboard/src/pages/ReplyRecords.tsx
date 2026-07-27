import { useState } from 'react'
import { Search, Filter, MessageSquareOff, X } from 'lucide-react'
import TopBar from '../components/layout/TopBar'
import StatusBadge from '../components/ui/StatusBadge'

const records = [
  { id: 'RR-5043', author: '@zhangwei88', comment: '请问有没有中小企业套餐', reply: '您好 zhangwei88，感谢您的留言！我们有适合您需求的方案...', campaign: '跨境电商引流', platform: 'Facebook', status: '已阻断', verified: false, error: '系统发送开关关闭', sentAt: '—' },
  { id: 'RR-5042', author: '@maria.santos', comment: 'How can I contact your sales team?', reply: "Hi Maria, thanks for your interest! We'd love to help...", campaign: '独立站获客', platform: 'Instagram', status: '已阻断', verified: false, error: '系统发送开关关闭', sentAt: '—' },
  { id: 'RR-5001', author: '@kenji88', comment: '请问有货吗', reply: '您好，目前有货，欢迎下单。', campaign: '跨境电商引流', platform: 'Facebook', status: '已发送', verified: true, error: '—', sentAt: '07/22 14:30' },
  { id: 'RR-5000', author: '@lily_trade', comment: '价格能谈吗', reply: '您好，批量采购有折扣，联系我们...', campaign: '海外招商合作', platform: 'YouTube', status: '已验证', verified: true, error: '—', sentAt: '07/21 09:15' },
  { id: 'RR-4998', author: '@wang_global', comment: '能不能发到海外', reply: '可以全球发货，请联系...', campaign: '独立站获客', platform: 'Instagram', status: '失败', verified: false, error: 'API 频率限制', sentAt: '07/20 16:44' },
]

interface ReplyRecordsProps {
  onMenuOpen?: () => void
}

export default function ReplyRecords({ onMenuOpen }: ReplyRecordsProps) {
  const [search, setSearch] = useState('')
  const [filterOpen, setFilterOpen] = useState(false)
  const [detailId, setDetailId] = useState<string | null>(null)

  const filtered = records.filter((r) =>
    !search || r.author.includes(search) || r.campaign.includes(search)
  )

  const detail = records.find((r) => r.id === detailId)

  return (
    <div className="flex flex-col min-h-screen">
      <TopBar breadcrumbs={['回复自动化', '回复记录']} pageTitle="回复记录" onMenuOpen={onMenuOpen} />
      <div className="flex-1 p-4 md:p-6 flex flex-col gap-4">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-gray-900">回复记录</h1>
          <p className="text-sm text-gray-500 mt-0.5 hidden md:block">查看所有已处理的回复候选执行状态</p>
        </div>

        <div className="flex items-start gap-3 p-4 rounded-xl border" style={{ background: '#f0fdf4', borderColor: '#bbf7d0' }}>
          <MessageSquareOff size={16} className="text-green-600 shrink-0 mt-0.5" />
          <div className="text-sm text-green-700 leading-relaxed">
            当前系统发送功能已关闭，因此暂时没有真实回复记录。以下记录来自系统发送开关关闭前的历史数据。
          </div>
        </div>

        {/* Filters row */}
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative flex-1 min-w-0" style={{ maxWidth: 240 }}>
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="搜索作者或活动..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 pr-3 py-2.5 text-sm border rounded-lg bg-white focus:outline-none w-full"
              style={{ borderColor: 'var(--border)', minHeight: 44 }}
            />
          </div>
          <div className="hidden md:flex items-center gap-2">
            {['活动', '平台', '状态'].map((label) => (
              <select key={label} className="px-3 py-2.5 text-sm border rounded-lg bg-white focus:outline-none" style={{ borderColor: 'var(--border)', minHeight: 44 }}>
                <option>全部{label}</option>
              </select>
            ))}
          </div>
          <button
            className="md:hidden flex items-center gap-1.5 px-3 py-2.5 text-sm border rounded-lg hover:bg-gray-50"
            style={{ borderColor: 'var(--border)', minHeight: 44 }}
            onClick={() => setFilterOpen(true)}
          >
            <Filter size={13} /> 筛选
          </button>
        </div>

        {/* Desktop table */}
        <div className="hidden md:block bg-white border rounded-xl overflow-hidden" style={{ borderColor: 'var(--border)' }}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[860px]">
              <thead>
                <tr className="border-b" style={{ borderColor: 'var(--border)', background: '#fafafa' }}>
                  {['记录ID', '作者', '原始评论', '活动', '平台', '状态', '错误类型', '发送时间'].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-gray-500">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr
                    key={r.id}
                    className="border-b last:border-0 hover:bg-gray-50 cursor-pointer"
                    style={{ borderColor: 'var(--border)' }}
                    onClick={() => setDetailId(r.id)}
                  >
                    <td className="px-4 py-3 font-mono text-xs text-gray-500">{r.id}</td>
                    <td className="px-4 py-3 font-medium text-gray-800 whitespace-nowrap">{r.author}</td>
                    <td className="px-4 py-3 text-gray-600 max-w-[180px] truncate">{r.comment}</td>
                    <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{r.campaign}</td>
                    <td className="px-4 py-3 text-gray-600">{r.platform}</td>
                    <td className="px-4 py-3"><StatusBadge status={r.status} /></td>
                    <td className="px-4 py-3 text-xs text-gray-500 max-w-[140px] truncate">{r.error}</td>
                    <td className="px-4 py-3 text-gray-400 whitespace-nowrap">{r.sentAt}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Mobile cards */}
        <div className="md:hidden flex flex-col gap-3">
          {filtered.map((r) => (
            <div
              key={r.id}
              className="bg-white border rounded-xl p-4 cursor-pointer active:bg-gray-50"
              style={{ borderColor: 'var(--border)' }}
              onClick={() => setDetailId(r.id)}
            >
              <div className="flex items-start justify-between gap-2 mb-1">
                <div className="min-w-0">
                  <span className="font-medium text-sm text-gray-800">{r.author}</span>
                  <div className="text-xs text-gray-500 mt-0.5 line-clamp-2 break-words">{r.comment}</div>
                </div>
                <StatusBadge status={r.status} />
              </div>
              <div className="flex items-center gap-2 mt-2 flex-wrap text-xs text-gray-400">
                <span className="font-mono">{r.id}</span>
                <span>·</span>
                <span>{r.campaign}</span>
                <span>·</span>
                <span>{r.platform}</span>
                {r.error !== '—' && (
                  <>
                    <span>·</span>
                    <span className="text-red-400 truncate max-w-[120px]">{r.error}</span>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Detail drawer */}
      {detail && (
        <>
          <div className="fixed inset-0 bg-black/20 z-30" onClick={() => setDetailId(null)} />
          <div className="fixed inset-0 md:inset-y-0 md:right-0 md:left-auto md:w-[480px] bg-white border-l flex flex-col z-40 shadow-xl" style={{ borderColor: 'var(--border)' }}>
            <div className="flex items-center justify-between px-4 py-3 border-b shrink-0" style={{ borderColor: 'var(--border)' }}>
              <div>
                <h3 className="font-semibold text-gray-900">回复记录详情</h3>
                <div className="text-xs text-gray-400 mt-0.5 font-mono">{detail.id}</div>
              </div>
              <button className="text-gray-400 hover:text-gray-600 p-2" onClick={() => setDetailId(null)} style={{ minHeight: 44, minWidth: 44 }}><X size={16} /></button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
              <div className="flex items-center gap-2 flex-wrap">
                <StatusBadge status={detail.status} />
                <span className="text-xs text-gray-400">{detail.platform} · {detail.campaign}</span>
              </div>
              <div>
                <div className="text-xs font-semibold text-gray-500 mb-1.5">原始评论</div>
                <div className="bg-gray-50 border rounded-xl p-3 text-sm text-gray-700 leading-relaxed break-words" style={{ borderColor: 'var(--border)' }}>{detail.comment}</div>
              </div>
              <div>
                <div className="text-xs font-semibold text-gray-500 mb-1.5">回复文本</div>
                <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-3 text-sm text-gray-700 leading-relaxed break-words">{detail.reply}</div>
              </div>
              {detail.error !== '—' && (
                <div className="flex items-start gap-2 p-3 rounded-xl bg-red-50 border border-red-100 text-sm text-red-700 break-words">
                  <span className="font-semibold shrink-0">错误：</span>
                  <span>{detail.error}</span>
                </div>
              )}
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: '发送时间', value: detail.sentAt },
                  { label: '已验证', value: detail.verified ? '是' : '否' },
                ].map(({ label, value }) => (
                  <div key={label} className="bg-gray-50 border rounded-xl p-3" style={{ borderColor: 'var(--border)' }}>
                    <div className="text-xs text-gray-400">{label}</div>
                    <div className="text-sm font-medium text-gray-800 mt-0.5">{value}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </>
      )}

      {/* Mobile filter bottom sheet */}
      {filterOpen && (
        <>
          <div className="fixed inset-0 bg-black/30 z-30" onClick={() => setFilterOpen(false)} />
          <div className="fixed inset-x-0 bottom-0 z-40 bg-white rounded-t-2xl p-5 flex flex-col gap-4" style={{ paddingBottom: 'max(20px, env(safe-area-inset-bottom))' }}>
            <div className="flex items-center justify-between">
              <span className="font-semibold text-gray-900">筛选</span>
              <button className="p-2 text-gray-400" onClick={() => setFilterOpen(false)} style={{ minHeight: 44, minWidth: 44 }}><X size={16} /></button>
            </div>
            {['活动', '平台', '状态'].map((label) => (
              <div key={label} className="flex flex-col gap-1">
                <label className="text-xs font-medium text-gray-600">{label}</label>
                <select className="w-full px-3 py-2.5 text-sm border rounded-xl bg-white focus:outline-none" style={{ borderColor: 'var(--border)', minHeight: 44 }}>
                  <option>全部{label}</option>
                </select>
              </div>
            ))}
            <button
              className="w-full py-3 text-sm font-medium rounded-xl text-white"
              style={{ background: 'var(--primary)', minHeight: 44 }}
              onClick={() => setFilterOpen(false)}
            >
              应用筛选
            </button>
          </div>
        </>
      )}
    </div>
  )
}
