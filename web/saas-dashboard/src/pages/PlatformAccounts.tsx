import { useState } from 'react'
import { Plus, RefreshCw, Play, Square, RotateCcw, LogIn, AlertTriangle, CheckCircle, X, MoreVertical } from 'lucide-react'
import TopBar from '../components/layout/TopBar'
import StatusBadge from '../components/ui/StatusBadge'
import ConfirmModal from '../components/ui/ConfirmModal'

const accounts = [
  { id: 1, platform: 'Facebook', handle: '@smmo_business', displayName: 'SMMO 商务号', connectionStatus: '已连接', loginStatus: '登录有效', runtimeStatus: '运行中', cdpPort: 9222, profileStatus: '正常', lastChecked: '5 分钟前', color: '#1877f2' },
  { id: 2, platform: 'Instagram', handle: '@smmo_official', displayName: 'SMMO 官方号', connectionStatus: '已连接', loginStatus: '登录有效', runtimeStatus: '运行中', cdpPort: 9223, profileStatus: '正常', lastChecked: '8 分钟前', color: '#e1306c' },
  { id: 3, platform: 'TikTok', handle: '@smmo_tiktok', displayName: 'SMMO TikTok', connectionStatus: '已连接', loginStatus: '登录有效', runtimeStatus: '运行中', cdpPort: 9224, profileStatus: '正常', lastChecked: '15 分钟前', color: '#010101' },
  { id: 4, platform: 'X', handle: '@smmo_x', displayName: 'SMMO X Account', connectionStatus: '需要重新登录', loginStatus: '需要重新登录', runtimeStatus: '异常', cdpPort: 9225, profileStatus: '会话过期', lastChecked: '2 小时前', color: '#1da1f2' },
  { id: 5, platform: 'YouTube', handle: '@smmo_channel', displayName: 'SMMO Channel', connectionStatus: '已停止', loginStatus: '登录有效', runtimeStatus: '已停止', cdpPort: null, profileStatus: '正常', lastChecked: '3 小时前', color: '#ff0000' },
]

function runtimeBg(status: string) {
  if (status === '运行中') return '#10b981'
  if (status === '异常') return '#ef4444'
  return '#d1d5db'
}

interface PlatformAccountsProps {
  onMenuOpen?: () => void
}

export default function PlatformAccounts({ onMenuOpen }: PlatformAccountsProps) {
  const [confirmStop, setConfirmStop] = useState<number | null>(null)
  const [openMenu, setOpenMenu] = useState<number | null>(null)

  return (
    <div className="flex flex-col min-h-screen" onClick={() => setOpenMenu(null)}>
      <TopBar breadcrumbs={['获客管理', '平台账号']} pageTitle="平台账号" onMenuOpen={onMenuOpen} />
      <div className="flex-1 p-4 md:p-6 flex flex-col gap-4">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold text-gray-900">平台账号</h1>
            <p className="text-sm text-gray-500 mt-0.5 hidden md:block">管理已连接的社媒平台账号和浏览器运行时</p>
          </div>
          <div className="flex items-center gap-2">
            <button className="flex items-center gap-1.5 px-3 py-2.5 text-sm border rounded-lg hover:bg-gray-50" style={{ borderColor: 'var(--border)', minHeight: 44 }}>
              <RefreshCw size={13} /> 全部刷新
            </button>
            <button
              className="flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium rounded-lg text-white hover:opacity-90"
              style={{ background: 'var(--primary)', minHeight: 44 }}
            >
              <Plus size={14} /> 添加账号
            </button>
          </div>
        </div>

        {/* Desktop table */}
        <div className="hidden md:block bg-white border rounded-xl overflow-hidden" style={{ borderColor: 'var(--border)' }}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[760px]">
              <thead>
                <tr className="border-b text-left" style={{ borderColor: 'var(--border)', background: '#fafafa' }}>
                  {['账号', '平台', '连接状态', '登录状态', '运行时状态', 'CDP 端口', '最近检查', '操作'].map((h) => (
                    <th key={h} className="px-4 py-3 text-xs font-semibold text-gray-500">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {accounts.map((acc) => (
                  <tr
                    key={acc.id}
                    className="border-b hover:bg-gray-50 transition-colors"
                    style={{ borderColor: 'var(--border)', background: acc.runtimeStatus === '异常' ? '#fff5f5' : 'white' }}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className="w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-white text-xs font-bold" style={{ background: acc.color }}>
                          {acc.platform[0]}
                        </div>
                        <div className="min-w-0">
                          <div className="font-medium text-gray-800 truncate">{acc.displayName}</div>
                          <div className="text-xs text-gray-400">{acc.handle}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-600">{acc.platform}</td>
                    <td className="px-4 py-3"><StatusBadge status={acc.connectionStatus} /></td>
                    <td className="px-4 py-3">
                      {acc.loginStatus === '登录有效'
                        ? <span className="flex items-center gap-1 text-green-600 text-xs"><CheckCircle size={11} /> 登录有效</span>
                        : <span className="flex items-center gap-1 text-amber-600 text-xs"><AlertTriangle size={11} /> {acc.loginStatus}</span>
                      }
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1.5">
                        <div className="w-2 h-2 rounded-full" style={{ background: runtimeBg(acc.runtimeStatus) }} />
                        <span className="text-sm">{acc.runtimeStatus}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-gray-500">{acc.cdpPort ?? '—'}</td>
                    <td className="px-4 py-3 text-gray-400">{acc.lastChecked}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        {acc.runtimeStatus === '运行中' && (
                          <button className="p-2 text-gray-400 hover:text-red-600 rounded-lg" title="停止" style={{ minHeight: 36, minWidth: 36 }} onClick={() => setConfirmStop(acc.id)}><Square size={12} /></button>
                        )}
                        {acc.runtimeStatus !== '运行中' && (
                          <button className="p-2 text-gray-400 hover:text-green-600 rounded-lg" title="启动" style={{ minHeight: 36, minWidth: 36 }}><Play size={12} /></button>
                        )}
                        <button className="p-2 text-gray-400 hover:text-indigo-600 rounded-lg" title="重启" style={{ minHeight: 36, minWidth: 36 }}><RotateCcw size={12} /></button>
                        {acc.loginStatus !== '登录有效' && (
                          <button className="p-2 text-amber-500 hover:text-amber-700 rounded-lg" title="重新登录" style={{ minHeight: 36, minWidth: 36 }}><LogIn size={12} /></button>
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
        <div className="md:hidden flex flex-col gap-3">
          {accounts.map((acc) => (
            <div
              key={acc.id}
              className="bg-white border rounded-xl p-4 relative"
              style={{ borderColor: acc.runtimeStatus === '异常' ? '#fca5a5' : 'var(--border)' }}
            >
              <div className="flex items-start gap-3">
                <div className="w-10 h-10 rounded-full flex items-center justify-center shrink-0 text-white text-sm font-bold" style={{ background: acc.color }}>
                  {acc.platform[0]}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="font-medium text-sm text-gray-800 truncate">{acc.displayName}</div>
                      <div className="text-xs text-gray-400">{acc.handle}</div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <div className="w-2 h-2 rounded-full" style={{ background: runtimeBg(acc.runtimeStatus) }} />
                      <span className="text-xs text-gray-600">{acc.runtimeStatus}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 mt-1.5 flex-wrap">
                    <StatusBadge status={acc.connectionStatus} />
                    {acc.loginStatus !== '登录有效' && (
                      <span className="flex items-center gap-1 text-amber-600 text-xs"><AlertTriangle size={11} /> {acc.loginStatus}</span>
                    )}
                  </div>
                </div>

                {/* Overflow menu */}
                <div className="relative shrink-0" onClick={(e) => e.stopPropagation()}>
                  <button
                    className="p-2 text-gray-400 hover:text-gray-600 rounded-lg"
                    style={{ minHeight: 44, minWidth: 44 }}
                    onClick={() => setOpenMenu(openMenu === acc.id ? null : acc.id)}
                  >
                    <MoreVertical size={16} />
                  </button>
                  {openMenu === acc.id && (
                    <div className="absolute right-0 top-10 z-10 bg-white border rounded-xl shadow-lg py-1 min-w-[120px]" style={{ borderColor: 'var(--border)' }}>
                      {acc.runtimeStatus === '运行中' ? (
                        <button className="w-full px-4 py-2.5 text-sm text-left text-red-600 flex items-center gap-2" style={{ minHeight: 44 }} onClick={() => { setConfirmStop(acc.id); setOpenMenu(null) }}>
                          <Square size={13} /> 停止
                        </button>
                      ) : (
                        <button className="w-full px-4 py-2.5 text-sm text-left text-green-600 flex items-center gap-2" style={{ minHeight: 44 }}>
                          <Play size={13} /> 启动
                        </button>
                      )}
                      <button className="w-full px-4 py-2.5 text-sm text-left text-gray-700 flex items-center gap-2" style={{ minHeight: 44 }}>
                        <RotateCcw size={13} /> 重启
                      </button>
                      {acc.loginStatus !== '登录有效' && (
                        <button className="w-full px-4 py-2.5 text-sm text-left text-amber-600 flex items-center gap-2" style={{ minHeight: 44 }}>
                          <LogIn size={13} /> 重新登录
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-3 mt-3 text-xs text-gray-400">
                <span>检查：{acc.lastChecked}</span>
                {acc.cdpPort && <span>CDP：{acc.cdpPort}</span>}
              </div>
            </div>
          ))}
        </div>
      </div>

      <ConfirmModal
        open={confirmStop !== null}
        title="停止账号运行时"
        description="停止后该账号的所有扫描任务将暂停，直到手动重新启动。"
        confirmLabel="停止"
        destructive
        onConfirm={() => setConfirmStop(null)}
        onCancel={() => setConfirmStop(null)}
      />
    </div>
  )
}
