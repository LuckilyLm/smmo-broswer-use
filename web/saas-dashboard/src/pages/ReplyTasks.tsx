import { useState } from 'react'
import { Eye, CheckCircle, XCircle, X, AlertTriangle, Info, ChevronDown, ChevronUp } from 'lucide-react'
import TopBar from '../components/layout/TopBar'
import StatusBadge from '../components/ui/StatusBadge'
import ConfirmModal from '../components/ui/ConfirmModal'

const plans = [
  { id: 'RP-1047', campaign: '跨境电商引流', account: '@smmo_business', mode: '人工审批', candidates: 5, approved: 0, sent: 0, failed: 0, status: '待审批', created: '07/24 10:15' },
  { id: 'RP-1046', campaign: '独立站获客', account: '@smmo_official', mode: '人工审批', candidates: 4, approved: 0, sent: 0, failed: 0, status: '待审批', created: '07/24 09:52' },
  { id: 'RP-1045', campaign: 'TikTok 品牌曝光', account: '@smmo_tiktok', mode: '人工审批', candidates: 2, approved: 2, sent: 0, failed: 0, status: '已批准', created: '07/24 08:30' },
  { id: 'RP-1044', campaign: '海外招商合作', account: '@smmo_channel', mode: '已关闭', candidates: 3, approved: 1, sent: 0, failed: 0, status: '已阻断', created: '07/23 22:10' },
  { id: 'RP-1043', campaign: '独立站获客', account: '@smmo_official', mode: '人工审批', candidates: 6, approved: 6, sent: 6, failed: 0, status: '已完成', created: '07/23 18:45' },
]

const candidates = [
  { id: 'C-001', author: '@zhangwei88', comment: '请问有没有针对中小企业的套餐价格，想了解一下合作方式...', keyword: '套餐价格', rule: '价格意向强匹配', preview: '您好 zhangwei88，感谢您的留言！我们有多款适合中小企业的方案，欢迎通过 WhatsApp 联系：+86 138 xxxx xxxx', status: '待审批', plan: 'RP-1047' },
  { id: 'C-002', author: '@li_beauty', comment: '这个产品支持代购吗，我在海外想买', keyword: '代购', rule: '海外代购需求', preview: '您好 li_beauty！我们支持全球发货，欢迎访问官网了解更多。', status: '待审批', plan: 'RP-1047' },
  { id: 'C-003', author: '@trade_wang', comment: '有没有批发价或者大客户折扣', keyword: '批发价', rule: '价格意向强匹配', preview: '您好 trade_wang，我们确实为大客户提供专属折扣，欢迎联系。', status: '待审批', plan: 'RP-1046' },
]

const TABS = ['待审批', '已批准', '已阻断', '执行中', '已完成', '已取消']
const MAIN_TABS = ['回复计划', '回复候选']

function PlanDrawer({ onClose }: { onClose: () => void }) {
  const [approvedList, setApprovedList] = useState<string[]>([])
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)
  const [approveConfirm, setApproveConfirm] = useState(false)

  return (
    <div className="fixed inset-0 md:inset-y-0 md:right-0 md:left-auto z-50 flex flex-col bg-white md:w-[560px] shadow-xl md:border-l" style={{ borderColor: 'var(--border)' }}>
      <div className="flex items-center justify-between px-5 py-4 border-b shrink-0" style={{ borderColor: 'var(--border)' }}>
        <div>
          <h3 className="font-semibold text-gray-900">回复计划详情</h3>
          <div className="text-xs text-gray-400 mt-0.5">RP-1047 · 跨境电商引流</div>
        </div>
        <button className="p-2 text-gray-400 hover:text-gray-600" onClick={onClose} style={{ minHeight: 44, minWidth: 44 }}><X size={16} /></button>
      </div>

      <div
        className="mx-4 mt-3 flex items-start gap-2 px-3 py-2.5 rounded-lg border shrink-0"
        style={{ background: '#fffbeb', borderColor: '#fcd34d' }}
      >
        <AlertTriangle size={13} className="text-amber-500 shrink-0 mt-0.5" />
        <div className="text-xs text-amber-700">系统级回复发送开关当前处于关闭状态，已批准的回复不会实际发送。</div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
        <div className="border rounded-xl p-4" style={{ borderColor: 'var(--border)' }}>
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">计划信息</div>
          <div className="grid grid-cols-2 gap-2 text-sm">
            {[['平台账号', '@smmo_business'], ['回复模式', '人工审批'], ['候选数量', '5'], ['创建时间', '07/24 10:15']].map(([k, v]) => (
              <div key={k}>
                <span className="text-gray-400 text-xs">{k}</span>
                <div className="text-gray-800 font-medium text-sm">{v}</div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">候选回复</div>
          <div className="flex flex-col gap-2">
            {candidates.map((c, i) => (
              <div
                key={c.id}
                className="border rounded-xl overflow-hidden"
                style={{ borderColor: approvedList.includes(c.id) ? '#a7f3d0' : 'var(--border)' }}
              >
                <div
                  className="p-3.5 cursor-pointer"
                  style={{ background: approvedList.includes(c.id) ? '#f0fdf4' : 'white' }}
                  onClick={() => setExpandedIdx(expandedIdx === i ? null : i)}
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-xs font-medium text-gray-800">{c.author}</span>
                    <div className="flex items-center gap-2">
                      <StatusBadge status={approvedList.includes(c.id) ? '已批准' : c.status} />
                      {expandedIdx === i ? <ChevronUp size={12} className="text-gray-400" /> : <ChevronDown size={12} className="text-gray-400" />}
                    </div>
                  </div>
                  <div className="text-xs text-gray-500 line-clamp-2">{c.comment}</div>
                  <div className="flex items-center gap-2 mt-2 text-[11px] text-gray-400 flex-wrap">
                    <span className="px-1.5 py-0.5 bg-gray-100 rounded">规则：{c.rule}</span>
                    <span className="px-1.5 py-0.5 bg-gray-100 rounded">关键词：{c.keyword}</span>
                  </div>
                </div>
                {expandedIdx === i && (
                  <div className="border-t p-3.5" style={{ borderColor: 'var(--border)', background: '#fafafa' }}>
                    <div className="text-[11px] text-gray-500 mb-1.5">渲染后回复内容</div>
                    <div className="text-xs text-gray-700 leading-relaxed">{c.preview}</div>
                    {!approvedList.includes(c.id) && (
                      <div className="flex gap-2 mt-3">
                        <button
                          className="flex items-center gap-1 px-3 py-2 text-xs border rounded-lg hover:bg-red-50 text-red-500"
                          style={{ borderColor: '#fca5a5', minHeight: 44, flex: 1 }}
                        >
                          <XCircle size={12} /> 拒绝
                        </button>
                        <button
                          className="flex items-center gap-1 px-3 py-2 text-xs rounded-lg text-white hover:opacity-90"
                          style={{ background: 'var(--primary)', minHeight: 44, flex: 1 }}
                          onClick={() => setApprovedList((prev) => [...prev, c.id])}
                        >
                          <CheckCircle size={12} /> 批准
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="border-t p-4 flex gap-2 shrink-0" style={{ borderColor: 'var(--border)', paddingBottom: 'max(16px, env(safe-area-inset-bottom))' }}>
        <button
          className="flex-1 px-3 py-2.5 text-sm font-medium rounded-lg border hover:bg-gray-50 flex items-center justify-center gap-1.5"
          style={{ borderColor: '#fca5a5', color: '#ef4444', minHeight: 44 }}
        >
          <XCircle size={13} /> 拒绝全部
        </button>
        <button
          className="flex-1 px-3 py-2.5 text-sm font-medium rounded-lg flex items-center justify-center gap-1.5 cursor-not-allowed"
          style={{ background: '#e5e7eb', color: '#9ca3af', minHeight: 44 }}
          title="系统级回复发送开关当前处于关闭状态"
        >
          <CheckCircle size={13} /> 批准并执行
          <Info size={11} />
        </button>
      </div>
      <ConfirmModal open={approveConfirm} title="确认批准全部" onConfirm={() => setApproveConfirm(false)} onCancel={() => setApproveConfirm(false)} />
    </div>
  )
}

export default function ReplyTasks({ onMenuOpen }: { onMenuOpen?: () => void }) {
  const [mainTab, setMainTab] = useState('回复计划')
  const [activeTab, setActiveTab] = useState('待审批')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [selectedIds, setSelectedIds] = useState<string[]>([])

  const metrics = [
    { label: '待审批计划', value: 2, color: '#f59e0b' },
    { label: '待审批候选', value: 14, color: '#f59e0b' },
    { label: '已批准', value: 8, color: '#10b981' },
    { label: '已阻断', value: 3, color: '#d97706' },
    { label: '失败', value: 1, color: '#ef4444' },
  ]

  const filteredPlans = plans.filter((p) => {
    if (activeTab === '待审批') return p.status === '待审批'
    if (activeTab === '已批准') return p.status === '已批准'
    if (activeTab === '已阻断') return p.status === '已阻断'
    if (activeTab === '执行中') return p.status === '执行中'
    if (activeTab === '已完成') return p.status === '已完成'
    if (activeTab === '已取消') return p.status === '已取消'
    return true
  })

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id])
  }

  return (
    <div className="flex flex-col min-h-screen">
      <TopBar breadcrumbs={['回复自动化', '回复任务']} pageTitle="回复任务" onMenuOpen={onMenuOpen} />
      <div className="flex-1 p-4 md:p-6 flex flex-col gap-4">
        <div>
          <h1 className="text-lg md:text-xl font-semibold text-gray-900">回复任务</h1>
          <p className="text-sm text-gray-500 mt-0.5 hidden md:block">查看并审批待执行的回复计划</p>
        </div>

        {/* Metrics */}
        <div className="grid grid-cols-3 md:grid-cols-5 gap-2 md:gap-3">
          {metrics.map((m) => (
            <div key={m.label} className="bg-white border rounded-xl px-3 py-3" style={{ borderColor: 'var(--border)' }}>
              <div className="text-[10px] md:text-[11px] text-gray-400 leading-tight">{m.label}</div>
              <div className="text-xl md:text-2xl font-bold mt-1" style={{ color: m.color }}>{m.value}</div>
            </div>
          ))}
        </div>

        {/* Main tabs */}
        <div className="flex border-b" style={{ borderColor: 'var(--border)' }}>
          {MAIN_TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setMainTab(tab)}
              className="px-4 py-2.5 text-sm font-medium border-b-2 transition-colors"
              style={{
                borderBottomColor: mainTab === tab ? 'var(--primary)' : 'transparent',
                color: mainTab === tab ? 'var(--primary)' : '#6b7280',
                minHeight: 44,
              }}
            >
              {tab}
            </button>
          ))}
        </div>

        {mainTab === '回复计划' && (
          <>
            {/* Sub tabs */}
            <div className="flex border-b overflow-x-auto scrollbar-hide -mt-2" style={{ borderColor: 'var(--border)' }}>
              {TABS.map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className="px-3 py-2 text-xs font-medium border-b-2 transition-colors whitespace-nowrap shrink-0"
                  style={{
                    borderBottomColor: activeTab === tab ? 'var(--primary)' : 'transparent',
                    color: activeTab === tab ? 'var(--primary)' : '#6b7280',
                    minHeight: 40,
                  }}
                >
                  {tab}
                </button>
              ))}
            </div>

            {/* Desktop table */}
            <div className="hidden md:block bg-white border rounded-xl overflow-hidden" style={{ borderColor: 'var(--border)' }}>
              {filteredPlans.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                  <CheckCircle size={32} className="mb-3 text-gray-200" />
                  <div className="text-sm">暂无{activeTab}计划</div>
                </div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b" style={{ borderColor: 'var(--border)', background: '#fafafa' }}>
                      <th className="px-4 py-3 w-10"><input type="checkbox" className="rounded" /></th>
                      {['计划 ID', '营销活动', '平台账号', '回复模式', '候选数', '已批准', '已发送', '失败', '状态', '创建时间', '操作'].map((h) => (
                        <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-gray-500 whitespace-nowrap">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredPlans.map((p) => (
                      <tr key={p.id} className="border-b last:border-0 hover:bg-gray-50" style={{ borderColor: 'var(--border)' }}>
                        <td className="px-4 py-3"><input type="checkbox" className="rounded" checked={selectedIds.includes(p.id)} onChange={() => toggleSelect(p.id)} /></td>
                        <td className="px-4 py-3 font-mono text-xs text-gray-600 whitespace-nowrap">{p.id}</td>
                        <td className="px-4 py-3 font-medium text-gray-800 whitespace-nowrap">{p.campaign}</td>
                        <td className="px-4 py-3 text-gray-500 text-xs whitespace-nowrap">{p.account}</td>
                        <td className="px-4 py-3"><StatusBadge status={p.mode} /></td>
                        <td className="px-4 py-3 text-center text-gray-600">{p.candidates}</td>
                        <td className="px-4 py-3 text-center text-green-600 font-medium">{p.approved}</td>
                        <td className="px-4 py-3 text-center text-gray-400">{p.sent}</td>
                        <td className="px-4 py-3 text-center text-red-400">{p.failed || '—'}</td>
                        <td className="px-4 py-3"><StatusBadge status={p.status} variant="dot" /></td>
                        <td className="px-4 py-3 text-gray-400 text-xs whitespace-nowrap">{p.created}</td>
                        <td className="px-4 py-3">
                          <button
                            className="flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-lg border hover:bg-gray-50 whitespace-nowrap"
                            style={{ borderColor: 'var(--border)', color: 'var(--primary)' }}
                            onClick={() => setDrawerOpen(true)}
                          >
                            <Eye size={11} /> 查看
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {/* Mobile cards */}
            <div className="md:hidden flex flex-col gap-2">
              {filteredPlans.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                  <CheckCircle size={32} className="mb-3 text-gray-200" />
                  <div className="text-sm">暂无{activeTab}计划</div>
                </div>
              ) : filteredPlans.map((p) => (
                <div
                  key={p.id}
                  className="bg-white border rounded-xl p-4 cursor-pointer"
                  style={{ borderColor: 'var(--border)' }}
                  onClick={() => setDrawerOpen(true)}
                >
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <div>
                      <div className="font-medium text-gray-900">{p.campaign}</div>
                      <div className="text-xs text-gray-400 mt-0.5">{p.id} · {p.account}</div>
                    </div>
                    <StatusBadge status={p.status} variant="dot" />
                  </div>
                  <div className="flex items-center gap-3 text-xs text-gray-500 flex-wrap">
                    <span>候选 {p.candidates}</span>
                    <span className="text-green-600">已批准 {p.approved}</span>
                    <StatusBadge status={p.mode} />
                  </div>
                </div>
              ))}
            </div>

            {/* Batch action bar */}
            {selectedIds.length > 0 && (
              <div
                className="fixed bottom-0 left-0 right-0 flex items-center gap-3 px-4 py-3 bg-white border-t shadow-lg z-30"
                style={{ borderColor: 'var(--border)', paddingBottom: 'max(12px, env(safe-area-inset-bottom))' }}
              >
                <span className="text-sm text-gray-600">已选 {selectedIds.length} 个</span>
                <button className="ml-auto flex items-center gap-1.5 px-3 py-2 text-sm border rounded-lg hover:bg-red-50 text-red-500" style={{ borderColor: '#fca5a5', minHeight: 44 }}>
                  <XCircle size={13} /> 批量拒绝
                </button>
                <button
                  className="flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg cursor-not-allowed"
                  style={{ background: '#e5e7eb', color: '#9ca3af', minHeight: 44 }}
                  title="回复发送当前处于关闭状态"
                >
                  <CheckCircle size={13} /> 批量批准
                </button>
              </div>
            )}
          </>
        )}

        {mainTab === '回复候选' && (
          <div className="flex flex-col gap-2">
            {candidates.map((c) => (
              <div key={c.id} className="bg-white border rounded-xl p-4" style={{ borderColor: 'var(--border)' }}>
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div className="font-medium text-gray-900 text-sm">{c.author}</div>
                  <StatusBadge status={c.status} />
                </div>
                <div className="text-xs text-gray-500 mb-2">{c.comment}</div>
                <div className="flex flex-wrap gap-1.5 mb-3">
                  <span className="px-1.5 py-0.5 bg-gray-100 rounded text-[11px] text-gray-500">关键词：{c.keyword}</span>
                  <span className="px-1.5 py-0.5 bg-gray-100 rounded text-[11px] text-gray-500">规则：{c.rule}</span>
                </div>
                <div className="border-t pt-2.5" style={{ borderColor: 'var(--border)' }}>
                  <div className="text-[11px] text-gray-400 mb-1">回复预览</div>
                  <div className="text-xs text-gray-700 leading-relaxed">{c.preview}</div>
                </div>
                <div className="flex gap-2 mt-3">
                  <button className="flex-1 flex items-center justify-center gap-1 py-2.5 text-xs border rounded-lg hover:bg-red-50 text-red-500" style={{ borderColor: '#fca5a5', minHeight: 44 }}>
                    <XCircle size={12} /> 拒绝
                  </button>
                  <button className="flex-1 flex items-center justify-center gap-1 py-2.5 text-xs rounded-lg text-white" style={{ background: 'var(--primary)', minHeight: 44 }}>
                    <CheckCircle size={12} /> 批准
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {drawerOpen && <PlanDrawer onClose={() => setDrawerOpen(false)} />}
      {drawerOpen && <div className="fixed inset-0 bg-black/20 z-40 hidden md:block" onClick={() => setDrawerOpen(false)} />}
    </div>
  )
}
