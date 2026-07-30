import { Activity, Database, PlayCircle, Server, Shield, Users } from "lucide-react";
import { useState } from "react";

import {
  type BrowserRuntime,
  type QueueItem,
  type Tenant,
  useAdminQueue,
  useAdminRuntimes,
  useAdminTenants,
  useAdminUsers,
  useSystemHealth,
  useSystemUsage,
} from "../api/admin";
import MetricCard from "../components/ui/MetricCard";
import { EmptyState, ErrorState } from "../components/ui/PageState";
import StatusBadge from "../components/ui/StatusBadge";
import { Skeleton } from "../components/ui/skeleton";

const tabs = ["概览", "租户", "用户", "运行时与队列", "系统健康"] as const;
type Tab = (typeof tabs)[number];

const dateTime = (value?: string | null) =>
  value ? new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—";
const errorMessage = (error: unknown) => (error instanceof Error ? error.message : "请求系统管理数据时发生错误");
const planName = (tenant: Tenant) => tenant.plan?.name || tenant.plan?.code || "未配置";

function LoadingState() {
  return <div className="grid gap-3 md:grid-cols-2"><Skeleton className="h-32 rounded-xl" /><Skeleton className="h-32 rounded-xl" /></div>;
}

function TenantView({ tenants }: { tenants: Tenant[] }) {
  if (!tenants.length) return <EmptyState title="暂无租户" description="系统中还没有租户记录。" />;
  return (
    <>
      <div className="hidden overflow-x-auto rounded-xl border bg-card md:block">
        <table className="w-full text-sm">
          <thead><tr className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
            {['租户', '套餐', '成员', '活动', '状态', '创建时间'].map((item) => <th className="px-4 py-3 font-medium" key={item}>{item}</th>)}
          </tr></thead>
          <tbody>{tenants.map((tenant) => <tr className="border-b last:border-0" key={tenant.id}>
            <td className="px-4 py-3"><div className="font-medium">{tenant.name}</div><div className="text-xs text-muted-foreground">{tenant.slug} · {tenant.id}</div></td>
            <td className="px-4 py-3">{planName(tenant)}</td>
            <td className="px-4 py-3">{tenant.usage?.members ?? 0}</td>
            <td className="px-4 py-3">{tenant.usage?.campaigns ?? 0}</td>
            <td className="px-4 py-3"><StatusBadge status={tenant.status} variant="dot" /></td>
            <td className="px-4 py-3 text-muted-foreground">{dateTime(tenant.created_at)}</td>
          </tr>)}</tbody>
        </table>
      </div>
      <div className="grid gap-3 md:hidden">{tenants.map((tenant) => <article className="rounded-xl border bg-card p-4" key={tenant.id}>
        <div className="flex items-start justify-between gap-3"><div><h2 className="font-medium">{tenant.name}</h2><p className="text-xs text-muted-foreground">{tenant.slug}</p></div><StatusBadge status={tenant.status} variant="dot" /></div>
        <dl className="mt-3 grid grid-cols-3 gap-2 text-xs"><div><dt className="text-muted-foreground">套餐</dt><dd>{planName(tenant)}</dd></div><div><dt className="text-muted-foreground">成员</dt><dd>{tenant.usage?.members ?? 0}</dd></div><div><dt className="text-muted-foreground">活动</dt><dd>{tenant.usage?.campaigns ?? 0}</dd></div></dl>
      </article>)}</div>
    </>
  );
}

function RuntimeCard({ runtime }: { runtime: BrowserRuntime }) {
  return <article className="rounded-xl border bg-card p-4"><div className="flex justify-between gap-3"><div><h3 className="font-medium">{runtime.runtime_type}</h3><p className="break-all text-xs text-muted-foreground">{runtime.id}</p></div><StatusBadge status={runtime.status} variant="dot" /></div><dl className="mt-3 grid grid-cols-2 gap-2 text-xs"><div><dt className="text-muted-foreground">租户</dt><dd className="break-all">{runtime.tenant_id}</dd></div><div><dt className="text-muted-foreground">端口</dt><dd>{runtime.cdp_port}</dd></div><div><dt className="text-muted-foreground">最后检查</dt><dd>{dateTime(runtime.last_health_check_at)}</dd></div><div><dt className="text-muted-foreground">启动时间</dt><dd>{dateTime(runtime.started_at)}</dd></div></dl>{runtime.last_error && <p className="mt-3 text-xs text-destructive">{runtime.last_error}</p>}</article>;
}

function QueueCard({ item }: { item: QueueItem }) {
  return <article className="rounded-xl border bg-card p-4"><div className="flex justify-between gap-3"><div><h3 className="font-medium">执行 {item.execution_id}</h3><p className="text-xs text-muted-foreground">活动 {item.campaign_id}</p></div><StatusBadge status={item.status} variant="dot" /></div><div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground"><span>优先级 {item.priority}</span><span>尝试 {item.attempt_count}/{item.max_attempts}</span><span>入队 {dateTime(item.queued_at)}</span></div>{item.error_message && <p className="mt-3 text-xs text-destructive">{item.error_message}</p>}</article>;
}

export default function SystemAdmin() {
  const [activeTab, setActiveTab] = useState<Tab>("概览");
  const usage = useSystemUsage();
  const tenants = useAdminTenants();
  const users = useAdminUsers();
  const health = useSystemHealth();
  const runtimes = useAdminRuntimes();
  const queue = useAdminQueue();

  const healthServices = health.data ? [
    { name: "API", ok: health.data.api.status === "ok", detail: health.data.api.status },
    { name: "PostgreSQL", ok: health.data.postgres.status === "ok", detail: health.data.postgres.status },
    { name: "Worker", ok: health.data.worker.online, detail: `${health.data.worker.worker_count} 个在线` },
    { name: "Scheduler", ok: health.data.scheduler.online, detail: `${health.data.scheduler.queued_tasks} 排队 / ${health.data.scheduler.running_tasks} 运行` },
  ] : [];

  return <div className="flex min-h-full flex-col gap-4 p-4 md:p-6">
    <header className="flex items-center gap-2"><Shield className="text-primary" size={20} /><div><h1 className="text-xl font-semibold">系统管理</h1><p className="text-xs text-muted-foreground">来自系统管理 API 的实时数据</p></div></header>
    <nav aria-label="系统管理区域" className="flex overflow-x-auto border-b">{tabs.map((tab) => <button className={`shrink-0 border-b-2 px-4 py-2.5 text-sm font-medium ${activeTab === tab ? 'border-primary text-primary' : 'border-transparent text-muted-foreground'}`} key={tab} onClick={() => setActiveTab(tab)}>{tab}</button>)}</nav>

    {activeTab === "概览" && (usage.isLoading ? <LoadingState /> : usage.isError ? <ErrorState description={errorMessage(usage.error)} onRetry={() => usage.refetch()} /> : usage.data && <div className="grid grid-cols-2 gap-3 lg:grid-cols-5"><MetricCard label="租户" value={usage.data.tenants} icon={<Database size={16} />} /><MetricCard label="用户" value={usage.data.users} icon={<Users size={16} />} /><MetricCard label="执行" value={usage.data.executions} icon={<PlayCircle size={16} />} /><MetricCard label="Token" value={usage.data.tokens.toLocaleString()} icon={<Activity size={16} />} /><MetricCard label="在线 Worker" value={usage.data.worker_health} icon={<Server size={16} />} accent={usage.data.worker_health ? "success" : "warning"} /></div>)}

    {activeTab === "租户" && (tenants.isLoading ? <LoadingState /> : tenants.isError ? <ErrorState description={errorMessage(tenants.error)} onRetry={() => tenants.refetch()} /> : <TenantView tenants={tenants.data?.items ?? []} />)}

    {activeTab === "用户" && (users.isLoading ? <LoadingState /> : users.isError ? <ErrorState description={errorMessage(users.error)} onRetry={() => users.refetch()} /> : !users.data?.items.length ? <EmptyState title="暂无用户" description="系统中还没有用户记录。" /> : <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{users.data.items.map((user) => <article className="rounded-xl border bg-card p-4" key={user.id}><div className="flex items-start justify-between gap-3"><div className="min-w-0"><h2 className="truncate font-medium">{user.display_name}</h2><p className="truncate text-xs text-muted-foreground">{user.email}</p></div><StatusBadge status={user.status} variant="dot" /></div><div className="mt-3 flex items-center justify-between text-xs text-muted-foreground"><span>{user.is_system_admin ? '系统管理员' : '普通用户'}</span><span>{dateTime(user.created_at)}</span></div></article>)}</div>)}

    {activeTab === "运行时与队列" && <div className="grid gap-5 xl:grid-cols-2"><section><h2 className="mb-3 font-semibold">浏览器运行时 ({runtimes.data?.total ?? 0})</h2>{runtimes.isLoading ? <LoadingState /> : runtimes.isError ? <ErrorState description={errorMessage(runtimes.error)} onRetry={() => runtimes.refetch()} /> : !runtimes.data?.items.length ? <EmptyState compact title="暂无运行时" /> : <div className="grid gap-3">{runtimes.data.items.map((item) => <RuntimeCard key={item.id} runtime={item} />)}</div>}</section><section><h2 className="mb-3 font-semibold">执行队列 ({queue.data?.total ?? 0})</h2>{queue.isLoading ? <LoadingState /> : queue.isError ? <ErrorState description={errorMessage(queue.error)} onRetry={() => queue.refetch()} /> : !queue.data?.items.length ? <EmptyState compact title="队列为空" /> : <div className="grid gap-3">{queue.data.items.map((item) => <QueueCard item={item} key={item.id} />)}</div>}</section></div>}

    {activeTab === "系统健康" && (health.isLoading ? <LoadingState /> : health.isError ? <ErrorState description={errorMessage(health.error)} onRetry={() => health.refetch()} /> : <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{healthServices.map((service) => <article className={`rounded-xl border bg-card p-4 ${service.ok ? '' : 'border-destructive/40'}`} key={service.name}><div className="flex items-center justify-between"><h2 className="font-medium">{service.name}</h2><StatusBadge status={service.ok ? 'active' : 'unhealthy'} label={service.ok ? '正常' : '异常'} variant="dot" /></div><p className="mt-2 text-xs text-muted-foreground">{service.detail}</p></article>)}</div>)}
  </div>;
}
