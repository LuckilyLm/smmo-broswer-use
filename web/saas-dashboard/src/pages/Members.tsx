import { useState } from 'react'
import { AlertTriangle, Mail, RefreshCw, Search, Trash2, UserPlus, X } from 'lucide-react'

import {
  type Invitation,
  type Member,
  useDeleteInvitation,
  useInvitations,
  useInviteMember,
  useMembers,
  useRemoveMember,
  useResendInvitation,
  useUpdateMemberRole,
} from '../api/members'
import { useAuth } from '../auth/AuthProvider'
import ConfirmModal, { ModalDialog } from '../components/ui/ConfirmModal'

const roleLabels: Record<Member['role'], string> = { owner: '所有者', admin: '管理员', member: '成员', viewer: '访客' }
const roleColors: Record<Member['role'], { bg: string; text: string }> = {
  owner: { bg: '#ede9fe', text: '#7c3aed' }, admin: { bg: '#dbeafe', text: '#1d4ed8' },
  member: { bg: '#f0fdf4', text: '#15803d' }, viewer: { bg: '#f3f4f6', text: '#4b5563' },
}
const editableRoles: Array<Exclude<Member['role'], 'owner'>> = ['admin', 'member', 'viewer']

const memberDateFormatter = new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium' })

function date(value?: string) {
  if (!value) return '—'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : memberDateFormatter.format(parsed)
}

interface InviteDrawerProps {
  canInviteAdmin: boolean
  loading: boolean
  onClose: () => void
  onInvite: (email: string, role: Invitation['role']) => Promise<void>
}

function InviteDrawer({ canInviteAdmin, loading, onClose, onInvite }: InviteDrawerProps) {
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<Invitation['role']>('member')
  const [error, setError] = useState('')
  const valid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)
  const availableRoles = editableRoles.filter((item) => canInviteAdmin || item !== 'admin')

  const submit = async () => {
    if (!valid) return setError('请输入有效的邮箱地址')
    try {
      await onInvite(email.trim(), role)
      onClose()
    } catch {
      // The mutation toast contains the server error and the drawer remains available for retry.
    }
  }

  return (
    <ModalDialog
      open
      onClose={onClose}
      labelledBy="invite-title"
      className="flex justify-end backdrop:bg-black/20"
      panelClassName="flex min-h-0 w-full flex-col overflow-hidden bg-white shadow-xl md:w-[400px] md:border-l"
      panelStyle={{ borderColor: 'var(--border)' }}
    >
      <div className="flex shrink-0 items-center justify-between border-b px-5 py-4" style={{ borderColor: 'var(--border)' }}>
        <h2 id="invite-title" className="font-semibold text-gray-900">邀请成员</h2>
        <button type="button" aria-label="关闭邀请面板" className="p-2 text-gray-400 hover:text-gray-600" onClick={onClose}><X size={18} /></button>
      </div>
      <div className="flex flex-1 flex-col gap-4 p-5">
        <label className="flex flex-col gap-1.5 text-sm font-medium text-gray-700">
          邮箱地址 <span className="sr-only">必填</span>
          <input type="email" value={email} placeholder="member@company.com" onChange={(event) => { setEmail(event.target.value); setError('') }} className="min-h-11 rounded-lg border px-3 py-2.5 text-sm font-normal focus:outline-none" style={{ borderColor: error ? '#ef4444' : 'var(--border)' }} />
          {error && <span role="alert" className="flex items-center gap-1 text-xs text-red-500"><AlertTriangle size={12} />{error}</span>}
        </label>
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1.5 text-sm font-medium text-gray-700">角色</legend>
          {availableRoles.map((item) => (
            <label key={item} className="flex cursor-pointer items-start gap-3 rounded-lg border p-3" style={{ borderColor: role === item ? 'var(--primary)' : 'var(--border)', background: role === item ? 'var(--accent)' : 'white' }}>
              <input type="radio" name="role" checked={role === item} onChange={() => setRole(item)} className="mt-0.5" />
              <span><span className="block text-sm font-medium text-gray-800">{roleLabels[item]}</span><span className="mt-0.5 block text-xs text-gray-400">{item === 'admin' ? '可管理工作区配置和成员' : item === 'member' ? '可查看和操作工作区内容' : '仅可查看工作区内容'}</span></span>
            </label>
          ))}
        </fieldset>
      </div>
      <div className="flex shrink-0 gap-2 border-t p-4" style={{ borderColor: 'var(--border)' }}>
        <button type="button" className="min-h-11 flex-1 rounded-lg border px-4 py-2.5 text-sm hover:bg-gray-50" style={{ borderColor: 'var(--border)' }} onClick={onClose} disabled={loading}>取消</button>
        <button type="button" className="flex min-h-11 flex-1 items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium text-white disabled:opacity-60" style={{ background: 'var(--primary)' }} disabled={!valid || loading} onClick={submit}>
          {loading ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" /> : <Mail size={14} />}发送邀请
        </button>
      </div>
    </ModalDialog>
  )
}

function RoleBadge({ role }: { role: Member['role'] }) {
  return <span className="rounded px-2 py-0.5 text-xs font-medium" style={{ background: roleColors[role].bg, color: roleColors[role].text }}>{roleLabels[role]}</span>
}

export default function Members() {
  const { role: currentRole, user } = useAuth()
  const membersQuery = useMembers()
  const invitationsQuery = useInvitations()
  const invite = useInviteMember()
  const updateRole = useUpdateMemberRole()
  const remove = useRemoveMember()
  const resend = useResendInvitation()
  const revoke = useDeleteInvitation()
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('all')
  const [inviteOpen, setInviteOpen] = useState(false)
  const [confirmRemove, setConfirmRemove] = useState<Member | null>(null)

  const canManage = currentRole === 'owner' || currentRole === 'admin'
  const members = membersQuery.data?.items || []
  const pendingInvites = (invitationsQuery.data?.items || []).filter((item) => item.status === 'pending')
  const filtered = members.filter((member) => {
    const term = search.trim().toLowerCase()
    return (!term || member.display_name.toLowerCase().includes(term) || member.email.toLowerCase().includes(term)) && (roleFilter === 'all' || member.role === roleFilter)
  })
  const canEdit = (member: Member) => canManage && member.user_id !== user?.id && member.role !== 'owner' && (currentRole === 'owner' || member.role !== 'admin')
  const optionsFor = (member: Member) => editableRoles.filter((item) => currentRole === 'owner' || (member.role !== 'admin' && item !== 'admin'))
  const loading = membersQuery.isLoading || invitationsQuery.isLoading
  const error = membersQuery.error || invitationsQuery.error

  if (loading) return <div className="flex min-h-64 items-center justify-center gap-2 p-6 text-sm text-gray-500"><span className="h-5 w-5 animate-spin rounded-full border-2 border-gray-200 border-t-gray-600" />正在加载成员…</div>
  if (error) return <div role="alert" className="m-4 rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-700 md:m-6"><p className="font-medium">无法加载成员数据</p><p className="mt-1 text-red-600">{error instanceof Error ? error.message : '请稍后重试'}</p><button type="button" className="mt-3 rounded-lg border border-red-300 px-3 py-2" onClick={() => { membersQuery.refetch(); invitationsQuery.refetch() }}>重试</button></div>

  return (
    <div className="flex min-h-full flex-col">
      <div className="flex flex-1 flex-col gap-4 p-4 md:p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div><h1 className="text-lg font-semibold text-gray-900 md:text-xl">成员管理</h1><p className="mt-0.5 hidden text-sm text-gray-500 md:block">管理工作区成员和权限</p></div>
          {canManage && <button type="button" className="flex min-h-11 items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium text-white hover:opacity-90" style={{ background: 'var(--primary)' }} onClick={() => setInviteOpen(true)}><UserPlus size={15} />邀请成员</button>}
        </div>

        {pendingInvites.length > 0 && <section aria-labelledby="pending-title" className="overflow-hidden rounded-xl border bg-white" style={{ borderColor: 'var(--border)' }}>
          <div className="border-b bg-amber-50 px-4 py-3" style={{ borderColor: '#fcd34d' }}><h2 id="pending-title" className="text-xs font-semibold text-amber-700">待接受邀请 ({pendingInvites.length})</h2></div>
          {pendingInvites.map((invitation) => <div key={invitation.id} className="flex flex-wrap items-center gap-3 border-b px-4 py-3 last:border-0" style={{ borderColor: 'var(--border)' }}>
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gray-200 text-xs font-semibold text-gray-500">?</div>
            <div className="min-w-48 flex-1"><div className="truncate text-sm font-medium text-gray-800">{invitation.email}</div><div className="text-xs text-gray-400">邀请于 {date(invitation.invited_at)} · 到期 {date(invitation.expires_at)}</div></div>
            <RoleBadge role={invitation.role} />
            {canManage && <div className="ml-auto flex gap-1"><button type="button" aria-label={`重发 ${invitation.email} 的邀请`} className="flex min-h-9 items-center gap-1 rounded-lg border px-2.5 text-xs hover:bg-gray-50 disabled:opacity-50" style={{ borderColor: 'var(--border)' }} disabled={resend.isPending || revoke.isPending} onClick={() => resend.mutate(invitation.id)}><RefreshCw size={13} />重发</button><button type="button" aria-label={`撤销 ${invitation.email} 的邀请`} className="flex min-h-9 items-center gap-1 rounded-lg border border-red-300 px-2.5 text-xs text-red-500 hover:bg-red-50 disabled:opacity-50" disabled={resend.isPending || revoke.isPending} onClick={() => revoke.mutate(invitation.id)}><Trash2 size={13} />撤销</button></div>}
          </div>)}
        </section>}

        <div className="flex flex-wrap items-center gap-2">
          <label className="relative min-w-0 flex-1 md:flex-none"><span className="sr-only">搜索成员</span><Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" /><input type="search" placeholder="搜索成员..." value={search} onChange={(event) => setSearch(event.target.value)} className="min-h-11 w-full rounded-lg border bg-white py-2 pl-8 pr-3 text-sm focus:outline-none" style={{ borderColor: 'var(--border)' }} /></label>
          <label><span className="sr-only">按角色筛选</span><select value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)} className="min-h-11 rounded-lg border bg-white px-3 py-2 text-sm focus:outline-none" style={{ borderColor: 'var(--border)' }}><option value="all">全部角色</option>{(['owner', ...editableRoles] as Member['role'][]).map((item) => <option key={item} value={item}>{roleLabels[item]}</option>)}</select></label>
        </div>

        {filtered.length === 0 ? <div className="rounded-xl border bg-white px-5 py-12 text-center" style={{ borderColor: 'var(--border)' }}><p className="text-sm font-medium text-gray-700">{members.length ? '没有匹配的成员' : '暂无成员'}</p><p className="mt-1 text-xs text-gray-400">{members.length ? '请调整搜索词或角色筛选' : '邀请成员加入当前工作区'}</p></div> : <>
          <div className="hidden overflow-hidden rounded-xl border bg-white md:block" style={{ borderColor: 'var(--border)' }}><table className="w-full text-sm"><thead><tr className="border-b bg-gray-50" style={{ borderColor: 'var(--border)' }}>{['成员', '邮箱', '角色', '状态', '加入时间', '最近活跃', '操作'].map((heading) => <th key={heading} className="px-4 py-3 text-left text-xs font-semibold text-gray-500">{heading}</th>)}</tr></thead><tbody>{filtered.map((member) => <tr key={member.id} className="border-b last:border-0 hover:bg-gray-50" style={{ borderColor: 'var(--border)' }}><td className="px-4 py-3"><div className="flex items-center gap-2.5"><div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white" style={{ background: 'var(--primary)' }}>{member.display_name.slice(0, 1).toUpperCase()}</div><span className="font-medium text-gray-800">{member.display_name}</span></div></td><td className="px-4 py-3 text-xs text-gray-500">{member.email}</td><td className="px-4 py-3"><RoleBadge role={member.role} /></td><td className="px-4 py-3"><span className={member.status === 'active' ? 'text-green-700' : 'text-gray-400'}>{member.status === 'active' ? '活跃' : '停用'}</span></td><td className="px-4 py-3 text-xs text-gray-400">{date(member.joined_at)}</td><td className="px-4 py-3 text-xs text-gray-400">{date(member.last_active_at)}</td><td className="px-4 py-3">{canEdit(member) ? <div className="flex items-center gap-2"><select aria-label={`更改 ${member.display_name} 的角色`} className="min-h-9 rounded-lg border bg-white px-2 text-xs" style={{ borderColor: 'var(--border)' }} value={member.role} disabled={updateRole.isPending} onChange={(event) => updateRole.mutate({ id: member.id, role: event.target.value as Exclude<Member['role'], 'owner'> })}>{optionsFor(member).map((item) => <option key={item} value={item}>{roleLabels[item]}</option>)}</select><button type="button" aria-label={`移除 ${member.display_name}`} className="min-h-9 rounded-lg px-2 text-xs text-red-500 hover:bg-red-50" onClick={() => setConfirmRemove(member)}>移除</button></div> : <span className="text-xs text-gray-300">—</span>}</td></tr>)}</tbody></table></div>
          <div className="flex flex-col gap-2 md:hidden">{filtered.map((member) => <article key={member.id} className="rounded-xl border bg-white p-4" style={{ borderColor: 'var(--border)' }}><div className="flex items-start justify-between gap-2"><div className="flex min-w-0 items-center gap-2.5"><div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-semibold text-white" style={{ background: 'var(--primary)' }}>{member.display_name.slice(0, 1).toUpperCase()}</div><div className="min-w-0"><div className="truncate font-medium text-gray-900">{member.display_name}</div><div className="truncate text-xs text-gray-400">{member.email}</div></div></div><RoleBadge role={member.role} /></div><div className="mt-3 flex items-center justify-between gap-2 border-t pt-3 text-xs text-gray-400" style={{ borderColor: 'var(--border)' }}><span>加入：{date(member.joined_at)}</span>{canEdit(member) && <div className="flex items-center gap-1"><select aria-label={`更改 ${member.display_name} 的角色`} value={member.role} disabled={updateRole.isPending} onChange={(event) => updateRole.mutate({ id: member.id, role: event.target.value as Exclude<Member['role'], 'owner'> })} className="min-h-10 rounded-lg border bg-white px-2 text-xs text-gray-700" style={{ borderColor: 'var(--border)' }}>{optionsFor(member).map((item) => <option key={item} value={item}>{roleLabels[item]}</option>)}</select><button type="button" aria-label={`移除 ${member.display_name}`} className="min-h-10 rounded-lg px-2 text-red-500 hover:bg-red-50" onClick={() => setConfirmRemove(member)}>移除</button></div>}</div></article>)}</div>
        </>}
      </div>

      {inviteOpen && <InviteDrawer canInviteAdmin={currentRole === 'owner'} loading={invite.isPending} onClose={() => setInviteOpen(false)} onInvite={(email, role) => invite.mutateAsync({ email, role }).then(() => undefined)} />}
      <ConfirmModal open={confirmRemove !== null} title="确认移除成员" description={`移除后，${confirmRemove?.display_name || '该成员'} 将立即失去工作区访问权限。`} confirmLabel="移除" destructive loading={remove.isPending} onConfirm={() => { if (confirmRemove) remove.mutate(confirmRemove.id, { onSuccess: () => setConfirmRemove(null) }) }} onCancel={() => setConfirmRemove(null)} />
    </div>
  )
}
