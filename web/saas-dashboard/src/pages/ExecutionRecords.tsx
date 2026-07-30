import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { AlertTriangle, CheckCircle, Clock, Download, ExternalLink, FileText, RefreshCw, Search, X } from 'lucide-react'

import { useExecution, useExecutionArtifacts, useExecutionKeywords, useExecutionLogs, useExecutions, type Execution, type ExecutionArtifact } from '../api/executions'
import StatusBadge from '../components/ui/StatusBadge'
import { isDemoData } from '../utils/provenance'
import { Button } from '../components/ui/button'
import { Skeleton } from '../components/ui/skeleton'

function formatDateTime(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function formatDuration(ms?: number | null) {
  if (!ms) return '—'
  const seconds = Math.round(ms / 1000)
  if (seconds < 60) return `${seconds}s`
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
}

function triggerLabel(value?: string) {
  if (value === 'manual') return '手动'
  if (value === 'scheduled') return '定时'
  return value || '—'
}

function reportArtifact(artifacts: ExecutionArtifact[]) {
  return artifacts.find((item) => item.name === 'execution_report.html')
    || artifacts.find((item) => item.name === 'job_report.html')
    || artifacts.find((item) => item.name.endsWith('.html'))
}

function openArtifact(item?: ExecutionArtifact) {
  if (!item) return
  window.open(item.url, '_blank', 'noopener,noreferrer')
}

function downloadArtifact(item?: ExecutionArtifact) {
  if (!item) return
  const separator = item.url.includes('?') ? '&' : '?'
  window.open(`${item.url}${separator}download=1`, '_blank', 'noopener,noreferrer')
}

function ExecutionDrawer({ execId, onClose }: { execId: string; onClose: () => void }) {
  const { data: exec, isLoading: detailLoading } = useExecution(execId)
  const isActive = exec?.status === 'queued' || exec?.status === 'running'
  const { data: keywords = [], refetch: refetchKeywords } = useExecutionKeywords(execId, isActive)
  const { data: artifacts, refetch: refetchArtifacts } = useExecutionArtifacts(execId, isActive)
  const { data: logs, refetch: refetchLogs } = useExecutionLogs(execId, 80, isActive)
  const previousStatus = useRef(exec?.status)

  useEffect(() => {
    const wasActive = previousStatus.current === 'queued' || previousStatus.current === 'running'
    if (wasActive && exec?.status && !isActive) {
      void Promise.all([refetchKeywords(), refetchArtifacts(), refetchLogs()])
    }
    previousStatus.current = exec?.status
  }, [exec?.status, isActive, refetchArtifacts, refetchKeywords, refetchLogs])
  const items = artifacts?.items || []
  const report = reportArtifact(items)
  const objectStorage = exec?.config_snapshot?.artifacts?.object_storage

  return (
    <div className="fixed inset-0 z-40 flex min-h-0 flex-col overflow-hidden border-l bg-white shadow-xl md:inset-y-0 md:left-auto md:right-0 md:w-[560px]" style={{ borderColor: 'var(--border)' }}>
      <div className="flex shrink-0 items-center justify-between border-b px-4 py-3" style={{ borderColor: 'var(--border)' }}>
        <div className="min-w-0">
          <div className="flex items-center gap-2"><h3 className="font-semibold text-gray-900">执行详情</h3>{isDemoData(exec) && <DemoBadge />}</div>
          <div className="mt-0.5 truncate font-mono text-xs text-gray-400">{execId}</div>
        </div>
        <button className="p-2 text-gray-400 hover:text-gray-600" onClick={onClose} style={{ minHeight: 44, minWidth: 44 }}>
          <X size={16} />
        </button>
      </div>

      {detailLoading || !exec ? (
        <div className="flex flex-1 flex-col gap-3 p-4">
          <Skeleton className="h-20 rounded-xl" />
          <Skeleton className="h-40 rounded-xl" />
          <Skeleton className="h-40 rounded-xl" />
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-4">
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: '扫描内容', value: exec.scanned_contents },
              { label: '扫描评论', value: exec.scanned_comments },
              { label: '候选线索', value: exec.lead_candidates },
            ].map((m) => (
              <div key={m.label} className="rounded-xl border bg-gray-50 p-3 text-center" style={{ borderColor: 'var(--border)' }}>
                <div className="text-xl font-bold text-gray-900">{m.value}</div>
                <div className="mt-0.5 text-[11px] text-gray-400">{m.label}</div>
              </div>
            ))}
          </div>

          <section className="mt-5 rounded-xl border bg-white p-4" style={{ borderColor: 'var(--border)' }}>
            <div className="mb-3 flex items-center justify-between gap-2">
              <div className="text-xs font-semibold uppercase tracking-wider text-gray-500">执行状态</div>
              <StatusBadge status={exec.status} variant="dot" />
            </div>
            <dl className="grid grid-cols-2 gap-3 text-sm">
              <Info label="活动 ID" value={exec.campaign_id} mono />
              <Info label="Run ID" value={exec.run_id || '—'} mono />
              <Info label="触发方式" value={triggerLabel(exec.trigger_type)} />
              <Info label="阶段" value={exec.stage || '—'} />
              <Info label="开始时间" value={formatDateTime(exec.started_at)} />
              <Info label="完成时间" value={formatDateTime(exec.finished_at)} />
              <Info label="耗时" value={formatDuration(exec.elapsed_ms)} />
              <Info label="Worker" value={exec.queue?.claimed_by || '—'} />
            </dl>
            {exec.error_type && (
              <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">
                <div className="mb-1 flex items-center gap-1.5 font-semibold"><AlertTriangle size={13} />执行异常</div>
                <div>{exec.error_type}: {exec.error_message || '—'}</div>
              </div>
            )}
          </section>

          <section className="mt-5 rounded-xl border bg-white p-4" style={{ borderColor: 'var(--border)' }}>
            <div className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">关键词执行</div>
            {keywords.length === 0 ? (
              <div className="text-sm text-gray-400">暂无关键词明细</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[520px] text-xs">
                  <thead>
                    <tr className="border-b bg-gray-50" style={{ borderColor: 'var(--border)' }}>
                      {['关键词', '状态', '内容', '评论', '候选', '耗时'].map((heading) => <th key={heading} className="px-3 py-2 text-left font-medium text-gray-500">{heading}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {keywords.map((item) => (
                      <tr key={item.id} className="border-b last:border-0" style={{ borderColor: 'var(--border)' }}>
                        <td className="px-3 py-2 font-medium">{item.keyword}</td>
                        <td className="px-3 py-2"><StatusBadge status={item.status} variant="dot" /></td>
                        <td className="px-3 py-2">{item.discovered_contents}</td>
                        <td className="px-3 py-2">{item.scanned_comments}</td>
                        <td className="px-3 py-2">{item.lead_candidates}</td>
                        <td className="px-3 py-2 font-mono text-gray-500">{formatDuration(item.elapsed_ms)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          <section className="mt-5 rounded-xl border bg-white p-4" style={{ borderColor: 'var(--border)' }}>
            <div className="mb-3 flex items-center justify-between gap-2">
              <div>
                <div className="text-xs font-semibold uppercase tracking-wider text-gray-500">报告和产物</div>
                <div className="mt-1 text-xs text-gray-400">
                  对象存储：{objectStorage?.enabled ? `已启用，上传 ${objectStorage.uploaded || 0} 个文件` : '未启用'}
                  {objectStorage?.error ? `，错误：${objectStorage.error}` : ''}
                </div>
              </div>
              <Button size="sm" variant="outline" disabled={!report} onClick={() => openArtifact(report)}>
                <ExternalLink className="h-3.5 w-3.5" /> 打开报告
              </Button>
            </div>
            {items.length === 0 ? (
              <div className="text-sm text-gray-400">暂无产物</div>
            ) : (
              <div className="grid grid-cols-1 gap-2">
                {items.map((item) => (
                  <div key={`${item.url}-${item.name}`} className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-xs" style={{ borderColor: 'var(--border)', minHeight: 44 }}>
                    <span className="flex min-w-0 items-center gap-2">
                      <FileText size={13} className="shrink-0 text-gray-400" />
                      <span className="truncate font-medium">{item.name}</span>
                    </span>
                    <span className="flex shrink-0 items-center gap-1">
                      <span className="mr-1 hidden text-gray-400 sm:inline">{item.external_url ? '已同步对象存储' : '本地产物'}</span>
                      <Button size="icon-sm" variant="ghost" title="预览" onClick={() => openArtifact(item)}>
                        <ExternalLink className="h-3.5 w-3.5" />
                      </Button>
                      <Button size="icon-sm" variant="ghost" title="下载" onClick={() => downloadArtifact(item)}>
                        <Download className="h-3.5 w-3.5" />
                      </Button>
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="mt-5 rounded-xl border bg-white p-4" style={{ borderColor: 'var(--border)' }}>
            <div className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">执行日志</div>
            {!logs?.items?.length ? (
              <div className="text-sm text-gray-400">暂无日志</div>
            ) : (
              <div className="max-h-64 overflow-auto rounded-lg bg-gray-950 p-3 font-mono text-[11px] leading-relaxed text-gray-100">
                {logs.items.map((item, index) => (
                  <div key={`${item.source || 'log'}-${index}`} className="whitespace-pre-wrap break-words">
                    <span className="text-gray-500">{String(item.line_number ?? index + 1).padStart(4, '0')} </span>{item.line}
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  )
}

function Info({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <dt className="text-xs text-gray-400">{label}</dt>
      <dd className={`mt-1 truncate text-xs text-gray-800 ${mono ? 'font-mono' : ''}`}>{value}</dd>
    </div>
  )
}

export default function ExecutionRecords() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('')
  const openDrawer = searchParams.get('execution_id')
  const setOpenDrawer = (executionId: string | null) => {
    const next = new URLSearchParams(searchParams)
    if (executionId) next.set('execution_id', executionId)
    else next.delete('execution_id')
    setSearchParams(next, { replace: true })
  }
  const { data, isLoading, error, refetch, isFetching } = useExecutions({ status: status || undefined, limit: 50, offset: 0 })
  const executions = data?.items || []

  const filtered = useMemo(() => executions.filter((item) => {
    if (!search) return true
    const text = `${item.id} ${item.campaign_id} ${item.run_id || ''} ${item.current_keyword || ''}`.toLowerCase()
    return text.includes(search.toLowerCase())
  }), [executions, search])

  return (
    <div className="flex min-h-full flex-col">
      <div className="flex flex-1 flex-col gap-4 p-4 md:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold text-gray-900">执行记录</h1>
            <p className="mt-0.5 hidden text-sm text-gray-500 md:block">查看后端 worker 的真实扫描、候选生成和报告产物</p>
          </div>
          <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} /> 刷新
          </Button>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-0 flex-1" style={{ maxWidth: 280 }}>
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="搜索执行 ID / 关键词..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="w-full rounded-lg border bg-white py-2.5 pl-8 pr-3 text-sm focus:outline-none"
              style={{ borderColor: 'var(--border)', minHeight: 44 }}
            />
          </div>
          <select value={status} onChange={(event) => setStatus(event.target.value)} className="rounded-lg border bg-white px-3 py-2.5 text-sm focus:outline-none" style={{ borderColor: 'var(--border)', minHeight: 44 }}>
            <option value="">全部状态</option>
            <option value="running">执行中</option>
            <option value="completed">已完成</option>
            <option value="partial">部分完成</option>
            <option value="failed">失败</option>
            <option value="cancelled">已取消</option>
          </select>
          <span className="ml-auto shrink-0 text-xs text-gray-400">{filtered.length} 条记录</span>
        </div>

        {error && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">执行记录加载失败，请刷新重试</div>}

        <div className="hidden overflow-hidden rounded-xl border bg-white md:block" style={{ borderColor: 'var(--border)' }}>
          {isLoading ? (
            <div className="p-4"><Skeleton className="h-48 rounded-xl" /></div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[980px] text-sm">
                <thead>
                  <tr className="border-b bg-gray-50" style={{ borderColor: 'var(--border)' }}>
                    {['执行 ID', '活动', '触发', '状态', '阶段', '关键词', '内容', '评论', '候选', '耗时', '开始时间', '报告'].map((heading) => (
                      <th key={heading} className="px-3 py-3 text-left text-xs font-semibold text-gray-500">{heading}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((item) => (
                    <tr key={item.id} className="cursor-pointer border-b last:border-0 hover:bg-gray-50" style={{ borderColor: 'var(--border)' }} onClick={() => setOpenDrawer(item.id)}>
                      <td className="px-3 py-3 font-mono text-xs text-gray-600"><span className="flex items-center gap-1.5">{item.id}{isDemoData(item) && <DemoBadge />}</span></td>
                      <td className="px-3 py-3 text-xs text-gray-500">{item.campaign_id}</td>
                      <td className="px-3 py-3 text-xs text-gray-500">{triggerLabel(item.trigger_type)}</td>
                      <td className="px-3 py-3"><StatusBadge status={item.status} variant="dot" /></td>
                      <td className="px-3 py-3 text-xs text-gray-400">{item.stage || '—'}</td>
                      <td className="px-3 py-3 text-center text-xs text-gray-600">{item.total_keywords}</td>
                      <td className="px-3 py-3 text-center text-xs text-gray-600">{item.scanned_contents}</td>
                      <td className="px-3 py-3 text-center text-xs text-gray-600">{item.scanned_comments}</td>
                      <td className="px-3 py-3 text-center text-xs font-medium text-gray-800">{item.lead_candidates}</td>
                      <td className="px-3 py-3 font-mono text-xs text-gray-500">{formatDuration(item.elapsed_ms)}</td>
                      <td className="px-3 py-3 text-xs text-gray-400">{formatDateTime(item.started_at || item.created_at)}</td>
                      <td className="px-3 py-3">
                        {item.config_snapshot?.artifacts ? (
                          <span className="inline-flex items-center gap-1 text-xs text-emerald-700"><CheckCircle size={12} /> 已生成</span>
                        ) : item.status === 'completed' || item.status === 'partial' ? (
                          <span className="inline-flex items-center gap-1 text-xs text-amber-600"><Clock size={12} /> 生成中</span>
                        ) : (
                          <span className="text-xs text-gray-300">—</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {filtered.length === 0 && <div className="p-8 text-center text-sm text-gray-400">暂无执行记录</div>}
            </div>
          )}
        </div>

        <div className="flex flex-col gap-3 md:hidden">
          {filtered.map((item) => (
            <button key={item.id} className="rounded-xl border bg-white p-4 text-left active:bg-gray-50" style={{ borderColor: item.status === 'failed' ? '#fca5a5' : 'var(--border)' }} onClick={() => setOpenDrawer(item.id)}>
              <div className="mb-2 flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5"><div className="truncate font-mono text-xs text-gray-800">{item.id}</div>{isDemoData(item) && <DemoBadge />}</div>
                  <div className="mt-0.5 text-xs text-gray-400">{triggerLabel(item.trigger_type)} · {formatDateTime(item.started_at || item.created_at)}</div>
                </div>
                <StatusBadge status={item.status} variant="dot" />
              </div>
              <div className="grid grid-cols-3 gap-2">
                <Metric label="评论" value={item.scanned_comments} />
                <Metric label="候选" value={item.lead_candidates} />
                <Metric label="耗时" value={formatDuration(item.elapsed_ms)} />
              </div>
              {item.error_type && <div className="mt-2 flex items-center gap-1 text-xs text-red-500"><AlertTriangle size={11} /> {item.error_type}</div>}
            </button>
          ))}
        </div>
      </div>

      {openDrawer && (
        <>
          <div className="fixed inset-0 z-30 bg-black/20" onClick={() => setOpenDrawer(null)} />
          <ExecutionDrawer execId={openDrawer} onClose={() => setOpenDrawer(null)} />
        </>
      )}
    </div>
  )
}

function DemoBadge() {
  return <span className="shrink-0 rounded border border-sky-200 bg-sky-50 px-1.5 py-0.5 font-sans text-[10px] font-medium text-sky-700">演示样本</span>
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="text-center">
      <div className="text-sm font-semibold text-gray-800">{value}</div>
      <div className="text-[11px] text-gray-400">{label}</div>
    </div>
  )
}
