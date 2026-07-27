import { useState } from 'react'
import { Search, X, ChevronDown, ChevronRight, Shield } from 'lucide-react'
import TopBar from '../components/layout/TopBar'

const logs = [
  { id: 'AL-8841', time: '07/24 10:32', user: '王小明', action: '创建营销活动', resource: '跨境电商引流 – 全渠道', result: '成功', ip: '203.0.113.5', details: { campaignId: 'CAM-124', platform: 'Facebook', keywords: 5 } },
  { id: 'AL-8840', time: '07/24 10:15', user: '王小明', action: '审批回复计划', resource: 'RP-1047', result: '成功', ip: '203.0.113.5', details: { planId: 'RP-1047', candidates: 3, approved: 3 } },
  { id: 'AL-8839', time: '07/24 09:52', user: '李美华', action: '修改匹配规则', resource: '价格意向强匹配', result: '成功', ip: '203.0.113.12', details: { ruleId: 'RULE-12', field: 'keywords', before: '价格', after: '价格, 报价' } },
  { id: 'AL-8838', time: '07/24 09:30', user: '张伟国', action: '登录', resource: '系统', result: '成功', ip: '203.0.113.88', details: { device: 'Chrome / Windows', location: '广州' } },
  { id: 'AL-8837', time: '07/23 22:00', user: 'system', action: '执行定时任务', resource: 'X 高净值用户', result: '失败', ip: '内部', details: { executionId: 'EX-2844', error: '账号登录已过期', stage: '登录检查' } },
  { id: 'AL-8836', time: '07/23 18:45', user: '李美华', action: '删除关键词', resource: '采购', result: '成功', ip: '203.0.113.12', details: { keywordId: 'KW-88', campaign: '跨境电商引流' } },
  { id: 'AL-8835', time: '07/23 16:20', user: '王小明', action: '修改设置', resource: '租户信息', result: '成功', ip: '203.0.113.5', details: { field: 'defaultWhatsApp', before: '+86 130 xxxx', after: '+86 138 xxxx' } },
]

const actionColors: Record<string, string> = {
  '创建营销活动': '#4338ca',
  '审批回复计划': '#10b981',
  '修改匹配规则': '#f59e0b',
  '登录': '#6b7280',
  '执行定时任务': '#f59e0b',
  '删除关键词': '#ef4444',
  '修改设置': '#6366f1',
}

function DetailDrawer({ log, onClose }: { log: typeof logs[0]; onClose: () => void }) {
  const [showJson, setShowJson] = useState(false)
  return (
    <div className="fixed inset-0 md:inset-y-0 md:right-0 md:left-auto z-50 flex flex-col bg-white md:w-[440px] shadow-xl border-l" style={{ borderColor: 'var(--border)' }}>
      <div className="flex items-center justify-between px-5 py-4 border-b shrink-0" style={{ borderColor: 'var(--border)' }}>
        <h3 className="font-semibold text-gray-900">审计日志详情</h3>
        <button className="p-2 text-gray-400 hover:text-gray-600" onClick={onClose} style={{ minHeight: 44, minWidth: 44 }}><X size={16} /></button>
      </div>
      <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-3 text-sm">
          {[
            ['日志 ID', log.id],
            ['时间', log.time],
            ['用户', log.user],
            ['操作', log.action],
            ['资源', log.resource],
            ['结果', log.result],
            ['IP 地址', log.ip],
          ].map(([k, v]) => (
            <div key={k} className={k === '操作' || k === '资源' ? 'col-span-2' : ''}>
              <div className="text-xs text-gray-400 mb-0.5">{k}</div>
              <div className="text-sm font-medium text-gray-800">{v}</div>
            </div>
          ))}
        </div>

        <div className="border-t pt-4" style={{ borderColor: 'var(--border)' }}>
          <button
            className="flex items-center gap-1.5 text-sm font-medium text-gray-700 mb-2"
            onClick={() => setShowJson(!showJson)}
          >
            {showJson ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            详细数据
          </button>
          {showJson && (
            <pre className="bg-gray-900 text-green-400 rounded-xl p-3 text-[11px] font-mono overflow-x-auto">
              {JSON.stringify(log.details, null, 2)}
            </pre>
          )}
        </div>
      </div>
    </div>
  )
}

export default function AuditLog({ onMenuOpen }: { onMenuOpen?: () => void }) {
  const [search, setSearch] = useState('')
  const [selectedLog, setSelectedLog] = useState<typeof logs[0] | null>(null)

  const filtered = logs.filter((l) =>
    !search || l.user.includes(search) || l.action.includes(search) || l.resource.includes(search)
  )

  return (
    <div className="flex flex-col min-h-screen">
      <TopBar breadcrumbs={['组织管理', '审计日志']} pageTitle="审计日志" onMenuOpen={onMenuOpen} />
      <div className="flex-1 p-4 md:p-6 flex flex-col gap-4">
        <div>
          <h1 className="text-lg md:text-xl font-semibold text-gray-900">审计日志</h1>
          <p className="text-sm text-gray-500 mt-0.5 hidden md:block">所有用户操作和系统事件的只读记录</p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative flex-1 min-w-0 md:flex-none">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="搜索用户或操作..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 pr-3 py-2 text-sm border rounded-lg bg-white focus:outline-none w-full"
              style={{ borderColor: 'var(--border)', minHeight: 44 }}
            />
          </div>
          {['用户', '操作类型', '资源类型'].map((f) => (
            <select key={f} className="px-3 py-2 text-sm border rounded-lg bg-white focus:outline-none hidden md:block" style={{ borderColor: 'var(--border)', minHeight: 44 }}>
              <option>全部{f}</option>
            </select>
          ))}
          <div className="hidden md:flex items-center gap-2">
            <input type="date" className="px-3 py-2 text-sm border rounded-lg bg-white focus:outline-none" style={{ borderColor: 'var(--border)' }} />
            <span className="text-gray-400 text-xs">至</span>
            <input type="date" className="px-3 py-2 text-sm border rounded-lg bg-white focus:outline-none" style={{ borderColor: 'var(--border)' }} />
          </div>
        </div>

        {/* Desktop table - horizontally scrollable */}
        <div className="hidden md:block bg-white border rounded-xl overflow-hidden" style={{ borderColor: 'var(--border)' }}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm" style={{ minWidth: 720 }}>
              <thead>
                <tr className="border-b" style={{ borderColor: 'var(--border)', background: '#fafafa' }}>
                  {['时间', '用户', '操作', '资源', '结果', 'IP / 设备', '详情'].map((h) => (
                    <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-gray-500 whitespace-nowrap">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((l) => (
                  <tr key={l.id} className="border-b last:border-0 hover:bg-gray-50" style={{ borderColor: 'var(--border)' }}>
                    <td className="px-4 py-3 text-xs text-gray-500 whitespace-nowrap font-mono">{l.time}</td>
                    <td className="px-4 py-3 text-xs font-medium text-gray-800 whitespace-nowrap">{l.user}</td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 rounded text-xs font-medium" style={{ background: '#eef2ff', color: actionColors[l.action] ?? '#374151' }}>
                        {l.action}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-600 max-w-[160px] truncate">{l.resource}</td>
                    <td className="px-4 py-3">
                      <span className={`text-xs font-medium ${l.result === '成功' ? 'text-green-600' : 'text-red-500'}`}>{l.result}</span>
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-400 font-mono whitespace-nowrap">{l.ip}</td>
                    <td className="px-4 py-3">
                      <button className="text-xs px-2.5 py-1 border rounded-lg hover:bg-gray-50" style={{ borderColor: 'var(--border)', color: 'var(--primary)' }} onClick={() => setSelectedLog(l)}>
                        查看
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Mobile timeline cards */}
        <div className="md:hidden flex flex-col gap-0">
          {filtered.map((l, i) => (
            <div key={l.id} className="flex gap-3 py-3">
              <div className="flex flex-col items-center">
                <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0 ${l.result === '成功' ? 'bg-green-500' : 'bg-red-400'}`} />
                {i < filtered.length - 1 && <div className="w-px flex-1 mt-1" style={{ background: '#e5e7eb', minHeight: 24 }} />}
              </div>
              <div
                className="flex-1 bg-white border rounded-xl p-3 mb-2 cursor-pointer"
                style={{ borderColor: 'var(--border)' }}
                onClick={() => setSelectedLog(l)}
              >
                <div className="flex items-start justify-between gap-2">
                  <span className="px-2 py-0.5 rounded text-xs font-medium" style={{ background: '#eef2ff', color: actionColors[l.action] ?? '#374151' }}>{l.action}</span>
                  <span className="text-[11px] text-gray-400 shrink-0">{l.time}</span>
                </div>
                <div className="mt-1.5 text-sm text-gray-800 truncate">{l.resource}</div>
                <div className="text-xs text-gray-400 mt-0.5">{l.user} · {l.ip}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {selectedLog && <DetailDrawer log={selectedLog} onClose={() => setSelectedLog(null)} />}
      {selectedLog && <div className="fixed inset-0 bg-black/20 z-40 hidden md:block" onClick={() => setSelectedLog(null)} />}
    </div>
  )
}
