import { useState } from 'react'
import {
  LayoutDashboard, Users, Megaphone, Tag, Inbox,
  FileText, GitBranch, CheckSquare, Clock,
  Activity, Zap, UserCheck, ScrollText,
  Bell, Settings, Shield, ChevronLeft, ChevronRight,
  ChevronDown, Building2, X
} from 'lucide-react'

interface NavItem {
  id: string
  label: string
  icon: React.ReactNode
  badge?: number
}

interface NavGroup {
  label: string
  items: NavItem[]
}

const navGroups: NavGroup[] = [
  {
    label: 'Overview',
    items: [
      { id: 'dashboard', label: '仪表盘', icon: <LayoutDashboard size={16} /> },
    ],
  },
  {
    label: '获客管理',
    items: [
      { id: 'platform-accounts', label: '平台账号', icon: <Users size={16} /> },
      { id: 'campaigns', label: '营销活动', icon: <Megaphone size={16} /> },
      { id: 'keywords', label: '关键词', icon: <Tag size={16} /> },
      { id: 'leads-inbox', label: '线索收件箱', icon: <Inbox size={16} />, badge: 21 },
    ],
  },
  {
    label: '回复自动化',
    items: [
      { id: 'reply-templates', label: '回复模板', icon: <FileText size={16} /> },
      { id: 'matching-rules', label: '匹配规则', icon: <GitBranch size={16} /> },
      { id: 'reply-tasks', label: '回复任务', icon: <CheckSquare size={16} />, badge: 14 },
      { id: 'reply-records', label: '回复记录', icon: <Clock size={16} /> },
    ],
  },
  {
    label: '运营管理',
    items: [
      { id: 'execution-records', label: '执行记录', icon: <Activity size={16} /> },
      { id: 'token-usage', label: 'Token 用量', icon: <Zap size={16} /> },
    ],
  },
  {
    label: '组织管理',
    items: [
      { id: 'members', label: '成员管理', icon: <UserCheck size={16} /> },
      { id: 'audit-log', label: '审计日志', icon: <ScrollText size={16} /> },
      { id: 'notifications', label: '通知中心', icon: <Bell size={16} />, badge: 3 },
    ],
  },
  {
    label: '系统',
    items: [
      { id: 'settings', label: '设置', icon: <Settings size={16} /> },
      { id: 'system-admin', label: '系统管理', icon: <Shield size={16} /> },
    ],
  },
]

interface SidebarProps {
  activePage: string
  onNavigate: (page: string) => void
  mobileOpen?: boolean
  onMobileClose?: () => void
}

function SidebarInner({
  activePage, onNavigate, collapsed, setCollapsed,
}: {
  activePage: string
  onNavigate: (page: string) => void
  collapsed: boolean
  setCollapsed: (v: boolean) => void
}) {
  const [workspace, setWorkspace] = useState('科技有限公司')
  const [wsOpen, setWsOpen] = useState(false)
  const workspaces = ['科技有限公司', '贸易集团', '营销中心']

  return (
    <>
      {/* Logo + workspace */}
      <div className="flex items-center gap-2 px-3 py-3 border-b shrink-0" style={{ borderColor: 'var(--border)' }}>
        <div
          className="flex items-center justify-center rounded-lg shrink-0"
          style={{ width: 32, height: 32, background: 'var(--primary)' }}
        >
          <span className="text-white font-bold text-xs">SM</span>
        </div>
        {!collapsed && (
          <div className="flex-1 min-w-0 relative">
            <button
              className="flex items-center gap-1 w-full text-left"
              onClick={() => setWsOpen(!wsOpen)}
            >
              <span className="text-sm font-semibold truncate text-gray-900">{workspace}</span>
              <ChevronDown size={12} className="shrink-0 text-gray-400" />
            </button>
            {wsOpen && (
              <div
                className="absolute top-full left-0 mt-1 w-44 bg-white border rounded-lg shadow-lg z-50 py-1"
                style={{ borderColor: 'var(--border)' }}
              >
                {workspaces.map((ws) => (
                  <button
                    key={ws}
                    className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 flex items-center gap-2"
                    onClick={() => { setWorkspace(ws); setWsOpen(false) }}
                  >
                    <Building2 size={13} className="text-gray-400" />
                    <span className="truncate">{ws}</span>
                    {ws === workspace && <span className="ml-auto w-1.5 h-1.5 rounded-full bg-indigo-600 shrink-0" />}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        <button
          className="ml-auto flex items-center justify-center rounded hover:bg-gray-100 text-gray-400 shrink-0 hidden md:flex"
          style={{ width: 24, height: 24 }}
          onClick={() => setCollapsed(!collapsed)}
        >
          {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-2 scrollbar-hide">
        {navGroups.map((group) => (
          <div key={group.label} className="mb-1">
            {!collapsed && (
              <div className="px-3 py-1 text-[11px] font-semibold tracking-wider text-gray-400 uppercase">
                {group.label}
              </div>
            )}
            {group.items.map((item) => {
              const isActive = activePage === item.id
              return (
                <button
                  key={item.id}
                  onClick={() => onNavigate(item.id)}
                  title={collapsed ? item.label : undefined}
                  className="w-full flex items-center gap-2.5 px-3 rounded-md mx-1 transition-colors"
                  style={{
                    width: 'calc(100% - 8px)',
                    color: isActive ? 'var(--primary)' : '#374151',
                    background: isActive ? 'var(--accent)' : 'transparent',
                    fontWeight: isActive ? 600 : 400,
                    minHeight: 36,
                    paddingTop: 6,
                    paddingBottom: 6,
                  }}
                  onMouseEnter={(e) => { if (!isActive) e.currentTarget.style.background = '#f9fafb' }}
                  onMouseLeave={(e) => { if (!isActive) e.currentTarget.style.background = 'transparent' }}
                >
                  <span className="shrink-0" style={{ color: isActive ? 'var(--primary)' : '#9ca3af' }}>
                    {item.icon}
                  </span>
                  {!collapsed && (
                    <>
                      <span className="flex-1 text-left truncate text-sm">{item.label}</span>
                      {item.badge !== undefined && (
                        <span
                          className="text-[11px] font-medium px-1.5 py-0.5 rounded-full shrink-0"
                          style={{ background: isActive ? 'var(--primary)' : '#e5e7eb', color: isActive ? '#fff' : '#374151' }}
                        >
                          {item.badge}
                        </span>
                      )}
                    </>
                  )}
                </button>
              )
            })}
            {!collapsed && <div className="my-1 mx-3 border-t" style={{ borderColor: 'var(--border)' }} />}
          </div>
        ))}
      </nav>

      {/* Bottom user */}
      {!collapsed && (
        <div className="border-t p-3 shrink-0" style={{ borderColor: 'var(--border)' }}>
          <div className="flex items-center gap-2">
            <div
              className="rounded-full flex items-center justify-center text-white text-xs font-semibold shrink-0"
              style={{ width: 28, height: 28, background: 'var(--primary)' }}
            >
              王
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium text-gray-800 truncate">王小明</div>
              <div className="text-[11px] text-gray-400 truncate">管理员</div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

export default function Sidebar({ activePage, onNavigate, mobileOpen, onMobileClose }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false)

  const handleNavigate = (page: string) => {
    onNavigate(page)
    onMobileClose?.()
  }

  return (
    <>
      {/* Desktop sidebar */}
      <aside
        className="hidden md:flex flex-col border-r bg-white shrink-0 transition-all duration-200"
        style={{
          width: collapsed ? 56 : 220,
          borderColor: 'var(--border)',
          height: '100vh',
          position: 'sticky',
          top: 0,
        }}
      >
        <SidebarInner
          activePage={activePage}
          onNavigate={handleNavigate}
          collapsed={collapsed}
          setCollapsed={setCollapsed}
        />
      </aside>

      {/* Mobile drawer overlay */}
      {mobileOpen && (
        <div className="md:hidden fixed inset-0 z-50 flex">
          <div
            className="absolute inset-0 bg-black/40"
            onClick={onMobileClose}
          />
          <aside
            className="relative flex flex-col bg-white shadow-xl"
            style={{ width: 260, height: '100%' }}
          >
            <button
              className="absolute top-3 right-3 p-2 rounded-lg hover:bg-gray-100 text-gray-400 z-10"
              onClick={onMobileClose}
              style={{ minHeight: 44, minWidth: 44 }}
            >
              <X size={18} />
            </button>
            <SidebarInner
              activePage={activePage}
              onNavigate={handleNavigate}
              collapsed={false}
              setCollapsed={() => {}}
            />
          </aside>
        </div>
      )}
    </>
  )
}
