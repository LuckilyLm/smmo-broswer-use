import { useState } from 'react'
import { Search, Bell, Globe, ChevronDown, RefreshCw, Plus, Menu, X } from 'lucide-react'

interface TopBarProps {
  breadcrumbs: string[]
  onRefresh?: () => void
  onCreateCampaign?: () => void
  showCreateCampaign?: boolean
  onMenuOpen?: () => void
  pageTitle?: string
}

export default function TopBar({
  breadcrumbs, onRefresh, onCreateCampaign, showCreateCampaign,
  onMenuOpen, pageTitle
}: TopBarProps) {
  const [lang, setLang] = useState<'zh' | 'en'>('zh')
  const [notifOpen, setNotifOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)

  const title = pageTitle || breadcrumbs[breadcrumbs.length - 1] || ''

  return (
    <header
      className="flex items-center gap-2 px-3 md:px-6 border-b bg-white sticky top-0 z-30 shrink-0"
      style={{ height: 52, borderColor: 'var(--border)' }}
    >
      {/* Mobile: hamburger + title */}
      <button
        className="md:hidden flex items-center justify-center rounded-lg hover:bg-gray-100 text-gray-500 shrink-0"
        style={{ minWidth: 44, minHeight: 44 }}
        onClick={onMenuOpen}
      >
        <Menu size={18} />
      </button>
      <span className="md:hidden text-sm font-semibold text-gray-900 truncate flex-1 min-w-0">{title}</span>

      {/* Desktop: breadcrumbs */}
      <nav className="hidden md:flex items-center gap-1.5 text-sm flex-1 min-w-0">
        {breadcrumbs.map((crumb, i) => (
          <span key={crumb} className="flex items-center gap-1.5 min-w-0">
            {i > 0 && <span className="text-gray-300 shrink-0">/</span>}
            <span className={`truncate ${i === breadcrumbs.length - 1 ? 'font-medium text-gray-800' : 'text-gray-400'}`}>
              {crumb}
            </span>
          </span>
        ))}
      </nav>

      {/* Mobile search expand */}
      {searchOpen && (
        <div className="md:hidden absolute inset-x-0 top-0 h-full bg-white flex items-center px-3 gap-2 z-40" style={{ borderBottom: '1px solid var(--border)' }}>
          <Search size={14} className="text-gray-400 shrink-0" />
          <input
            type="text"
            placeholder="搜索..."
            autoFocus
            className="flex-1 text-sm focus:outline-none"
          />
          <button
            className="p-2 text-gray-400"
            style={{ minWidth: 44, minHeight: 44 }}
            onClick={() => setSearchOpen(false)}
          >
            <X size={16} />
          </button>
        </div>
      )}

      {/* Desktop search */}
      <div className="relative hidden md:block">
        <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          placeholder="搜索..."
          className="pl-8 pr-3 py-1.5 text-sm border rounded-lg bg-gray-50 focus:outline-none focus:ring-1"
          style={{ width: 200, borderColor: 'var(--border)' }}
        />
      </div>

      {/* Mobile search icon */}
      <button
        className="md:hidden flex items-center justify-center text-gray-500 shrink-0"
        style={{ minWidth: 44, minHeight: 44 }}
        onClick={() => setSearchOpen(true)}
      >
        <Search size={16} />
      </button>

      {/* Notifications */}
      <div className="relative">
        <button
          className="relative flex items-center justify-center rounded-lg hover:bg-gray-100 transition-colors shrink-0"
          style={{ minWidth: 44, minHeight: 44 }}
          onClick={() => setNotifOpen(!notifOpen)}
        >
          <Bell size={16} className="text-gray-500" />
          <span className="absolute top-2 right-2 w-1.5 h-1.5 rounded-full bg-red-500" />
        </button>
        {notifOpen && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setNotifOpen(false)} />
            <div
              className="absolute right-0 top-full mt-1 w-80 max-w-[calc(100vw-16px)] bg-white border rounded-xl shadow-lg z-50"
              style={{ borderColor: 'var(--border)' }}
            >
              <div className="px-4 py-3 border-b flex items-center justify-between" style={{ borderColor: 'var(--border)' }}>
                <span className="font-semibold text-sm">通知中心</span>
                <span className="text-xs text-indigo-600 cursor-pointer">全部标为已读</span>
              </div>
              <div className="py-2 max-h-72 overflow-y-auto">
                {[
                  { title: '2 个回复计划待审批', time: '5 分钟前', dot: '#4338ca' },
                  { title: '营销活动「跨境电商引流」执行异常', time: '1 小时前', dot: '#ef4444' },
                  { title: '今日扫描完成：1,284 条评论', time: '2 小时前', dot: '#10b981' },
                ].map((n, i) => (
                  <div key={i} className="px-4 py-2.5 hover:bg-gray-50 flex gap-3 cursor-pointer" style={{ minHeight: 44 }}>
                    <span className="w-2 h-2 rounded-full shrink-0 mt-1.5" style={{ background: n.dot }} />
                    <div>
                      <div className="text-sm text-gray-800">{n.title}</div>
                      <div className="text-xs text-gray-400 mt-0.5">{n.time}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </>
        )}
      </div>

      {/* Language - desktop only */}
      <button
        className="hidden md:flex items-center gap-1 px-2.5 py-1.5 text-xs border rounded-lg hover:bg-gray-50 transition-colors shrink-0"
        style={{ borderColor: 'var(--border)', color: '#374151' }}
        onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')}
      >
        <Globe size={13} />
        {lang === 'zh' ? '中文' : 'EN'}
        <ChevronDown size={11} className="text-gray-400" />
      </button>

      {/* Refresh - desktop only */}
      {onRefresh && (
        <button
          className="hidden md:flex items-center justify-center rounded-lg border hover:bg-gray-50 transition-colors shrink-0"
          style={{ width: 34, height: 34, borderColor: 'var(--border)' }}
          onClick={onRefresh}
        >
          <RefreshCw size={14} className="text-gray-500" />
        </button>
      )}

      {/* Create campaign - desktop only */}
      {showCreateCampaign && onCreateCampaign && (
        <button
          className="hidden md:flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-lg text-white hover:opacity-90 shrink-0"
          style={{ background: 'var(--primary)' }}
          onClick={onCreateCampaign}
        >
          <Plus size={14} />
          新建活动
        </button>
      )}

      {/* User avatar */}
      <div
        className="rounded-full flex items-center justify-center text-white text-xs font-semibold cursor-pointer shrink-0"
        style={{ width: 28, height: 28, minWidth: 28, background: 'var(--primary)' }}
      >
        王
      </div>
    </header>
  )
}
