import { useMemo, useState } from 'react'
import { Filter, MessageSquareOff, Search, X } from 'lucide-react'

import { useReplyRecord, useReplyRecords, type ReplyRecord } from '../api/reply-records'
import StatusBadge from '../components/ui/StatusBadge'

function formatDate(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function statusLabel(status?: string) {
  const labels: Record<string, string> = {
    sent: '已发送',
    failed: '失败',
    pending: '待处理',
    blocked: '已阻断',
    verified: '已验证',
    cancelled: '已取消',
  }
  return status ? labels[status] || status : '—'
}

function rowText(record: ReplyRecord) {
  return `${record.id} ${record.campaign_id} ${record.reply_candidate_id || ''} ${record.comment_id || ''} ${record.reply_text} ${record.status} ${record.error_message || ''}`.toLowerCase()
}

export default function ReplyRecords() {
  const [search, setSearch] = useState('')
  const [filterOpen, setFilterOpen] = useState(false)
  const [detailId, setDetailId] = useState<string | null>(null)
  const { data, isLoading, error } = useReplyRecords({ limit: 100, offset: 0 })
  const { data: detailData, isLoading: detailLoading } = useReplyRecord(detailId)
  const records = data?.items || []
  const filtered = useMemo(() => records.filter((record) => !search || rowText(record).includes(search.toLowerCase())), [records, search])
  const detail = detailData?.record || records.find((record) => record.id === detailId)

  return (
    <div className="flex min-h-full flex-col">
      <div className="flex flex-1 flex-col gap-4 p-4 md:p-6">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-gray-900">回复记录</h1>
          <p className="mt-0.5 hidden text-sm text-gray-500 md:block">查看真实回复发送、阻断、失败和验证结果</p>
        </div>

        <div className="flex items-start gap-3 rounded-xl border p-4" style={{ background: '#f0fdf4', borderColor: '#bbf7d0' }}>
          <MessageSquareOff size={16} className="mt-0.5 shrink-0 text-green-600" />
          <div className="text-sm leading-relaxed text-green-700">
            当前列表读取后端回复记录表。系统发送关闭时，执行计划会产生阻断记录；没有记录时说明还没有执行过发送/阻断阶段。
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-0 flex-1" style={{ maxWidth: 280 }}>
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="搜索记录、活动或错误..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="w-full rounded-lg border bg-white py-2.5 pl-8 pr-3 text-sm focus:outline-none"
              style={{ borderColor: 'var(--border)', minHeight: 44 }}
            />
          </div>
          <button
            className="flex items-center gap-1.5 rounded-lg border px-3 py-2.5 text-sm hover:bg-gray-50 md:hidden"
            style={{ borderColor: 'var(--border)', minHeight: 44 }}
            onClick={() => setFilterOpen(true)}
          >
            <Filter size={13} /> 筛选
          </button>
          <span className="ml-auto text-xs text-gray-400">{filtered.length} 条记录</span>
        </div>

        {error && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">回复记录加载失败，请刷新重试</div>}

        <div className="hidden overflow-hidden rounded-xl border bg-white md:block" style={{ borderColor: 'var(--border)' }}>
          {isLoading ? (
            <div className="p-4 text-sm text-gray-500">正在加载回复记录...</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[900px] text-sm">
                <thead>
                  <tr className="border-b bg-gray-50" style={{ borderColor: 'var(--border)' }}>
                    {['记录 ID', '活动 ID', '候选 ID', '回复文本', '状态', '验证', '错误', '创建时间'].map((header) => (
                      <th key={header} className="px-4 py-3 text-left text-xs font-semibold text-gray-500">{header}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((record) => (
                    <tr key={record.id} className="cursor-pointer border-b last:border-0 hover:bg-gray-50" style={{ borderColor: 'var(--border)' }} onClick={() => setDetailId(record.id)}>
                      <td className="px-4 py-3 font-mono text-xs text-gray-500">{record.id}</td>
                      <td className="px-4 py-3 font-mono text-xs text-gray-500">{record.campaign_id}</td>
                      <td className="px-4 py-3 font-mono text-xs text-gray-500">{record.reply_candidate_id || '—'}</td>
                      <td className="max-w-[220px] truncate px-4 py-3 text-gray-700">{record.reply_text || '—'}</td>
                      <td className="px-4 py-3"><StatusBadge status={statusLabel(record.status)} /></td>
                      <td className="px-4 py-3 text-xs text-gray-600">{record.verified ? '是' : '否'}</td>
                      <td className="max-w-[160px] truncate px-4 py-3 text-xs text-gray-500">{record.error_message || record.error_type || '—'}</td>
                      <td className="px-4 py-3 text-xs text-gray-400">{formatDate(record.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {filtered.length === 0 && <div className="p-8 text-center text-sm text-gray-400">暂无回复记录</div>}
            </div>
          )}
        </div>

        <div className="flex flex-col gap-3 md:hidden">
          {filtered.map((record) => (
            <button key={record.id} className="rounded-xl border bg-white p-4 text-left active:bg-gray-50" style={{ borderColor: 'var(--border)' }} onClick={() => setDetailId(record.id)}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate font-mono text-xs text-gray-500">{record.id}</div>
                  <div className="mt-1 line-clamp-2 text-sm text-gray-800">{record.reply_text || '—'}</div>
                </div>
                <StatusBadge status={statusLabel(record.status)} />
              </div>
              <div className="mt-2 text-xs text-gray-400">{record.campaign_id} · {formatDate(record.created_at)}</div>
            </button>
          ))}
        </div>
      </div>

      {detailId && (
        <>
          <div className="fixed inset-0 z-30 bg-black/20" onClick={() => setDetailId(null)} />
          <div className="fixed inset-0 z-40 flex min-h-0 flex-col overflow-hidden bg-white shadow-xl md:inset-y-0 md:left-auto md:right-0 md:w-[480px] md:border-l" style={{ borderColor: 'var(--border)' }}>
            <div className="flex shrink-0 items-center justify-between border-b px-4 py-3" style={{ borderColor: 'var(--border)' }}>
              <div>
                <h3 className="font-semibold text-gray-900">回复记录详情</h3>
                <div className="mt-0.5 font-mono text-xs text-gray-400">{detailId}</div>
              </div>
              <button className="p-2 text-gray-400 hover:text-gray-600" onClick={() => setDetailId(null)} style={{ minHeight: 44, minWidth: 44 }}><X size={16} /></button>
            </div>
            <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
              {detailLoading && <div className="text-sm text-gray-500">正在加载详情...</div>}
              {detail && (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge status={statusLabel(detail.status)} />
                    <span className="text-xs text-gray-400">{detailData?.campaign?.name || detail.campaign_id}</span>
                  </div>
                  <InfoGrid items={[
                    ['候选 ID', detail.reply_candidate_id || '—'],
                    ['计划 ID', detail.reply_plan_id || '—'],
                    ['账号 ID', detail.platform_account_id || '—'],
                    ['评论 ID', detail.comment_id || '—'],
                    ['验证结果', detail.verified ? '已验证' : '未验证'],
                    ['创建时间', formatDate(detail.created_at)],
                  ]} />
                  <TextBlock title="原始评论" value={detailData?.original_comment?.text || detailData?.candidate?.comment_text || '—'} />
                  <TextBlock title="回复文本" value={detail.reply_text || detailData?.candidate?.rendered_reply_text || '—'} highlight />
                  {(detail.error_type || detail.error_message) && (
                    <div className="rounded-xl border border-red-100 bg-red-50 p-3 text-sm text-red-700">
                      <div className="font-semibold">{detail.error_type || '错误'}</div>
                      <div className="mt-1 break-words">{detail.error_message || '—'}</div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </>
      )}

      {filterOpen && (
        <>
          <div className="fixed inset-0 z-30 bg-black/30" onClick={() => setFilterOpen(false)} />
          <div className="fixed inset-x-0 bottom-0 z-40 flex flex-col gap-4 rounded-t-2xl bg-white p-5" style={{ paddingBottom: 'max(20px, env(safe-area-inset-bottom))' }}>
            <div className="flex items-center justify-between">
              <span className="font-semibold text-gray-900">筛选</span>
              <button className="p-2 text-gray-400" onClick={() => setFilterOpen(false)} style={{ minHeight: 44, minWidth: 44 }}><X size={16} /></button>
            </div>
            <div className="text-sm text-gray-500">当前移动端先支持搜索过滤；状态和日期过滤会继续接入后端查询参数。</div>
            <button className="w-full rounded-xl py-3 text-sm font-medium text-white" style={{ background: 'var(--primary)', minHeight: 44 }} onClick={() => setFilterOpen(false)}>
              确定
            </button>
          </div>
        </>
      )}
    </div>
  )
}

function InfoGrid({ items }: { items: Array<[string, string]> }) {
  return (
    <div className="grid grid-cols-2 gap-3">
      {items.map(([label, value]) => (
        <div key={label} className="min-w-0 rounded-xl border bg-gray-50 p-3" style={{ borderColor: 'var(--border)' }}>
          <div className="text-xs text-gray-400">{label}</div>
          <div className="mt-1 truncate text-xs font-medium text-gray-800">{value}</div>
        </div>
      ))}
    </div>
  )
}

function TextBlock({ title, value, highlight = false }: { title: string; value: string; highlight?: boolean }) {
  return (
    <div>
      <div className="mb-1.5 text-xs font-semibold text-gray-500">{title}</div>
      <div className={`rounded-xl border p-3 text-sm leading-relaxed text-gray-700 ${highlight ? 'border-indigo-100 bg-indigo-50' : 'bg-gray-50'}`} style={highlight ? undefined : { borderColor: 'var(--border)' }}>
        {value}
      </div>
    </div>
  )
}
