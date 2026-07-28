import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'
import { Megaphone, Users, MessageSquare, UserPlus, Star, CheckCircle, Reply, XCircle, ChevronRight, RefreshCw } from 'lucide-react'
import { useDashboardSummary, type DashboardRange } from '../api/dashboard'
import PageContainer from '../components/layout/PageContainer'
import MetricCard from '../components/ui/MetricCard'
import SafetyAlert from '../components/ui/SafetyAlert'
import StatusBadge from '../components/ui/StatusBadge'
import { EmptyState, ErrorState } from '../components/ui/PageState'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { formatCampaignStatus, formatExecutionStatus, formatLoginStatus } from '../utils/formatters'

const platformColors: Record<string, string> = {
  facebook: '#1877f2', instagram: '#e1306c', tiktok: '#010101', x: '#1da1f2', youtube: '#ff0000', twitter: '#1da1f2',
}

const platformLabels: Record<string, string> = {
  facebook: 'Facebook', instagram: 'Instagram', tiktok: 'TikTok', x: 'X', youtube: 'YouTube', twitter: 'X', unknown: '未知平台',
}

export default function Dashboard() {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [range, setRange] = useState<DashboardRange>('7d')
  const { data: metrics, isLoading, error, refetch, isFetching } = useDashboardSummary(range)

  if (isLoading && !metrics) return <DashboardSkeleton />
  if (error && !metrics) {
    return <ErrorState description="无法加载仪表盘真实数据，请检查网络后重试。" onRetry={() => refetch()} />
  }
  if (!metrics) return null

  return (
    <PageContainer maxWidth="dashboard" className="flex min-h-full flex-col gap-4 md:gap-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">仪表盘</h1>
          <p className="mt-1 text-sm text-muted-foreground">查看社媒获客、任务执行和回复审批的真实状态</p>
        </div>
        <div className="flex items-center gap-2">
          {isFetching && <span className="hidden text-xs text-muted-foreground sm:inline">正在刷新…</span>}
          <select className="h-10 rounded-lg border bg-card px-3 text-sm outline-none" value={range} onChange={(event) => setRange(event.target.value as DashboardRange)}>
            <option value="7d">最近 7 天</option>
            <option value="14d">最近 14 天</option>
            <option value="30d">最近 30 天</option>
          </select>
          <Button variant="outline" size="icon-lg" onClick={() => refetch()} aria-label="刷新仪表盘"><RefreshCw className={`h-4 w-4 ${isFetching ? 'animate-spin' : ''}`} /></Button>
        </div>
      </div>

      {!metrics.system_send_enabled && <SafetyAlert onViewSettings={() => navigate('/settings')} />}

      <div className="grid grid-cols-2 gap-2 md:grid-cols-4 md:gap-3 2xl:grid-cols-8">
        <MetricCard label="活跃营销活动" value={metrics.active_campaigns} icon={<Megaphone size={14} />} />
        <MetricCard label="已连接平台账号" value={metrics.connected_accounts} icon={<Users size={14} />} />
        <MetricCard label="今日扫描评论" value={metrics.comments_scanned_today} icon={<MessageSquare size={14} />} />
        <MetricCard label="今日新增线索" value={metrics.leads_today} icon={<UserPlus size={14} />} accent="success" />
        <MetricCard label="高意向线索" value={metrics.high_intent_leads} icon={<Star size={14} />} accent="warning" />
        <MetricCard label="待审批回复" value={metrics.pending_replies} icon={<CheckCircle size={14} />} accent="warning" />
        <MetricCard label="今日已回复" value={metrics.today_replied} icon={<Reply size={14} />} tooltip={!metrics.system_send_enabled ? '系统回复发送开关当前关闭' : undefined} />
        <MetricCard label="今日失败任务" value={metrics.failed_tasks_today} icon={<XCircle size={14} />} accent="danger" />
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <section className="rounded-xl border bg-card p-4 md:col-span-2">
          <SectionTitle title="线索趋势" subtitle={`最近 ${range.replace('d', '')} 天`} />
          {metrics.lead_trend.length === 0 ? <EmptyState compact title="暂无趋势数据" description="产生线索或扫描记录后会显示趋势。" /> : (
            <ResponsiveContainer width="100%" height={180}>
              <LineChart data={metrics.lead_trend} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis dataKey="day" tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: 'var(--muted-foreground)' }} axisLine={false} tickLine={false} />
                <Tooltip wrapperStyle={{ maxWidth: 'calc(100vw - 32px)' }} contentStyle={{ fontSize: 12, border: '1px solid var(--border)', borderRadius: 8 }} />
                <Line type="monotone" dataKey="leads" stroke="var(--primary)" strokeWidth={2} dot={false} name="线索" />
                <Line type="monotone" dataKey="scanned" stroke="var(--muted-foreground)" strokeWidth={1.5} dot={false} name="扫描量" strokeDasharray="4 2" />
              </LineChart>
            </ResponsiveContainer>
          )}
        </section>

        <section className="rounded-xl border bg-card p-4">
          <SectionTitle title="线索意向分布" subtitle={`共 ${metrics.intent_distribution.reduce((sum, item) => sum + item.value, 0)} 条`} />
          {metrics.intent_distribution.length === 0 ? <EmptyState compact title="暂无意向数据" /> : (
            <>
              <ResponsiveContainer width="100%" height={120}>
                <PieChart><Pie data={metrics.intent_distribution} cx="50%" cy="50%" innerRadius={30} outerRadius={52} dataKey="value" paddingAngle={2}>{metrics.intent_distribution.map((entry) => <Cell key={entry.name} fill={entry.color} />)}</Pie><Tooltip /></PieChart>
              </ResponsiveContainer>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-2">
                {metrics.intent_distribution.map((item) => <div key={item.name} className="flex min-w-24 flex-1 items-center justify-between gap-2 text-xs"><span className="flex items-center gap-1.5 text-muted-foreground"><span className="h-2 w-2 rounded-full" style={{ background: item.color }} />{item.name}</span><strong>{item.value}</strong></div>)}
              </div>
            </>
          )}
        </section>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <section className="overflow-hidden rounded-xl border bg-card lg:col-span-2">
          <PanelHeader title="活动表现" action="全部活动" onAction={() => navigate('/campaigns')} />
          {metrics.campaign_performance.length === 0 ? <EmptyState title="暂无营销活动" description="创建活动后，这里会显示真实表现。" /> : (
            <div className="overflow-x-auto"><table className="w-full min-w-[640px] text-xs"><thead><tr className="border-b bg-muted/40">{['活动名称', '平台', '状态', '线索', '待审批', '最近执行'].map((heading) => <th key={heading} className="px-4 py-3 text-left font-medium text-muted-foreground">{heading}</th>)}</tr></thead><tbody>{metrics.campaign_performance.map((item) => <tr key={item.id} className="border-b last:border-0 hover:bg-muted/30"><td className="max-w-52 truncate px-4 py-3 font-medium">{item.name}</td><td className="px-4 py-3" style={{ color: platformColors[item.platform.toLowerCase()] }}>{platformLabels[item.platform.toLowerCase()] || item.platform}</td><td className="px-4 py-3"><StatusBadge status={item.status} label={formatCampaignStatus(item.status, t)} /></td><td className="px-4 py-3">{item.leads}</td><td className="px-4 py-3">{item.pending}</td><td className="px-4 py-3 text-muted-foreground">{item.lastRun}</td></tr>)}</tbody></table></div>
          )}
        </section>

        <section className="overflow-hidden rounded-xl border bg-card">
          <PanelHeader title="最近执行" action="查看全部" onAction={() => navigate('/execution-records')} />
          {metrics.recent_executions.length === 0 ? <EmptyState compact title="暂无执行记录" /> : <div className="p-2">{metrics.recent_executions.map((item) => <div key={item.id} className="flex items-start gap-3 rounded-lg p-2.5 hover:bg-muted/40"><span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${item.status === 'completed' ? 'bg-emerald-500' : item.status === 'running' ? 'bg-primary' : item.status === 'failed' ? 'bg-destructive' : 'bg-muted-foreground'}`} /><div className="min-w-0 flex-1"><p className="truncate text-xs font-medium">{item.campaign}</p><p className="mt-0.5 text-[11px] text-muted-foreground">{item.id} · {item.comments} 评论 · {item.leads} 线索</p></div><StatusBadge status={item.status} label={formatExecutionStatus(item.status, t)} /></div>)}</div>}
        </section>
      </div>

      <section className="overflow-hidden rounded-xl border bg-card">
        <PanelHeader title={`待审批回复（${metrics.pending_replies}）`} action="查看全部" onAction={() => navigate('/reply-tasks')} />
        {metrics.pending_replies_list.length === 0 ? <EmptyState title="暂无待审批回复" /> : (
          <div className="overflow-x-auto"><table className="w-full min-w-[760px] text-xs"><thead><tr className="border-b bg-muted/40">{['作者', '原始评论', '匹配规则', '回复预览', '活动', '时间', '操作'].map((heading) => <th key={heading} className="px-4 py-3 text-left font-medium text-muted-foreground">{heading}</th>)}</tr></thead><tbody>{metrics.pending_replies_list.map((item) => <tr key={item.id} className="border-b last:border-0"><td className="whitespace-nowrap px-4 py-3 font-medium">{item.author}</td><td className="max-w-44 truncate px-4 py-3">{item.comment || '—'}</td><td className="px-4 py-3">{item.keyword}</td><td className="max-w-44 truncate px-4 py-3 text-muted-foreground">{item.preview || '—'}</td><td className="px-4 py-3">{item.campaign}</td><td className="whitespace-nowrap px-4 py-3 text-muted-foreground">{item.time}</td><td className="px-4 py-3"><Button size="sm" onClick={() => navigate('/reply-tasks')}>审核</Button></td></tr>)}</tbody></table></div>
        )}
      </section>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <section className="overflow-hidden rounded-xl border bg-card">
          <PanelHeader title="平台账号状态" action="管理账号" onAction={() => navigate('/platform-accounts')} />
          {metrics.platform_status.length === 0 ? <EmptyState compact title="暂无平台账号" /> : <div className="p-2">{metrics.platform_status.map((item) => { const key = item.name.toLowerCase(); return <div key={item.id} className="flex min-h-12 items-center gap-3 rounded-lg px-2 py-2 hover:bg-muted/40"><div className="flex h-8 w-8 items-center justify-center rounded-lg text-xs font-bold text-white" style={{ background: platformColors[key] || 'var(--primary)' }}>{(platformLabels[key] || item.name).slice(0, 1)}</div><div className="min-w-0 flex-1"><p className="truncate text-xs font-medium">{item.displayName}</p><p className="truncate text-[11px] text-muted-foreground">{platformLabels[key] || item.name}{item.handle ? ` · ${item.handle}` : ''}</p></div><StatusBadge status={item.loginStatus} label={formatLoginStatus(item.loginStatus, t)} /></div> })}</div>}
        </section>

        <section className="rounded-xl border bg-card p-4">
          <SectionTitle title="Token 用量" subtitle="后端当前提供真实用量，但未提供配额总量" />
          <div className="mt-4 grid grid-cols-2 gap-3">
            <div className="rounded-lg bg-muted/55 p-4"><p className="text-xs text-muted-foreground">今日 Token</p><p className="mt-2 text-2xl font-bold">{metrics.tokens_today.toLocaleString()}</p></div>
            <div className="rounded-lg bg-muted/55 p-4"><p className="text-xs text-muted-foreground">本月 Token</p><p className="mt-2 text-2xl font-bold">{metrics.tokens_this_month.toLocaleString()}</p></div>
          </div>
        </section>
      </div>
    </PageContainer>
  )
}

function SectionTitle({ title, subtitle }: { title: string; subtitle?: string }) { return <div className="mb-4"><h2 className="text-sm font-semibold">{title}</h2>{subtitle && <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>}</div> }
function PanelHeader({ title, action, onAction }: { title: string; action: string; onAction: () => void }) { return <div className="flex items-center justify-between border-b px-4 py-3"><h2 className="text-sm font-semibold">{title}</h2><button className="flex min-h-9 items-center gap-1 text-xs font-medium text-primary hover:underline" onClick={onAction}>{action}<ChevronRight className="h-3 w-3" /></button></div> }
function DashboardSkeleton() { return <PageContainer maxWidth="dashboard" className="flex flex-col gap-5"><div className="flex justify-between"><div><Skeleton className="h-8 w-32" /><Skeleton className="mt-2 h-4 w-72" /></div><Skeleton className="h-10 w-36" /></div><div className="grid grid-cols-2 gap-3 md:grid-cols-4 2xl:grid-cols-8">{Array.from({ length: 8 }).map((_, index) => <Skeleton key={index} className="h-24" />)}</div><div className="grid grid-cols-1 gap-4 md:grid-cols-3"><Skeleton className="h-56 md:col-span-2" /><Skeleton className="h-56" /></div><Skeleton className="h-72" /><Skeleton className="h-56" /></PageContainer> }
