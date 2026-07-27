import { useEffect, useState, useMemo } from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell
} from 'recharts'
import {
  Megaphone, Users, MessageSquare, UserPlus, Star, CheckCircle,
  Reply, XCircle, ChevronRight
} from 'lucide-react'
import { useResource } from '../hooks/useResource'
import MetricCard from '../components/ui/MetricCard'
import SafetyAlert from '../components/ui/SafetyAlert'
import StatusBadge from '../components/ui/StatusBadge'
import TopBar from '../components/layout/TopBar'

const platColors: Record<string, string> = {
  Facebook: '#1877f2', Instagram: '#e1306c', TikTok: '#010101',
  X: '#1da1f2', YouTube: '#ff0000',
}

interface DashboardProps {
  onNavigate: (page: string) => void
  onMenuOpen?: () => void
}

export default function Dashboard({ onNavigate, onMenuOpen }: DashboardProps) {
  const summary = useResource<Record<string, any>>('/api/dashboard/summary', {})

  const leadTrend = useMemo(() => {
    const data = summary.data?.lead_trend
    if (!Array.isArray(data)) return [
      { day: '7/17', leads: 52, scanned: 980 },
      { day: '7/18', leads: 68, scanned: 1050 },
      { day: '7/19', leads: 45, scanned: 890 },
      { day: '7/20', leads: 79, scanned: 1120 },
      { day: '7/21', leads: 91, scanned: 1280 },
      { day: '7/22', leads: 73, scanned: 1150 },
      { day: '7/23', leads: 86, scanned: 1284 },
    ]
    return data
  }, [summary.data])

  const intentDist = useMemo(() => {
    const data = summary.data?.intent_distribution
    if (!Array.isArray(data)) return [
      { name: '高意向', value: 21, color: '#ef4444' },
      { name: '中意向', value: 38, color: '#f59e0b' },
      { name: '低意向', value: 27, color: '#6366f1' },
    ]
    return data
  }, [summary.data])

  const campaigns = useMemo(() => {
    const data = summary.data?.campaign_performance
    if (!Array.isArray(data)) return [
      { name: '跨境电商引流 – Facebook', platform: 'Facebook', status: '运行中', leads: 312, pending: 5, lastRun: '10 分钟前' },
      { name: '独立站流量获取', platform: 'Instagram', status: '运行中', leads: 198, pending: 4, lastRun: '25 分钟前' },
      { name: '海外招商 – YouTube', platform: 'YouTube', status: '已暂停', leads: 87, pending: 3, lastRun: '3 小时前' },
      { name: 'TikTok 品牌曝光', platform: 'TikTok', status: '运行中', leads: 143, pending: 2, lastRun: '1 小时前' },
      { name: 'X 高净值用户', platform: 'X', status: '异常', leads: 62, pending: 0, lastRun: '昨天' },
    ]
    return data
  }, [summary.data])

  const recentExecutions = useMemo(() => {
    const data = summary.data?.recent_executions
    if (!Array.isArray(data)) return [
      { id: 'EX-2847', campaign: '跨境电商引流', status: '已完成', comments: 284, leads: 19 },
      { id: 'EX-2846', campaign: '独立站获客', status: '已完成', comments: 201, leads: 14 },
      { id: 'EX-2845', campaign: 'TikTok 品牌曝光', status: '执行中', comments: 143, leads: 9 },
      { id: 'EX-2844', campaign: 'X 高净值用户', status: '异常', comments: 0, leads: 0 },
    ]
    return data
  }, [summary.data])

  const pendingReplies = useMemo(() => {
    const data = summary.data?.pending_replies
    if (!Array.isArray(data)) return [
      { author: '@zhangwei88', comment: '请问有没有针对中小企业的套餐价格...', keyword: '套餐价格', preview: '您好 zhangwei88，感谢您的留言！', campaign: '跨境电商引流', time: '15 分钟前' },
      { author: '@maria.santos', comment: 'How can I contact your sales team?', keyword: '联系方式', preview: 'Hi Maria, thanks for your interest!', campaign: '独立站获客', time: '28 分钟前' },
      { author: '@李大山_gz', comment: '能不能先试用一下，看看效果再决定...', keyword: '试用', preview: '您好，我们提供 14 天免费试用', campaign: '跨境电商引流', time: '42 分钟前' },
      { author: '@kenji.tanaka', comment: 'I am interested in your product pricing', keyword: '价格', preview: '您好 Kenji，很高兴您感兴趣！', campaign: 'TikTok 品牌曝光', time: '1 小时前' },
    ]
    return data
  }, [summary.data])

  const platformStatus = useMemo(() => {
    const data = summary.data?.platform_status
    if (!Array.isArray(data)) return [
      { name: 'Facebook', handle: '@smmo_business', loginStatus: '登录有效' },
      { name: 'Instagram', handle: '@smmo_official', loginStatus: '登录有效' },
      { name: 'TikTok', handle: '@smmo_tiktok', loginStatus: '登录有效' },
      { name: 'X', handle: '@smmo_x', loginStatus: '需要重新登录' },
      { name: 'YouTube', handle: '@smmo_channel', loginStatus: '已停止' },
    ]
    return data
  }, [summary.data])

  const metrics = summary.data || {}

  return (
    <div className="flex flex-col min-h-full">
      <TopBar
        breadcrumbs={['仪表盘']}
        pageTitle="仪表盘"
        onRefresh={summary.refresh}
        showCreateCampaign
        onCreateCampaign={() => onNavigate('campaign-settings')}
        onMenuOpen={onMenuOpen}
      />
      <div className="flex-1 p-4 md:p-6 flex flex-col gap-4 md:gap-5">
        {/* Header */}
        <div className="hidden md:flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-semibold text-gray-900">仪表盘</h1>
            <p className="text-sm text-gray-500 mt-0.5">查看社媒获客、任务执行和回复审批的整体状态</p>
          </div>
          <div className="flex items-center gap-2">
            <select className="text-sm border rounded-lg px-3 py-1.5 bg-white focus:outline-none" style={{ borderColor: 'var(--border)' }}>
              <option>最近 7 天</option>
              <option>最近 14 天</option>
              <option>最近 30 天</option>
            </select>
          </div>
        </div>

        {/* Safety alert */}
        {!metrics.system_send_enabled && <SafetyAlert onViewSettings={() => onNavigate('settings')} />}

        {/* Metrics */}
        <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-2 md:gap-3">
          <MetricCard label="活跃营销活动" value={metrics.active_campaigns || 0} change={2} changeLabel="vs 昨天" icon={<Megaphone size={14} />} />
          <MetricCard label="已连接平台账号" value={metrics.connected_accounts || 0} icon={<Users size={14} />} />
          <MetricCard label="今日扫描评论" value={metrics.comments_scanned_today || 0} change={156} changeLabel="vs 昨天" icon={<MessageSquare size={14} />} />
          <MetricCard label="今日新增线索" value={metrics.leads_today || 0} change={13} changeLabel="vs 昨天" icon={<UserPlus size={14} />} accent="success" />
          <MetricCard label="高意向线索" value={metrics.high_intent_leads || 0} change={-3} changeLabel="vs 昨天" icon={<Star size={14} />} accent="warning" />
          <MetricCard label="待审批回复" value={metrics.pending_replies || 0} icon={<CheckCircle size={14} />} accent="warning" />
          <MetricCard label="今日已回复" value={metrics.today_replied || 0} icon={<Reply size={14} />} tooltip="系统回复发送开关当前关闭" />
          <MetricCard label="今日失败任务" value={metrics.today_failed || 0} icon={<XCircle size={14} />} accent="danger" />
        </div>

        {/* Charts row */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="md:col-span-2 bg-white border rounded-xl p-4" style={{ borderColor: 'var(--border)' }}>
            <div className="flex items-center justify-between mb-4">
              <div>
                <div className="text-sm font-semibold text-gray-800">线索趋势</div>
                <div className="text-xs text-gray-400 mt-0.5">最近 7 天</div>
              </div>
            </div>
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={leadTrend} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                <XAxis dataKey="day" tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ fontSize: 12, border: '1px solid #e5e7eb', borderRadius: 8 }} />
                <Line type="monotone" dataKey="leads" stroke="#4338ca" strokeWidth={2} dot={false} name="线索" />
                <Line type="monotone" dataKey="scanned" stroke="#d1d5db" strokeWidth={1.5} dot={false} name="扫描量" strokeDasharray="4 2" />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="bg-white border rounded-xl p-4" style={{ borderColor: 'var(--border)' }}>
            <div className="text-sm font-semibold text-gray-800 mb-1">线索意向分布</div>
            <div className="text-xs text-gray-400 mb-3">今日共 {metrics.leads_today || 86} 条</div>
            <ResponsiveContainer width="100%" height={110}>
              <PieChart>
                <Pie data={intentDist} cx="50%" cy="50%" innerRadius={28} outerRadius={50} dataKey="value" paddingAngle={2}>
                  {intentDist.map((entry: any, i: number) => <Cell key={i} fill={entry.color} />)}
                </Pie>
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
              </PieChart>
            </ResponsiveContainer>
            <div className="mt-2 flex flex-col gap-1">
              {intentDist.map((d: any) => (
                <div key={d.name} className="flex items-center justify-between text-xs">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full shrink-0" style={{ background: d.color }} />
                    <span className="text-gray-600">{d.name}</span>
                  </div>
                  <span className="font-medium text-gray-800">{d.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Campaign table + Executions */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="md:col-span-2 bg-white border rounded-xl overflow-hidden" style={{ borderColor: 'var(--border)' }}>
            <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: 'var(--border)' }}>
              <div className="text-sm font-semibold text-gray-800">活动表现</div>
              <button className="text-xs font-medium flex items-center gap-1 hover:underline" style={{ color: 'var(--primary)' }} onClick={() => onNavigate('campaigns')}>
                全部活动 <ChevronRight size={12} />
              </button>
            </div>
            {/* Desktop table */}
            <div className="hidden md:block overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b" style={{ borderColor: 'var(--border)' }}>
                    {['活动名称', '平台', '状态', '线索', '待审批', '最近执行'].map((h) => (
                      <th key={h} className="text-left px-4 py-2.5 text-gray-400 font-medium">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {campaigns.map((c: any, i: number) => (
                    <tr key={i} className="border-b last:border-0 hover:bg-gray-50" style={{ borderColor: 'var(--border)' }}>
                      <td className="px-4 py-2.5 font-medium text-gray-800 max-w-[180px] truncate">{c.name}</td>
                      <td className="px-4 py-2.5 font-medium" style={{ color: platColors[c.platform] }}>{c.platform}</td>
                      <td className="px-4 py-2.5"><StatusBadge status={c.status} /></td>
                      <td className="px-4 py-2.5 font-medium text-gray-800">{c.leads}</td>
                      <td className="px-4 py-2.5">{c.pending > 0 ? <span className="font-semibold" style={{ color: '#d97706' }}>{c.pending}</span> : '—'}</td>
                      <td className="px-4 py-2.5 text-gray-400">{c.lastRun}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {/* Mobile */}
            <div className="md:hidden divide-y">
              {campaigns.map((c: any, i: number) => (
                <div key={i} className="flex items-center gap-3 px-4 py-3">
                  <div className="w-2 h-2 rounded-full shrink-0" style={{ background: platColors[c.platform] }} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-800 truncate">{c.name}</div>
                    <div className="text-xs text-gray-400">{c.lastRun}</div>
                  </div>
                  <StatusBadge status={c.status} />
                </div>
              ))}
            </div>
          </div>

          <div className="bg-white border rounded-xl overflow-hidden" style={{ borderColor: 'var(--border)' }}>
            <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: 'var(--border)' }}>
              <div className="text-sm font-semibold text-gray-800">最近执行</div>
              <button className="text-xs font-medium flex items-center gap-1 hover:underline" style={{ color: 'var(--primary)' }} onClick={() => onNavigate('execution-records')}>
                查看全部 <ChevronRight size={12} />
              </button>
            </div>
            <div className="p-2">
              {recentExecutions.map((e: any, i: number) => (
                <div key={i} className="flex items-start gap-3 p-2.5 rounded-lg hover:bg-gray-50">
                  <div className="w-1.5 h-1.5 rounded-full mt-1.5 shrink-0" style={{ background: e.status === '已完成' ? '#10b981' : e.status === '执行中' ? '#6366f1' : '#ef4444' }} />
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium text-gray-800 truncate">{e.campaign}</div>
                    <div className="text-[11px] text-gray-400 mt-0.5">{e.id} · {e.comments} 评论 · {e.leads} 线索</div>
                  </div>
                  <StatusBadge status={e.status} />
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Pending approvals */}
        <div className="bg-white border rounded-xl overflow-hidden" style={{ borderColor: 'var(--border)' }}>
          <div className="flex items-center justify-between px-4 py-3 border-b" style={{ borderColor: 'var(--border)' }}>
            <div className="flex items-center gap-2">
              <div className="text-sm font-semibold text-gray-800">待审批回复</div>
              <span className="text-[11px] font-medium px-1.5 py-0.5 rounded-full" style={{ background: '#fef3c7', color: '#d97706' }}>{pendingReplies.length}</span>
            </div>
            <button className="text-xs font-medium flex items-center gap-1 hover:underline" style={{ color: 'var(--primary)' }} onClick={() => onNavigate('reply-tasks')}>
              查看全部 <ChevronRight size={12} />
            </button>
          </div>
          {/* Desktop table */}
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b" style={{ borderColor: 'var(--border)' }}>
                  {['作者', '原始评论', '匹配关键词', '回复预览', '活动', '时间', '操作'].map((h) => (
                    <th key={h} className="text-left px-4 py-2.5 text-gray-400 font-medium">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {pendingReplies.map((r: any, i: number) => (
                  <tr key={i} className="border-b last:border-0 hover:bg-gray-50" style={{ borderColor: 'var(--border)' }}>
                    <td className="px-4 py-2.5 font-medium text-gray-800 whitespace-nowrap">{r.author}</td>
                    <td className="px-4 py-2.5 text-gray-600 max-w-[140px]"><span className="truncate block">{r.comment?.slice(0, 24)}…</span></td>
                    <td className="px-4 py-2.5"><span className="px-1.5 py-0.5 rounded text-[11px] font-medium" style={{ background: 'var(--accent)', color: 'var(--primary)' }}>{r.keyword}</span></td>
                    <td className="px-4 py-2.5 text-gray-500 max-w-[140px]"><span className="truncate block">{r.preview?.slice(0, 24)}…</span></td>
                    <td className="px-4 py-2.5 text-gray-500 whitespace-nowrap">{r.campaign}</td>
                    <td className="px-4 py-2.5 text-gray-400 whitespace-nowrap">{r.time}</td>
                    <td className="px-4 py-2.5">
                      <button className="px-2.5 py-1 rounded-md text-xs font-medium text-white hover:opacity-90" style={{ background: 'var(--primary)', minHeight: 28 }} onClick={() => onNavigate('reply-tasks')}>审核</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {/* Mobile */}
          <div className="md:hidden divide-y">
            {pendingReplies.map((r: any, i: number) => (
              <div key={i} className="px-4 py-3 flex items-center gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-sm font-medium text-gray-900">{r.author}</span>
                    <span className="px-1.5 py-0.5 rounded text-[11px] font-medium shrink-0" style={{ background: 'var(--accent)', color: 'var(--primary)' }}>{r.keyword}</span>
                  </div>
                  <div className="text-xs text-gray-500 truncate">{r.comment}</div>
                  <div className="text-[11px] text-gray-400 mt-0.5">{r.time}</div>
                </div>
                <button className="px-3 py-2 rounded-lg text-xs font-medium text-white shrink-0" style={{ background: 'var(--primary)', minHeight: 44 }} onClick={() => onNavigate('reply-tasks')}>审核</button>
              </div>
            ))}
          </div>
        </div>

        {/* Platform status + Quota */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-white border rounded-xl overflow-hidden" style={{ borderColor: 'var(--border)' }}>
            <div className="text-sm font-semibold text-gray-800 px-4 py-3 border-b" style={{ borderColor: 'var(--border)' }}>平台账号状态</div>
            <div className="p-2">
              {platformStatus.map((p: any, i: number) => (
                <div key={i} className="flex items-center gap-2.5 px-2 py-2 rounded-lg hover:bg-gray-50" style={{ minHeight: 44 }}>
                  <div className="w-7 h-7 rounded-lg flex items-center justify-center text-white text-[10px] font-bold shrink-0" style={{ background: platColors[p.name] }}>{p.name[0]}</div>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-medium text-gray-800">{p.name}</div>
                    <div className="text-[11px] text-gray-400 truncate">{p.handle}</div>
                  </div>
                  <StatusBadge status={p.loginStatus} />
                </div>
              ))}
            </div>
          </div>

          <div className="bg-white border rounded-xl p-4" style={{ borderColor: 'var(--border)' }}>
            <div className="text-sm font-semibold text-gray-800 mb-3">运营用量</div>
            {[
              { label: '评论扫描', used: metrics.comments_scanned || 8453, total: 50000 },
              { label: '回复候选', used: metrics.reply_candidates || 243, total: 1000 },
              { label: 'LLM Token', used: metrics.tokens_used || 0, total: 100000 },
            ].map((q) => (
              <div key={q.label} className="mb-3 last:mb-0">
                <div className="flex items-center justify-between text-xs mb-1.5">
                  <span className="text-gray-600">{q.label}</span>
                  <span className="text-gray-400 font-medium">{q.used.toLocaleString()} / {q.total.toLocaleString()}</span>
                </div>
                <div className="h-1.5 rounded-full bg-gray-100 overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${Math.min((q.used / q.total) * 100, 100)}%`, background: (q.used / q.total) > 0.8 ? '#ef4444' : 'var(--primary)' }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
