import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bell, CheckCheck, ExternalLink } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useNotifications, useMarkAllNotificationsRead, useMarkNotificationRead } from '../api/notifications'
import PageContainer from '../components/layout/PageContainer'
import { EmptyState, ErrorState } from '../components/ui/PageState'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { formatNotificationMessage, formatNotificationTitle } from '../utils/formatters'

const tabs = [{ key: 'all', label: '全部' }, { key: 'unread', label: '未读' }] as const
type Tab = typeof tabs[number]['key']

const typeStyle: Record<string, { color: string; bg: string }> = {
  info: { color: '#4a6fa5', bg: '#edf3fb' }, success: { color: '#15803d', bg: '#dcfce7' }, warning: { color: '#a16207', bg: '#fef9c3' }, error: { color: '#dc2626', bg: '#fee2e2' },
}

export default function NotificationCenter() {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState<Tab>('all')
  const { data, isLoading, error, refetch, isFetching } = useNotifications(activeTab === 'unread', 50)
  const markAll = useMarkAllNotificationsRead()
  const markRead = useMarkNotificationRead()

  if (isLoading && !data) return <NotificationSkeleton />
  if (error && !data) return <ErrorState description="无法加载通知，请检查网络后重试。" onRetry={() => refetch()} />

  const items = data?.items || []
  const unreadCount = data?.unread_count || 0

  return (
    <PageContainer maxWidth="content" className="flex min-h-full flex-col gap-4">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div><div className="flex items-center gap-2"><h1 className="text-2xl font-semibold tracking-tight">通知中心</h1>{unreadCount > 0 && <span className="rounded-full bg-destructive px-2 py-0.5 text-xs font-medium text-white">{unreadCount}</span>}</div><p className="mt-1 text-sm text-muted-foreground">查看真实系统事件和业务提醒。</p></div>
        <Button variant="outline" size="lg" disabled={unreadCount === 0 || markAll.isPending} onClick={() => markAll.mutate()}><CheckCheck className="h-4 w-4" />{markAll.isPending ? '处理中…' : '全部标为已读'}</Button>
      </header>
      <div className="flex border-b">{tabs.map((tab) => <button type="button" key={tab.key} onClick={() => setActiveTab(tab.key)} className={`min-h-11 border-b-2 px-4 text-sm font-medium ${activeTab === tab.key ? 'border-primary text-primary' : 'border-transparent text-muted-foreground'}`}>{tab.label}</button>)}{isFetching && <span className="ml-auto self-center text-xs text-muted-foreground">正在刷新…</span>}</div>
      {items.length === 0 ? <EmptyState title={activeTab === 'unread' ? '没有未读通知' : '暂无通知'} /> : <div className="flex flex-col gap-2">{items.map((item) => { const style = typeStyle[item.severity || item.type] || typeStyle.info; const title = formatNotificationTitle(item.type, t); const message = formatNotificationMessage(item.type, t); return <article key={item.id} className={`flex gap-3 rounded-xl border p-4 ${item.read ? 'bg-card' : 'border-primary/25 bg-accent/20'}`}><div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg" style={{ background: style.bg, color: style.color }}><Bell className="h-4 w-4" /></div><div className="min-w-0 flex-1"><div className="flex flex-wrap items-start justify-between gap-2"><h2 className="text-sm font-semibold">{title}</h2><time className="text-xs text-muted-foreground">{new Date(item.created_at).toLocaleString('zh-CN')}</time></div><p className="mt-1 break-words text-sm leading-relaxed text-muted-foreground">{message}</p><div className="mt-3 flex flex-wrap gap-2">{!item.read && <Button variant="outline" size="sm" disabled={markRead.isPending} onClick={() => markRead.mutate(item.id)}>标为已读</Button>}{item.action_url && <Button variant="ghost" size="sm" onClick={() => navigate(item.action_url!)}><ExternalLink className="h-3.5 w-3.5" />{item.action_label || '查看详情'}</Button>}</div></div></article> })}</div>}
    </PageContainer>
  )
}

function NotificationSkeleton() { return <PageContainer maxWidth="content" className="flex flex-col gap-4"><Skeleton className="h-16 w-72" /><Skeleton className="h-12 w-full" />{[0, 1, 2].map((item) => <Skeleton key={item} className="h-28 w-full" />)}</PageContainer> }
