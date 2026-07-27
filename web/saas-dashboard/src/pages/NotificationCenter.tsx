import { useState } from 'react'
import { Bell, CheckCheck, Trash2, ExternalLink, X, AlertTriangle, Activity, Shield, CheckSquare } from 'lucide-react'
import TopBar from '../components/layout/TopBar'

type NotifType = 'all' | 'unread' | 'system' | 'execution' | 'security' | 'approval'

const typeConfig: Record<string, { icon: React.ReactNode; color: string; bg: string }> = {
  system: { icon: <Bell size={14} />, color: '#6366f1', bg: '#eef2ff' },
  execution: { icon: <Activity size={14} />, color: '#f59e0b', bg: '#fffbeb' },
  security: { icon: <Shield size={14} />, color: '#ef4444', bg: '#fee2e2' },
  approval: { icon: <CheckSquare size={14} />, color: '#10b981', bg: '#ecfdf5' },
}

const initialNotifs = [
  { id: 1, type: 'approval', title: '2 个回复计划待审批', body: '活动「跨境电商引流」共有 2 个新的回复候选需要审批。', read: false, time: '5 分钟前', link: 'reply-tasks' },
  { id: 2, type: 'execution', title: '营销活动执行异常', body: '活动「X 高净值用户」执行失败：账号登录已过期，请重新登录。', read: false, time: '1 小时前', link: 'execution-records' },
  { id: 3, type: 'system', title: '今日扫描完成', body: '系统今日共扫描 1,284 条评论，发现 86 条潜在线索。', read: false, time: '2 小时前', link: 'dashboard' },
  { id: 4, type: 'security', title: '新设备登录', body: '检测到新设备登录：Chrome / Windows，位置：广州。若非本人操作，请立即修改密码。', read: true, time: '3 小时前', link: 'settings' },
  { id: 5, type: 'approval', title: '5 个回复已审批', body: '活动「独立站获客」的 5 个回复候选已通过审批，等待系统发送开关开启后发送。', read: true, time: '昨天 18:30', link: 'reply-tasks' },
  { id: 6, type: 'system', title: '套餐用量提醒', body: '回复候选用量已达 24.3%（243/1000），请注意监控。', read: true, time: '昨天 09:00', link: 'token-usage' },
]

const TABS: { key: NotifType; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'unread', label: '未读' },
  { key: 'system', label: '系统' },
  { key: 'execution', label: '执行' },
  { key: 'security', label: '安全' },
  { key: 'approval', label: '审批' },
]

export default function NotificationCenter({ onMenuOpen, onNavigate }: { onMenuOpen?: () => void; onNavigate?: (p: string) => void }) {
  const [notifs, setNotifs] = useState(initialNotifs)
  const [activeTab, setActiveTab] = useState<NotifType>('all')

  const unreadCount = notifs.filter((n) => !n.read).length

  const filtered = notifs.filter((n) => {
    if (activeTab === 'unread') return !n.read
    if (activeTab !== 'all') return n.type === activeTab
    return true
  })

  const markAllRead = () => setNotifs((prev) => prev.map((n) => ({ ...n, read: true })))
  const markRead = (id: number) => setNotifs((prev) => prev.map((n) => n.id === id ? { ...n, read: true } : n))
  const deleteNotif = (id: number) => setNotifs((prev) => prev.filter((n) => n.id !== id))
  const clearRead = () => setNotifs((prev) => prev.filter((n) => !n.read))

  return (
    <div className="flex flex-col min-h-screen">
      <TopBar breadcrumbs={['组织管理', '通知中心']} pageTitle="通知中心" onMenuOpen={onMenuOpen} />
      <div className="flex-1 p-4 md:p-6 flex flex-col gap-4">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2">
            <h1 className="text-lg md:text-xl font-semibold text-gray-900">通知中心</h1>
            {unreadCount > 0 && (
              <span className="px-2 py-0.5 rounded-full text-xs font-medium text-white" style={{ background: '#ef4444' }}>{unreadCount}</span>
            )}
          </div>
          <div className="flex gap-2">
            <button
              className="flex items-center gap-1.5 px-3 py-2 text-sm border rounded-lg hover:bg-gray-50"
              style={{ borderColor: 'var(--border)', minHeight: 44 }}
              onClick={markAllRead}
              disabled={unreadCount === 0}
            >
              <CheckCheck size={14} /> 全部标为已读
            </button>
            <button
              className="flex items-center gap-1.5 px-3 py-2 text-sm border rounded-lg hover:bg-gray-50"
              style={{ borderColor: 'var(--border)', minHeight: 44, color: '#ef4444' }}
              onClick={clearRead}
            >
              <Trash2 size={14} /> 清除已读
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b overflow-x-auto scrollbar-hide" style={{ borderColor: 'var(--border)' }}>
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className="px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap shrink-0"
              style={{
                borderBottomColor: activeTab === tab.key ? 'var(--primary)' : 'transparent',
                color: activeTab === tab.key ? 'var(--primary)' : '#6b7280',
              }}
            >
              {tab.label}
              {tab.key === 'unread' && unreadCount > 0 && (
                <span className="ml-1.5 px-1.5 py-0.5 rounded-full text-[10px] font-medium" style={{ background: '#fee2e2', color: '#ef4444' }}>{unreadCount}</span>
              )}
            </button>
          ))}
        </div>

        {filtered.length === 0 ? (
          <div className="flex flex-col items-center py-20 text-gray-400">
            <Bell size={40} className="mb-3 text-gray-200" />
            <div className="text-sm">暂无通知</div>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            {filtered.map((n) => {
              const tc = typeConfig[n.type] ?? typeConfig.system
              return (
                <div
                  key={n.id}
                  className="bg-white border rounded-xl p-4 flex gap-3 transition-colors cursor-pointer"
                  style={{ borderColor: n.read ? 'var(--border)' : '#c7d2fe', background: n.read ? 'white' : '#fafbff' }}
                  onClick={() => markRead(n.id)}
                >
                  <div className="p-2 rounded-lg shrink-0 mt-0.5" style={{ background: tc.bg }}>
                    <span style={{ color: tc.color }}>{tc.icon}</span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-2">
                      <div className={`text-sm font-medium ${n.read ? 'text-gray-700' : 'text-gray-900'}`}>{n.title}</div>
                      <span className="text-[11px] text-gray-400 shrink-0 whitespace-nowrap">{n.time}</span>
                    </div>
                    <div className="text-xs text-gray-500 mt-1 leading-relaxed">{n.body}</div>
                    {n.link && onNavigate && (
                      <button
                        className="mt-2 flex items-center gap-1 text-xs font-medium hover:underline"
                        style={{ color: 'var(--primary)' }}
                        onClick={(e) => { e.stopPropagation(); onNavigate(n.link!) }}
                      >
                        <ExternalLink size={11} /> 查看详情
                      </button>
                    )}
                  </div>
                  <div className="flex flex-col gap-1 shrink-0">
                    {!n.read && <div className="w-2 h-2 rounded-full mt-1" style={{ background: 'var(--primary)' }} />}
                    <button
                      className="p-1 rounded hover:bg-gray-100 text-gray-300 hover:text-red-400"
                      style={{ minHeight: 32, minWidth: 32 }}
                      onClick={(e) => { e.stopPropagation(); deleteNotif(n.id) }}
                    >
                      <X size={12} />
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
