import { useState } from 'react'
import { Plus, Search, MoreHorizontal, UserPlus, Mail, X, AlertTriangle, CheckCircle } from 'lucide-react'
import TopBar from '../components/layout/TopBar'
import StatusBadge from '../components/ui/StatusBadge'
import ConfirmModal from '../components/ui/ConfirmModal'

const roles = ['Owner', 'Admin', 'Member', 'Viewer']

const roleColors: Record<string, { bg: string; text: string }> = {
  Owner: { bg: '#ede9fe', text: '#7c3aed' },
  Admin: { bg: '#dbeafe', text: '#1d4ed8' },
  Member: { bg: '#f0fdf4', text: '#15803d' },
  Viewer: { bg: '#f3f4f6', text: '#4b5563' },
}

const initialMembers = [
  { id: 1, name: '王小明', email: 'wang@company.com', role: 'Owner', status: '活跃', joined: '2024-01-15', lastActive: '10 分钟前', avatar: '王' },
  { id: 2, name: '李美华', email: 'li@company.com', role: 'Admin', status: '活跃', joined: '2024-02-20', lastActive: '1 小时前', avatar: '李' },
  { id: 3, name: '张伟国', email: 'zhang@company.com', role: 'Member', status: '活跃', joined: '2024-03-10', lastActive: '昨天', avatar: '张' },
  { id: 4, name: 'John Smith', email: 'john@partner.com', role: 'Viewer', status: '活跃', joined: '2024-05-01', lastActive: '3 天前', avatar: 'J' },
]

const pendingInvites = [
  { id: 101, email: 'newmember@company.com', role: 'Member', invitedAt: '2025-07-22', invitedBy: '王小明' },
]

interface InviteDrawerProps {
  onClose: () => void
  onInvite: (email: string, role: string) => void
}

function InviteDrawer({ onClose, onInvite }: InviteDrawerProps) {
  const [email, setEmail] = useState('')
  const [role, setRole] = useState('Member')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const valid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)

  const handleSubmit = async () => {
    if (!valid) { setError('请输入有效的邮箱地址'); return }
    setLoading(true); setError('')
    await new Promise((r) => setTimeout(r, 800))
    setLoading(false)
    onInvite(email, role)
    onClose()
  }

  return (
    <div className="fixed inset-0 md:inset-y-0 md:right-0 md:left-auto z-50 flex flex-col bg-white md:w-[400px] shadow-xl border-l" style={{ borderColor: 'var(--border)' }}>
      <div className="flex items-center justify-between px-5 py-4 border-b shrink-0" style={{ borderColor: 'var(--border)' }}>
        <h3 className="font-semibold text-gray-900">邀请成员</h3>
        <button className="p-2 text-gray-400 hover:text-gray-600" onClick={onClose} style={{ minHeight: 44, minWidth: 44 }}><X size={16} /></button>
      </div>
      <div className="flex-1 p-5 flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium text-gray-700">邮箱地址 <span className="text-red-500">*</span></label>
          <input
            type="email"
            placeholder="member@company.com"
            value={email}
            onChange={(e) => { setEmail(e.target.value); setError('') }}
            className="px-3 py-2.5 text-sm border rounded-lg focus:outline-none focus:ring-1"
            style={{
              borderColor: error ? '#ef4444' : 'var(--border)',
              outlineColor: 'var(--ring)',
              minHeight: 44,
            }}
          />
          {error && <p className="text-xs text-red-500 flex items-center gap-1"><AlertTriangle size={11} />{error}</p>}
        </div>
        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium text-gray-700">角色</label>
          <div className="flex flex-col gap-2">
            {roles.filter((r) => r !== 'Owner').map((r) => (
              <label
                key={r}
                className="flex items-start gap-3 p-3 border rounded-lg cursor-pointer transition-colors"
                style={{
                  borderColor: role === r ? 'var(--primary)' : 'var(--border)',
                  background: role === r ? 'var(--accent)' : 'white',
                }}
              >
                <input type="radio" name="role" value={r} checked={role === r} onChange={() => setRole(r)} className="mt-0.5" />
                <div>
                  <div className="text-sm font-medium text-gray-800">{r}</div>
                  <div className="text-xs text-gray-400 mt-0.5">
                    {r === 'Admin' && '可管理活动、账号和成员，但不能修改系统设置'}
                    {r === 'Member' && '可查看和操作活动、线索、回复任务'}
                    {r === 'Viewer' && '只读权限，无法创建或修改任何内容'}
                  </div>
                </div>
              </label>
            ))}
          </div>
        </div>
      </div>
      <div className="border-t p-4 flex gap-2 shrink-0" style={{ borderColor: 'var(--border)' }}>
        <button className="flex-1 px-4 py-2.5 text-sm border rounded-lg hover:bg-gray-50" style={{ borderColor: 'var(--border)', minHeight: 44 }} onClick={onClose}>取消</button>
        <button
          className="flex-1 px-4 py-2.5 text-sm font-medium rounded-lg text-white flex items-center justify-center gap-2 disabled:opacity-60"
          style={{ background: 'var(--primary)', minHeight: 44 }}
          disabled={!valid || loading}
          onClick={handleSubmit}
        >
          {loading ? <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" /> : <Mail size={13} />}
          发送邀请
        </button>
      </div>
    </div>
  )
}

export default function Members({ onMenuOpen }: { onMenuOpen?: () => void }) {
  const [members, setMembers] = useState(initialMembers)
  const [invites, setInvites] = useState(pendingInvites)
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('全部')
  const [inviteOpen, setInviteOpen] = useState(false)
  const [openMenu, setOpenMenu] = useState<number | null>(null)
  const [confirmRemove, setConfirmRemove] = useState<number | null>(null)

  const filtered = members.filter((m) => {
    if (search && !m.name.toLowerCase().includes(search.toLowerCase()) && !m.email.includes(search)) return false
    if (roleFilter !== '全部' && m.role !== roleFilter) return false
    return true
  })

  return (
    <div className="flex flex-col min-h-screen">
      <TopBar breadcrumbs={['组织管理', '成员管理']} pageTitle="成员管理" onMenuOpen={onMenuOpen} />
      <div className="flex-1 p-4 md:p-6 flex flex-col gap-4">
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div>
            <h1 className="text-lg md:text-xl font-semibold text-gray-900">成员管理</h1>
            <p className="text-sm text-gray-500 mt-0.5 hidden md:block">管理工作区成员和权限</p>
          </div>
          <button
            className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg text-white hover:opacity-90"
            style={{ background: 'var(--primary)', minHeight: 44 }}
            onClick={() => setInviteOpen(true)}
          >
            <UserPlus size={14} /> 邀请成员
          </button>
        </div>

        {/* Pending invites */}
        {invites.length > 0 && (
          <div className="bg-white border rounded-xl overflow-hidden" style={{ borderColor: 'var(--border)' }}>
            <div className="px-4 py-3 border-b bg-amber-50" style={{ borderColor: '#fcd34d' }}>
              <span className="text-xs font-semibold text-amber-700">待接受邀请 ({invites.length})</span>
            </div>
            {invites.map((inv) => (
              <div key={inv.id} className="flex items-center gap-3 px-4 py-3 border-b last:border-0 flex-wrap" style={{ borderColor: 'var(--border)' }}>
                <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center text-gray-500 text-xs font-semibold shrink-0">?</div>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-gray-800 truncate">{inv.email}</div>
                  <div className="text-xs text-gray-400">已邀请 · {inv.invitedAt}</div>
                </div>
                <span className="px-2 py-0.5 rounded text-xs font-medium shrink-0" style={{ background: roleColors[inv.role].bg, color: roleColors[inv.role].text }}>{inv.role}</span>
                <div className="flex gap-1 shrink-0">
                  <button className="text-xs px-2.5 py-1.5 border rounded-lg hover:bg-gray-50" style={{ borderColor: 'var(--border)', minHeight: 36 }}>重发邀请</button>
                  <button className="text-xs px-2.5 py-1.5 border rounded-lg hover:bg-red-50 text-red-500" style={{ borderColor: '#fca5a5', minHeight: 36 }} onClick={() => setInvites((i) => i.filter((x) => x.id !== inv.id))}>撤销</button>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Filters */}
        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative flex-1 min-w-0 md:flex-none">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="搜索成员..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 pr-3 py-2 text-sm border rounded-lg bg-white focus:outline-none w-full"
              style={{ borderColor: 'var(--border)', minHeight: 44 }}
            />
          </div>
          <select value={roleFilter} onChange={(e) => setRoleFilter(e.target.value)} className="px-3 py-2 text-sm border rounded-lg bg-white focus:outline-none" style={{ borderColor: 'var(--border)', minHeight: 44 }}>
            {['全部', ...roles].map((r) => <option key={r}>{r}</option>)}
          </select>
        </div>

        {/* Desktop table */}
        <div className="hidden md:block bg-white border rounded-xl overflow-hidden" style={{ borderColor: 'var(--border)' }}>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b" style={{ borderColor: 'var(--border)', background: '#fafafa' }}>
                {['成员', '邮箱', '角色', '状态', '加入时间', '最近活跃', '操作'].map((h) => (
                  <th key={h} className="text-left px-4 py-3 text-xs font-semibold text-gray-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((m) => (
                <tr key={m.id} className="border-b last:border-0 hover:bg-gray-50" style={{ borderColor: 'var(--border)' }}>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2.5">
                      <div className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-semibold shrink-0" style={{ background: 'var(--primary)' }}>{m.avatar}</div>
                      <span className="font-medium text-gray-800">{m.name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-gray-500 text-xs">{m.email}</td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-0.5 rounded text-xs font-medium" style={{ background: roleColors[m.role].bg, color: roleColors[m.role].text }}>{m.role}</span>
                  </td>
                  <td className="px-4 py-3"><StatusBadge status="运行中" /></td>
                  <td className="px-4 py-3 text-gray-400 text-xs">{m.joined}</td>
                  <td className="px-4 py-3 text-gray-400 text-xs">{m.lastActive}</td>
                  <td className="px-4 py-3">
                    <div className="relative">
                      <button
                        className="p-1.5 rounded hover:bg-gray-100 text-gray-400"
                        onClick={() => setOpenMenu(openMenu === m.id ? null : m.id)}
                      >
                        <MoreHorizontal size={14} />
                      </button>
                      {openMenu === m.id && (
                        <div className="absolute right-0 top-full mt-1 w-36 bg-white border rounded-lg shadow-lg z-20 py-1" style={{ borderColor: 'var(--border)' }}>
                          <button className="w-full text-left px-3 py-1.5 text-xs hover:bg-gray-50">更改角色</button>
                          {m.role !== 'Owner' && (
                            <button className="w-full text-left px-3 py-1.5 text-xs hover:bg-red-50 text-red-500" onClick={() => { setConfirmRemove(m.id); setOpenMenu(null) }}>移除成员</button>
                          )}
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Mobile cards */}
        <div className="md:hidden flex flex-col gap-2">
          {filtered.map((m) => (
            <div key={m.id} className="bg-white border rounded-xl p-4" style={{ borderColor: 'var(--border)' }}>
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2.5 min-w-0">
                  <div className="w-9 h-9 rounded-full flex items-center justify-center text-white text-sm font-semibold shrink-0" style={{ background: 'var(--primary)' }}>{m.avatar}</div>
                  <div className="min-w-0">
                    <div className="font-medium text-gray-900 truncate">{m.name}</div>
                    <div className="text-xs text-gray-400 truncate">{m.email}</div>
                  </div>
                </div>
                <span className="px-2 py-0.5 rounded text-xs font-medium shrink-0" style={{ background: roleColors[m.role].bg, color: roleColors[m.role].text }}>{m.role}</span>
              </div>
              <div className="flex items-center justify-between mt-3">
                <div className="text-xs text-gray-400">最近活跃：{m.lastActive}</div>
                <button className="p-2 rounded-lg hover:bg-gray-100 text-gray-400" style={{ minHeight: 44, minWidth: 44 }}><MoreHorizontal size={16} /></button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {inviteOpen && <InviteDrawer onClose={() => setInviteOpen(false)} onInvite={() => {}} />}
      {inviteOpen && <div className="fixed inset-0 bg-black/20 z-40 hidden md:block" onClick={() => setInviteOpen(false)} />}

      <ConfirmModal
        open={confirmRemove !== null}
        title="确认移除成员"
        description="移除后该成员将立即失去工作区访问权限，此操作不可撤销。"
        confirmLabel="移除"
        destructive
        onConfirm={() => { setMembers((prev) => prev.filter((m) => m.id !== confirmRemove)); setConfirmRemove(null) }}
        onCancel={() => setConfirmRemove(null)}
      />
    </div>
  )
}
