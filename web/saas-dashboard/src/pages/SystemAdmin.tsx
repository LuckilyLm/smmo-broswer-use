import { useState } from 'react'
import { Shield, Users, Server, CheckCircle, AlertTriangle } from 'lucide-react'

import StatusBadge from '../components/ui/StatusBadge'
import ConfirmModal from '../components/ui/ConfirmModal'

const tabs = ['租户管理', '用户管理', '功能标志', '运行时概况', '系统健康']

const tenants = [
  { id: 'T-001', name: '科技有限公司', plan: '专业版', members: 4, campaigns: 7, status: '活跃', created: '2024-01-15' },
  { id: 'T-002', name: '贸易集团', plan: '基础版', members: 2, campaigns: 3, status: '活跃', created: '2024-03-20' },
  { id: 'T-003', name: '测试租户', plan: '试用', members: 1, campaigns: 1, status: '已暂停', created: '2024-06-01' },
]

const flags = [
  { key: 'llm_enhancement', label: 'LLM 增强', desc: '允许租户启用 AI 回复增强功能', enabled: true },
  { key: 'auto_reply', label: '自动执行回复', desc: '允许在无审批的情况下自动发送回复（高风险）', enabled: false },
  { key: 'bulk_import', label: '批量导入', desc: '允许通过 CSV 批量导入关键词和活动', enabled: true },
  { key: 'api_access', label: 'API 访问', desc: '允许通过 REST API 访问数据', enabled: false },
]

const health = [
  { service: 'API', status: '正常', latency: '12ms', uptime: '99.98%' },
  { service: 'Worker', status: '正常', latency: '—', uptime: '99.95%' },
  { service: 'PostgreSQL', status: '正常', latency: '3ms', uptime: '100%' },
  { service: '浏览器运行时', status: '异常', latency: '—', uptime: '95.2%', note: '2 个实例离线' },
  { service: '任务队列', status: '正常', latency: '—', uptime: '99.9%' },
  { service: '调度器', status: '正常', latency: '—', uptime: '100%' },
]

export default function SystemAdmin({ onMenuOpen }: { onMenuOpen?: () => void }) {
  const [activeTab, setActiveTab] = useState('系统健康')
  const [featureFlags, setFlags] = useState(flags)
  const [suspendId, setSuspendId] = useState<string | null>(null)

  return (
    <div className="flex min-h-full flex-col">
      <div className="flex-1 p-4 md:p-6 flex flex-col gap-4">
        <div className="flex items-center gap-2">
          <Shield size={20} style={{ color: 'var(--primary)' }} />
          <div>
            <h1 className="text-lg md:text-xl font-semibold text-gray-900">系统管理</h1>
            <p className="text-xs text-gray-400 hidden md:block">仅系统管理员可见</p>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b overflow-x-auto scrollbar-hide" style={{ borderColor: 'var(--border)' }}>
          {tabs.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className="px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap shrink-0"
              style={{
                borderBottomColor: activeTab === tab ? 'var(--primary)' : 'transparent',
                color: activeTab === tab ? 'var(--primary)' : '#6b7280',
              }}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* System health */}
        {activeTab === '系统健康' && (
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {health.map((h) => (
                <div
                  key={h.service}
                  className="bg-white border rounded-xl p-4"
                  style={{ borderColor: h.status === '异常' ? '#fca5a5' : 'var(--border)', background: h.status === '异常' ? '#fff1f2' : 'white' }}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="text-sm font-medium text-gray-800">{h.service}</div>
                    {h.status === '正常'
                      ? <CheckCircle size={14} className="text-green-500" />
                      : <AlertTriangle size={14} className="text-red-500" />
                    }
                  </div>
                  <div className="flex items-center gap-2 text-xs text-gray-500">
                    <span>可用率 <span className="font-medium text-gray-800">{h.uptime}</span></span>
                    {h.latency !== '—' && <span>延迟 <span className="font-medium">{h.latency}</span></span>}
                  </div>
                  {h.note && <div className="text-xs text-red-500 mt-1">{h.note}</div>}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tenant management */}
        {activeTab === '租户管理' && (
          <>
            <div className="hidden md:block bg-white border rounded-xl overflow-hidden" style={{ borderColor: 'var(--border)' }}>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b" style={{ borderColor: 'var(--border)', background: '#fafafa' }}>
                    {['租户 ID', '名称', '套餐', '成员', '活动', '状态', '创建时间', '操作'].map((h) => (
                      <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-gray-500">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {tenants.map((t) => (
                    <tr key={t.id} className="border-b last:border-0 hover:bg-gray-50" style={{ borderColor: 'var(--border)' }}>
                      <td className="px-4 py-3 text-xs font-mono text-gray-500">{t.id}</td>
                      <td className="px-4 py-3 font-medium text-gray-800">{t.name}</td>
                      <td className="px-4 py-3 text-xs text-gray-500">{t.plan}</td>
                      <td className="px-4 py-3 text-center text-gray-600">{t.members}</td>
                      <td className="px-4 py-3 text-center text-gray-600">{t.campaigns}</td>
                      <td className="px-4 py-3">
                        <span className={`text-xs font-medium ${t.status === '活跃' ? 'text-green-600' : 'text-amber-600'}`}>{t.status}</span>
                      </td>
                      <td className="px-4 py-3 text-xs text-gray-400">{t.created}</td>
                      <td className="px-4 py-3">
                        <button
                          className="text-xs px-2.5 py-1.5 border rounded-lg hover:bg-red-50 text-red-500"
                          style={{ borderColor: '#fca5a5' }}
                          onClick={() => setSuspendId(t.id)}
                        >
                          {t.status === '活跃' ? '暂停' : '恢复'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {/* Mobile cards */}
            <div className="md:hidden flex flex-col gap-2">
              {tenants.map((t) => (
                <div key={t.id} className="bg-white border rounded-xl p-4" style={{ borderColor: 'var(--border)' }}>
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="font-medium text-gray-900">{t.name}</div>
                      <div className="text-xs text-gray-400 mt-0.5">{t.id} · {t.plan}</div>
                    </div>
                    <span className={`text-xs font-medium ${t.status === '活跃' ? 'text-green-600' : 'text-amber-600'}`}>{t.status}</span>
                  </div>
                  <div className="flex gap-4 mt-3 text-xs text-gray-500">
                    <span>{t.members} 成员</span>
                    <span>{t.campaigns} 活动</span>
                    <span>创建 {t.created}</span>
                  </div>
                  <button
                    className="mt-3 w-full py-2.5 text-sm border rounded-lg text-red-500 hover:bg-red-50"
                    style={{ borderColor: '#fca5a5', minHeight: 44 }}
                    onClick={() => setSuspendId(t.id)}
                  >
                    {t.status === '活跃' ? '暂停租户' : '恢复租户'}
                  </button>
                </div>
              ))}
            </div>
          </>
        )}

        {/* Feature flags */}
        {activeTab === '功能标志' && (
          <div className="flex flex-col gap-2">
            {featureFlags.map((f) => (
              <div key={f.key} className="bg-white border rounded-xl p-4 flex items-start justify-between gap-4" style={{ borderColor: 'var(--border)' }}>
                <div>
                  <div className="text-sm font-medium text-gray-900">{f.label}</div>
                  <div className="text-xs text-gray-400 mt-0.5">{f.desc}</div>
                  <code className="text-[11px] text-gray-400 font-mono mt-1 block">{f.key}</code>
                </div>
                <div
                  className="w-11 h-6 rounded-full relative cursor-pointer shrink-0 mt-0.5"
                  style={{ background: f.enabled ? 'var(--primary)' : '#d1d5db' }}
                  onClick={() => setFlags((prev) => prev.map((x) => x.key === f.key ? { ...x, enabled: !x.enabled } : x))}
                >
                  <div className="absolute top-1 w-4 h-4 rounded-full bg-white transition-all" style={{ left: f.enabled ? 26 : 4 }} />
                </div>
              </div>
            ))}
          </div>
        )}

        {activeTab === '用户管理' && (
          <div className="flex flex-col items-center py-16 text-gray-400">
            <Users size={32} className="mb-3 text-gray-200" />
            <div className="text-sm">跨租户用户管理即将推出</div>
          </div>
        )}

        {activeTab === '运行时概况' && (
          <div className="flex flex-col items-center py-16 text-gray-400">
            <Server size={32} className="mb-3 text-gray-200" />
            <div className="text-sm">浏览器运行时实时概况即将推出</div>
          </div>
        )}
      </div>

      <ConfirmModal
        open={suspendId !== null}
        title="确认暂停租户"
        description="暂停后该租户下的所有成员将无法访问系统，所有活动将被停止。"
        confirmLabel="确认暂停"
        destructive
        onConfirm={() => setSuspendId(null)}
        onCancel={() => setSuspendId(null)}
      />
    </div>
  )
}
