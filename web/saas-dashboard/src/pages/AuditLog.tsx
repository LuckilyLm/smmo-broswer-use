import { useState } from 'react'
import { Search, X } from 'lucide-react'

import { useAuditLogs, type AuditLog as AuditLogItem } from '../api/audit-logs'
import StatusBadge from '../components/ui/StatusBadge'

function formatDate(value?: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function logTime(log: AuditLogItem) {
  return log.timestamp || log.created_at
}

function logDetails(log: AuditLogItem) {
  return log.details || log.metadata_json || {}
}

function resultLabel(value?: string) {
  return value === 'success' ? '成功' : value === 'failure' ? '失败' : value || '—'
}

function DetailDrawer({ log, onClose }: { log: AuditLogItem; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex min-h-0 flex-col overflow-hidden bg-white shadow-xl md:inset-y-0 md:left-auto md:right-0 md:w-[480px] md:border-l" style={{ borderColor: 'var(--border)' }}>
      <div className="flex shrink-0 items-center justify-between border-b px-5 py-4" style={{ borderColor: 'var(--border)' }}>
        <div><h3 className="font-semibold text-gray-900">审计详情</h3><div className="mt-0.5 font-mono text-xs text-gray-400">{log.id}</div></div>
        <button className="p-2 text-gray-400 hover:text-gray-600" onClick={onClose} style={{ minHeight: 44, minWidth: 44 }}><X size={16} /></button>
      </div>
      <div className="flex-1 overflow-y-auto p-5">
        <div className="grid grid-cols-2 gap-3 text-sm">
          <Info label="时间" value={formatDate(logTime(log))} />
          <Info label="结果" value={resultLabel(log.result)} />
          <Info label="用户" value={log.user_display_name || log.user_email || log.user_id || '—'} />
          <Info label="操作" value={log.action} />
          <Info label="资源类型" value={log.resource_type || '—'} />
          <Info label="资源 ID" value={log.resource_id || '—'} mono />
          <Info label="IP" value={log.ip_address || '—'} />
          <Info label="User Agent" value={log.user_agent || '—'} />
        </div>
        <div className="mt-5">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">详细数据</div>
          <pre className="max-h-96 overflow-auto rounded-xl bg-gray-950 p-3 text-xs leading-relaxed text-gray-100">{JSON.stringify(logDetails(log), null, 2)}</pre>
        </div>
      </div>
    </div>
  )
}

export default function AuditLog() {
  const [search, setSearch] = useState('')
  const [selectedLog, setSelectedLog] = useState<AuditLogItem | null>(null)
  const { data, isLoading, error } = useAuditLogs({ limit: 100, offset: 0 })
  const logs = data?.items || []
  const filtered = logs.filter((log) => {
    if (!search) return true
    const text = `${log.id} ${log.user_display_name} ${log.user_email} ${log.user_id} ${log.action} ${log.resource_type} ${log.resource_id}`.toLowerCase()
    return text.includes(search.toLowerCase())
  })

  return (
    <div className="flex min-h-full flex-col">
      <div className="flex flex-1 flex-col gap-4 p-4 md:p-6">
        <div><h1 className="text-xl font-semibold text-gray-900">审计日志</h1><p className="mt-0.5 hidden text-sm text-gray-500 md:block">查看真实系统操作记录</p></div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-0 flex-1" style={{ maxWidth: 320 }}>
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="搜索用户、操作或资源..." className="w-full rounded-lg border bg-white py-2.5 pl-8 pr-3 text-sm focus:outline-none" style={{ borderColor: 'var(--border)', minHeight: 44 }} />
          </div>
          <span className="ml-auto text-xs text-gray-400">{filtered.length} 条日志</span>
        </div>
        {error && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">审计日志加载失败，请刷新重试</div>}
        <div className="hidden overflow-hidden rounded-xl border bg-white md:block" style={{ borderColor: 'var(--border)' }}>
          {isLoading ? <div className="p-4 text-sm text-gray-500">正在加载审计日志...</div> : <div className="overflow-x-auto"><table className="w-full min-w-[820px] text-sm"><thead><tr className="border-b bg-gray-50" style={{ borderColor: 'var(--border)' }}>{['时间', '用户', '操作', '资源', '结果', 'IP', ''].map((h) => <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500">{h}</th>)}</tr></thead><tbody>{filtered.map((log) => <tr key={log.id} className="cursor-pointer border-b last:border-0 hover:bg-gray-50" style={{ borderColor: 'var(--border)' }} onClick={() => setSelectedLog(log)}><td className="px-4 py-3 text-xs text-gray-500">{formatDate(logTime(log))}</td><td className="px-4 py-3 text-xs text-gray-700">{log.user_display_name || log.user_email || log.user_id || '—'}</td><td className="px-4 py-3 font-medium text-gray-800">{log.action}</td><td className="px-4 py-3 font-mono text-xs text-gray-500">{log.resource_type || '—'} / {log.resource_id || '—'}</td><td className="px-4 py-3"><StatusBadge status={resultLabel(log.result)} /></td><td className="px-4 py-3 text-xs text-gray-400">{log.ip_address || '—'}</td><td className="px-4 py-3 text-xs text-indigo-600">查看</td></tr>)}</tbody></table>{filtered.length === 0 && <div className="p-8 text-center text-sm text-gray-400">暂无审计日志</div>}</div>}
        </div>
        <div className="flex flex-col gap-2 md:hidden">{filtered.map((log) => <button key={log.id} className="rounded-xl border bg-white p-4 text-left" style={{ borderColor: 'var(--border)' }} onClick={() => setSelectedLog(log)}><div className="flex justify-between gap-2"><div className="font-medium text-gray-900">{log.action}</div><StatusBadge status={resultLabel(log.result)} /></div><div className="mt-1 text-xs text-gray-400">{formatDate(logTime(log))} · {log.user_display_name || log.user_email || log.user_id || '—'}</div></button>)}</div>
      </div>
      {selectedLog && <><div className="fixed inset-0 z-40 bg-black/20" onClick={() => setSelectedLog(null)} /><DetailDrawer log={selectedLog} onClose={() => setSelectedLog(null)} /></>}
    </div>
  )
}

function Info({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div className="min-w-0"><div className="text-xs text-gray-400">{label}</div><div className={`mt-1 truncate text-sm text-gray-800 ${mono ? 'font-mono text-xs' : ''}`}>{value || '—'}</div></div>
}
