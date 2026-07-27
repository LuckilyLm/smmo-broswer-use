import { useState } from 'react'
import { Search, RefreshCw, X, CheckCircle, AlertTriangle, FileText } from 'lucide-react'
import TopBar from '../components/layout/TopBar'
import StatusBadge from '../components/ui/StatusBadge'

const executions = [
  { id: 'EX-2847', campaign: '跨境电商引流', trigger: '定时', status: '已完成', stage: '—', keywords: 5, scanned: 284, candidates: 19, leads: 19, duration: '2m 31s', started: '07/24 10:05' },
  { id: 'EX-2846', campaign: '独立站获客', trigger: '定时', status: '已完成', stage: '—', keywords: 3, scanned: 201, candidates: 14, leads: 14, duration: '1m 58s', started: '07/24 09:48' },
  { id: 'EX-2845', campaign: 'TikTok 品牌曝光', trigger: '手动', status: '执行中', stage: '评论扫描', keywords: 4, scanned: 143, candidates: 9, leads: 9, duration: '—', started: '07/24 10:12' },
  { id: 'EX-2844', campaign: 'X 高净值用户', trigger: '定时', status: '异常', stage: '登录检查', keywords: 6, scanned: 0, candidates: 0, leads: 0, duration: '—', started: '07/23 22:00' },
  { id: 'EX-2843', campaign: '海外招商合作', trigger: '定时', status: '已完成', stage: '—', keywords: 7, scanned: 156, candidates: 8, leads: 8, duration: '1m 44s', started: '07/23 18:30' },
]

const timelineSteps = [
  { label: '任务入队', status: 'done', time: '10:12:03' },
  { label: 'Worker 认领', status: 'done', time: '10:12:04' },
  { label: '运行时检查', status: 'done', time: '10:12:08' },
  { label: '关键词搜索', status: 'done', time: '10:12:15' },
  { label: '评论扫描', status: 'active', time: '进行中...' },
  { label: '规则匹配', status: 'pending', time: '—' },
  { label: '候选生成', status: 'pending', time: '—' },
  { label: '完成', status: 'pending', time: '—' },
]

function ExecutionDrawer({ execId, onClose }: { execId: string; onClose: () => void }) {
  const exec = executions.find((e) => e.id === execId)
  if (!exec) return null

  return (
    <div className="fixed inset-0 md:inset-y-0 md:right-0 md:left-auto md:w-[520px] bg-white border-l flex flex-col z-40 shadow-xl" style={{ borderColor: 'var(--border)' }}>
      <div className="flex items-center justify-between px-4 py-3 border-b shrink-0" style={{ borderColor: 'var(--border)' }}>
        <div>
          <h3 className="font-semibold text-gray-900">执行详情</h3>
          <div className="text-xs text-gray-400 mt-0.5 font-mono">{exec.id} · {exec.campaign}</div>
        </div>
        <button className="text-gray-400 hover:text-gray-600 p-2" onClick={onClose} style={{ minHeight: 44, minWidth: 44 }}><X size={16} /></button>
      </div>
      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-5">
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: '扫描评论', value: exec.scanned },
            { label: '候选线索', value: exec.candidates },
            { label: '最终线索', value: exec.leads },
          ].map((m) => (
            <div key={m.label} className="bg-gray-50 border rounded-xl p-3 text-center" style={{ borderColor: 'var(--border)' }}>
              <div className="text-xl font-bold text-gray-900">{m.value}</div>
              <div className="text-[11px] text-gray-400 mt-0.5">{m.label}</div>
            </div>
          ))}
        </div>

        <div>
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">执行时间线</div>
          <div className="flex flex-col gap-0">
            {timelineSteps.map((step, i) => (
              <div key={i} className="flex gap-3">
                <div className="flex flex-col items-center">
                  <div
                    className="w-5 h-5 rounded-full flex items-center justify-center shrink-0"
                    style={{
                      background: step.status === 'done' ? '#10b981' : step.status === 'active' ? 'var(--primary)' : '#e5e7eb',
                    }}
                  >
                    {step.status === 'done' && <CheckCircle size={10} color="white" />}
                    {step.status === 'active' && <div className="w-2 h-2 rounded-full bg-white animate-pulse" />}
                    {step.status === 'pending' && <div className="w-1.5 h-1.5 rounded-full bg-gray-300" />}
                  </div>
                  {i < timelineSteps.length - 1 && (
                    <div className="w-px my-1" style={{ height: 20, background: step.status === 'done' ? '#10b981' : '#e5e7eb' }} />
                  )}
                </div>
                <div className="flex items-center justify-between flex-1 pb-3">
                  <span className={`text-sm ${step.status === 'pending' ? 'text-gray-300' : 'text-gray-700'} font-medium`}>{step.label}</span>
                  <span className={`text-xs ${step.status === 'done' ? 'text-gray-400' : step.status === 'active' ? 'text-indigo-500 font-medium' : 'text-gray-300'}`}>{step.time}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div>
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">执行日志</div>
          <div className="overflow-x-auto">
            <pre className="bg-gray-900 rounded-xl p-3 font-mono text-[11px] text-green-400 max-h-48 overflow-y-auto leading-relaxed min-w-0 whitespace-pre-wrap break-all">
{`[10:12:03] 任务 ${exec.id} 已入队
[10:12:04] Worker-3 认领任务
[10:12:08] 运行时检查通过，浏览器实例就绪
[10:12:15] 开始搜索关键词 (${exec.keywords} 个)
[10:12:22] 关键词 "跨境电商" → 发现 48 个帖子
[10:12:35] 关键词 "代购" → 发现 62 个帖子`}
            </pre>
          </div>
        </div>

        <div>
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">产物</div>
          <div className="flex gap-2 flex-wrap">
            <button className="flex items-center gap-1.5 px-3 py-2.5 text-xs border rounded-lg hover:bg-gray-50" style={{ borderColor: 'var(--border)', minHeight: 44 }}>
              <FileText size={11} /> 下载日志
            </button>
          </div>
        </div>

        {exec.status === '异常' && (
          <div className="border rounded-xl p-4" style={{ background: '#fff1f2', borderColor: '#fca5a5' }}>
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle size={14} className="text-red-500" />
              <span className="text-sm font-semibold text-red-700">执行异常</span>
            </div>
            <div className="text-xs text-red-600 mb-3">登录检查失败：账号 @smmo_x 会话已过期，需要重新登录。</div>
            <button className="flex items-center gap-1.5 px-3 py-2.5 text-xs font-medium rounded-lg text-white hover:opacity-90" style={{ background: '#ef4444', minHeight: 44 }}>
              <RefreshCw size={11} /> 重试
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

interface ExecutionRecordsProps {
  onMenuOpen?: () => void
}

export default function ExecutionRecords({ onMenuOpen }: ExecutionRecordsProps) {
  const [search, setSearch] = useState('')
  const [openDrawer, setOpenDrawer] = useState<string | null>(null)

  const filtered = executions.filter((e) =>
    !search || e.campaign.includes(search) || e.id.includes(search)
  )

  return (
    <div className="flex flex-col min-h-screen">
      <TopBar breadcrumbs={['运营管理', '执行记录']} pageTitle="执行记录" onMenuOpen={onMenuOpen} />
      <div className="flex-1 p-4 md:p-6 flex flex-col gap-4">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-gray-900">执行记录</h1>
          <p className="text-sm text-gray-500 mt-0.5 hidden md:block">查看所有营销活动的扫描和处理执行历史</p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative flex-1 min-w-0" style={{ maxWidth: 240 }}>
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="搜索执行记录..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 pr-3 py-2.5 text-sm border rounded-lg bg-white focus:outline-none w-full"
              style={{ borderColor: 'var(--border)', minHeight: 44 }}
            />
          </div>
          <select className="px-3 py-2.5 text-sm border rounded-lg bg-white focus:outline-none" style={{ borderColor: 'var(--border)', minHeight: 44 }}>
            {['全部状态', '已完成', '执行中', '异常'].map((v) => <option key={v}>{v}</option>)}
          </select>
        </div>

        {/* Desktop table */}
        <div className="hidden md:block bg-white border rounded-xl overflow-hidden" style={{ borderColor: 'var(--border)' }}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[820px]">
              <thead>
                <tr className="border-b" style={{ borderColor: 'var(--border)', background: '#fafafa' }}>
                  {['执行 ID', '活动', '触发', '状态', '阶段', '关键词', '扫描', '候选', '线索', '耗时', '开始时间', '操作'].map((h) => (
                    <th key={h} className="text-left px-3 py-3 text-xs font-semibold text-gray-500">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((e) => (
                  <tr key={e.id} className="border-b last:border-0 hover:bg-gray-50 cursor-pointer" style={{ borderColor: 'var(--border)' }} onClick={() => setOpenDrawer(e.id)}>
                    <td className="px-3 py-3 font-mono text-xs text-gray-600">{e.id}</td>
                    <td className="px-3 py-3 font-medium text-gray-800 text-xs whitespace-nowrap">{e.campaign}</td>
                    <td className="px-3 py-3 text-gray-500 text-xs">{e.trigger}</td>
                    <td className="px-3 py-3"><StatusBadge status={e.status} variant="dot" /></td>
                    <td className="px-3 py-3 text-gray-400 text-xs">{e.stage}</td>
                    <td className="px-3 py-3 text-center text-gray-600 text-xs">{e.keywords}</td>
                    <td className="px-3 py-3 text-center text-gray-600 text-xs">{e.scanned}</td>
                    <td className="px-3 py-3 text-center text-gray-600 text-xs">{e.candidates}</td>
                    <td className="px-3 py-3 text-center font-medium text-xs" style={{ color: e.leads > 0 ? '#10b981' : '#9ca3af' }}>{e.leads}</td>
                    <td className="px-3 py-3 text-gray-500 text-xs font-mono">{e.duration}</td>
                    <td className="px-3 py-3 text-gray-400 text-xs whitespace-nowrap">{e.started}</td>
                    <td className="px-3 py-3">
                      <button className="text-xs text-indigo-600 hover:underline" style={{ minHeight: 36 }}>详情</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Mobile cards */}
        <div className="md:hidden flex flex-col gap-3">
          {filtered.map((e) => (
            <div
              key={e.id}
              className="bg-white border rounded-xl p-4 cursor-pointer active:bg-gray-50"
              style={{ borderColor: e.status === '异常' ? '#fca5a5' : 'var(--border)' }}
              onClick={() => setOpenDrawer(e.id)}
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <div className="min-w-0">
                  <div className="font-medium text-sm text-gray-800 truncate">{e.campaign}</div>
                  <div className="text-xs text-gray-400 font-mono">{e.id} · {e.trigger} · {e.started}</div>
                </div>
                <StatusBadge status={e.status} variant="dot" />
              </div>
              <div className="grid grid-cols-3 gap-2 mt-2">
                {[
                  { label: '扫描', value: e.scanned },
                  { label: '候选', value: e.candidates },
                  { label: '线索', value: e.leads },
                ].map(({ label, value }) => (
                  <div key={label} className="text-center">
                    <div className="text-sm font-semibold text-gray-800">{value}</div>
                    <div className="text-[11px] text-gray-400">{label}</div>
                  </div>
                ))}
              </div>
              {e.status === '异常' && (
                <div className="mt-2 text-xs text-red-500 flex items-center gap-1">
                  <AlertTriangle size={11} /> 登录检查失败，需要重新登录
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {openDrawer && (
        <>
          <div className="fixed inset-0 bg-black/20 z-30" onClick={() => setOpenDrawer(null)} />
          <ExecutionDrawer execId={openDrawer} onClose={() => setOpenDrawer(null)} />
        </>
      )}
    </div>
  )
}
