import { lazy, Suspense, useMemo } from 'react'
import { Calendar, Download, TrendingUp, Zap } from 'lucide-react'

import { useSettings } from '../api/settings'
import { useTokenUsageDetails, useTokenUsageSummary } from '../api/token-usage'
import { formatUsageDate, usageDayKey } from '../utils/token-usage'

const DailyTokenChart = lazy(() => import('../components/charts/TokenUsageCharts').then((module) => ({ default: module.DailyTokenChart })))
const CampaignTokenChart = lazy(() => import('../components/charts/TokenUsageCharts').then((module) => ({ default: module.CampaignTokenChart })))

export default function TokenUsage() {
  const { data: summary, isLoading: summaryLoading, error: summaryError } = useTokenUsageSummary()
  const { data: settings } = useSettings()
  const timezone = settings?.timezone || 'UTC'
  const { data: detailsPage, isLoading: detailsLoading, error: detailsError } = useTokenUsageDetails({ limit: 200, offset: 0 })
  const details = useMemo(() => detailsPage?.items || [], [detailsPage?.items])
  const dailyData = useMemo(() => {
    const map = new Map<string, { day: string; input: number; output: number; total: number }>()
    for (const item of details) {
      const key = usageDayKey(item.created_at, timezone)
      const row = map.get(key) || { day: key.slice(5).replace('-', '/'), input: 0, output: 0, total: 0 }
      row.input += item.prompt_tokens ?? 0
      row.output += item.completion_tokens ?? 0
      row.total += item.tokens_used ?? 0
      map.set(key, row)
    }
    return Array.from(map.values()).slice(-14)
  }, [details, timezone])
  const byCampaign = useMemo(() => {
    const map = new Map<string, number>()
    for (const item of details) map.set(item.campaign_id || '未关联活动', (map.get(item.campaign_id || '未关联活动') || 0) + (item.tokens_used ?? 0))
    return Array.from(map.entries()).map(([campaign, tokens]) => ({ campaign, tokens })).sort((a, b) => b.tokens - a.tokens).slice(0, 8)
  }, [details])

  return (
    <div className="flex min-h-full flex-col">
      <div className="flex flex-1 flex-col gap-5 p-4 md:p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div><h1 className="text-lg font-semibold text-gray-900 md:text-xl">Token 用量</h1><p className="mt-0.5 hidden text-sm text-gray-500 md:block">真实 LLM 调用量统计，仅在启用 AI 功能时产生</p></div>
          <button type="button" className="flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm hover:bg-gray-50" style={{ borderColor: 'var(--border)', minHeight: 44 }} onClick={() => window.print()}><Download size={14} />导出</button>
        </div>
        {(summaryError || detailsError) && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">Token 用量加载失败，请刷新重试</div>}
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[
            { label: '今日 Token', value: summaryLoading ? '...' : (summary?.tokens_used_today || 0).toLocaleString(), icon: <Zap size={14} />, sub: '后端实时统计' },
            { label: '本月累计', value: summaryLoading ? '...' : (summary?.tokens_used_this_month || 0).toLocaleString(), icon: <Calendar size={14} />, sub: '自然月累计' },
            { label: '最近 7 天', value: summaryLoading ? '...' : (summary?.total_tokens_used || 0).toLocaleString(), icon: <TrendingUp size={14} />, sub: '最近窗口累计' },
            { label: '调用次数', value: details.reduce((total, item) => total + item.request_count, 0).toLocaleString(), icon: <Zap size={14} />, sub: '请求次数合计' },
          ].map((m) => <div key={m.label} className="rounded-xl border bg-white p-4" style={{ borderColor: 'var(--border)' }}><div className="mb-2 flex items-center justify-between"><div className="text-xs text-gray-500">{m.label}</div><div className="rounded-lg p-1.5" style={{ background: 'var(--accent)', color: 'var(--primary)' }}>{m.icon}</div></div><div className="text-xl font-bold text-gray-900">{m.value}</div><div className="mt-0.5 text-[11px] text-gray-400">{m.sub}</div></div>)}
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="rounded-xl border bg-white p-4" style={{ borderColor: 'var(--border)' }}>
            <div className="mb-1 text-sm font-semibold text-gray-800">每日 Token 趋势</div><div className="mb-3 text-xs text-gray-400">按调用明细聚合</div>
            {dailyData.length ? <Suspense fallback={<ChartLoadingSkeleton />}><DailyTokenChart data={dailyData} /></Suspense> : <EmptyChart />}
          </div>
          <div className="rounded-xl border bg-white p-4" style={{ borderColor: 'var(--border)' }}>
            <div className="mb-1 text-sm font-semibold text-gray-800">活动 Token 消耗</div><div className="mb-3 text-xs text-gray-400">按 campaign_id 聚合</div>
            {byCampaign.length ? <Suspense fallback={<ChartLoadingSkeleton />}><CampaignTokenChart data={byCampaign} /></Suspense> : <EmptyChart />}
          </div>
        </div>
        <div className="overflow-hidden rounded-xl border bg-white" style={{ borderColor: 'var(--border)' }}>
          <div className="border-b px-4 py-3 text-sm font-semibold text-gray-800" style={{ borderColor: 'var(--border)' }}>调用明细</div>
          {detailsLoading ? <div className="p-4 text-sm text-gray-500">正在加载明细...</div> : <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-sm"><thead><tr className="border-b bg-gray-50" style={{ borderColor: 'var(--border)' }}>{['时间', '活动', '执行', '模型', '调用次数', '输入 Token', '输出 Token', '合计', '费用'].map((h) => <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-gray-500">{h}</th>)}</tr></thead><tbody>{details.map((d) => <tr key={d.id} className="border-b last:border-0 hover:bg-gray-50" style={{ borderColor: 'var(--border)' }}><td className="px-4 py-3 text-xs text-gray-500">{formatUsageDate(d.created_at, timezone)}</td><td className="px-4 py-3 font-mono text-xs text-gray-500">{d.campaign_id || '—'}</td><td className="px-4 py-3 font-mono text-xs text-gray-500">{d.execution_id || '—'}</td><td className="px-4 py-3 font-mono text-xs text-gray-500">{d.model}</td><td className="px-4 py-3 text-right text-xs text-gray-600">{d.request_count.toLocaleString()}</td><td className="px-4 py-3 text-right text-xs text-gray-600">{d.prompt_tokens?.toLocaleString() ?? '—'}</td><td className="px-4 py-3 text-right text-xs text-gray-600">{d.completion_tokens?.toLocaleString() ?? '—'}</td><td className="px-4 py-3 text-right text-xs font-medium text-gray-800">{d.tokens_used?.toLocaleString() ?? '—'}</td><td className="px-4 py-3 text-right text-xs text-gray-500">{d.cost == null ? '—' : `$${d.cost.toFixed(4)}`}</td></tr>)}</tbody></table>{details.length === 0 && <div className="p-8 text-center text-sm text-gray-400">暂无 Token 调用记录</div>}</div>}
        </div>
      </div>
    </div>
  )
}

function ChartLoadingSkeleton() {
  return <div data-testid="chart-loading-skeleton" className="h-[180px] w-full animate-pulse rounded-lg bg-gray-100" />
}

function EmptyChart() {
  return <div className="flex h-[180px] items-center justify-center text-sm text-gray-400">暂无数据</div>
}
