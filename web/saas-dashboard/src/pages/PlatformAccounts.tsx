import { useState } from 'react'
import {
  AlertTriangle,
  CheckCircle,
  Grid2X2,
  List,
  LogIn,
  Monitor,
  ExternalLink,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Square,
} from 'lucide-react'
import { usePlatformAccounts, useStopRuntime, useRestartRuntime, useConnectPlatformAccount, useCheckLoginPlatformAccount, useRuntimeCapabilities, type PlatformAccount } from '../api/platform-accounts'
import StatusBadge from '../components/ui/StatusBadge'
import ConfirmModal from '../components/ui/ConfirmModal'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'

function isRunning(status: string) {
  return status === '运行中' || status === 'running'
}

function isRuntimeError(status: string) {
  return status === '异常' || status === 'error' || status === 'failed' || status === 'unhealthy'
}

function isLoginValid(status: string) {
  return status === '登录有效' || status === 'valid' || status === 'authenticated' || status === 'logged_in'
}

function runtimeLabel(status: string) {
  if (isRunning(status)) return '运行中'
  if (isRuntimeError(status)) return '异常'
  return '已停止'
}

function platformMark(platform: string) {
  const marks: Record<string, string> = {
    facebook: 'fb',
    instagram: 'ig',
    tiktok: 'tk',
    x: 'X',
    twitter: 'X',
    youtube: 'yt',
  }
  return marks[platform.toLowerCase()] || platform.slice(0, 2)
}

export default function PlatformAccounts() {
  const { data: accounts, isLoading, error, refetch } = usePlatformAccounts()
  const { data: runtimeCapabilities } = useRuntimeCapabilities()
  const stopRuntime = useStopRuntime()
  const restartRuntime = useRestartRuntime()
  const connectAccount = useConnectPlatformAccount()
  const checkLogin = useCheckLoginPlatformAccount()

  const [viewMode, setViewMode] = useState<'card' | 'list'>('card')
  const [confirmStop, setConfirmStop] = useState<string | null>(null)

  const handleStop = (id: string) => {
    stopRuntime.mutate(id)
    setConfirmStop(null)
  }

  const openLiveBrowser = async (id: string) => {
    window.open(getNoVncUrl(), '_blank', 'noopener,noreferrer')
    await connectAccount.mutateAsync(id)
  }

  if (isLoading) return <PlatformAccountsSkeleton />

  if (error) {
    return (
      <div className="p-4 md:p-6">
        <Alert variant="destructive">
          <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
            <span>加载平台账号失败，请刷新页面重试</span>
            <Button variant="outline" size="sm" onClick={() => refetch()}>重试</Button>
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  const accountList = accounts || []

  return (
    <div className="min-h-full p-4 md:p-6">
      <div className="mx-auto flex max-w-[1440px] flex-col gap-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold tracking-tight text-foreground">平台账号</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              管理已连接的社媒平台账号和浏览器运行时
              {runtimeCapabilities && (
                <span className="ml-2 text-xs">
                  {runtimeCapabilities.browser_platform} / {runtimeCapabilities.browser_backend || 'browser'} / {runtimeCapabilities.browser_headless ? 'headless' : '可视化'}
                </span>
              )}
            </p>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <div className="flex rounded-lg border bg-card p-0.5" aria-label="视图切换">
              <button
                type="button"
                className={`flex h-9 items-center gap-1.5 rounded-md px-3 text-sm transition ${viewMode === 'card' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'}`}
                onClick={() => setViewMode('card')}
                aria-pressed={viewMode === 'card'}
              >
                <Grid2X2 className="h-4 w-4" /> 卡片
              </button>
              <button
                type="button"
                className={`flex h-9 items-center gap-1.5 rounded-md px-3 text-sm transition ${viewMode === 'list' ? 'bg-primary text-primary-foreground shadow-sm' : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'}`}
                onClick={() => setViewMode('list')}
                aria-pressed={viewMode === 'list'}
              >
                <List className="h-4 w-4" /> 列表
              </button>
            </div>
            <Button variant="outline" onClick={() => refetch()}>
              <RefreshCw className="h-4 w-4" />
              <span className="hidden sm:inline">全部刷新</span>
            </Button>
            <Button>
              <Plus className="h-4 w-4" /> 添加账号
            </Button>
          </div>
        </div>

        {accountList.length === 0 ? (
          <div className="flex min-h-80 flex-col items-center justify-center rounded-2xl border border-dashed bg-card px-6 text-center">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-accent text-primary">
              <Monitor className="h-6 w-6" />
            </div>
            <h2 className="font-semibold">尚未添加平台账号</h2>
            <p className="mt-1 max-w-sm text-sm text-muted-foreground">添加社媒账号后，可在这里管理连接状态和浏览器运行时。</p>
            <Button className="mt-5"><Plus className="h-4 w-4" />添加账号</Button>
          </div>
        ) : (
          <>
            <div className={`${viewMode === 'card' ? 'grid' : 'hidden'} grid-cols-1 gap-4 lg:grid-cols-2 2xl:grid-cols-3`}>
              {accountList.map((account) => (
                <AccountCard
                  key={account.id}
                  account={account}
                  onStart={() => connectAccount.mutate(account.id)}
                  onStop={() => setConfirmStop(account.id)}
                  onRestart={() => restartRuntime.mutate(account.id)}
                  onCheckLogin={() => checkLogin.mutate(account.id)}
                  onOpenBrowser={() => openLiveBrowser(account.id)}
                  busy={connectAccount.isPending || restartRuntime.isPending || checkLogin.isPending || stopRuntime.isPending}
                />
              ))}
            </div>

            <div className={`${viewMode === 'list' ? 'hidden md:block' : 'hidden'} overflow-hidden rounded-2xl border bg-card shadow-sm`}>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[900px] text-sm">
                  <thead className="bg-muted/55 text-left">
                    <tr className="border-b">
                      {['账号', '平台', '连接状态', '登录状态', '运行时状态', 'CDP 端口', '最近检查', '操作'].map((heading) => (
                        <th key={heading} className="px-4 py-3 text-xs font-semibold text-muted-foreground">{heading}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {accountList.map((account) => (
                      <tr key={account.id} className={`border-b transition-colors last:border-b-0 hover:bg-accent/35 ${isRuntimeError(account.runtime_status) ? 'bg-destructive/5' : ''}`}>
                        <td className="px-4 py-3">
                          <AccountIdentity account={account} />
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">{account.platform}</td>
                        <td className="px-4 py-3"><StatusBadge status={account.connection_status} /></td>
                        <td className="px-4 py-3"><LoginState status={account.login_status} /></td>
                        <td className="px-4 py-3"><RuntimeState status={account.runtime_status} /></td>
                        <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{account.cdp_port ? `:${account.cdp_port}` : '—'}</td>
                        <td className="px-4 py-3 text-muted-foreground">{account.last_checked}</td>
                        <td className="px-4 py-3">
                          <AccountActions
                            account={account}
                            compact
                            onStart={() => connectAccount.mutate(account.id)}
                            onStop={() => setConfirmStop(account.id)}
                            onRestart={() => restartRuntime.mutate(account.id)}
                            onCheckLogin={() => checkLogin.mutate(account.id)}
                            onOpenBrowser={() => openLiveBrowser(account.id)}
                            busy={connectAccount.isPending || restartRuntime.isPending || checkLogin.isPending || stopRuntime.isPending}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {viewMode === 'list' && (
              <div className="grid grid-cols-1 gap-3 md:hidden">
                {accountList.map((account) => (
                  <AccountCard
                    key={account.id}
                    account={account}
                    onStart={() => connectAccount.mutate(account.id)}
                    onStop={() => setConfirmStop(account.id)}
                    onRestart={() => restartRuntime.mutate(account.id)}
                    onCheckLogin={() => checkLogin.mutate(account.id)}
                    onOpenBrowser={() => openLiveBrowser(account.id)}
                    busy={connectAccount.isPending || restartRuntime.isPending || checkLogin.isPending || stopRuntime.isPending}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>

      <ConfirmModal
        open={confirmStop !== null}
        title="停止账号运行时"
        description="停止后该账号的所有扫描任务将暂停，直到手动重新启动。"
        confirmLabel="停止"
        destructive
        onConfirm={() => confirmStop && handleStop(confirmStop)}
        onCancel={() => setConfirmStop(null)}
      />
    </div>
  )
}

interface AccountActionProps {
  account: PlatformAccount
  onStart: () => void
  onStop: () => void
  onRestart: () => void
  onCheckLogin: () => void
  onOpenBrowser: () => void
  busy?: boolean
}

function AccountCard({ account, ...actions }: AccountActionProps) {
  const hasError = isRuntimeError(account.runtime_status) || !isLoginValid(account.login_status)

  return (
    <article className={`overflow-hidden rounded-2xl border bg-card shadow-sm transition-shadow hover:shadow-md ${hasError ? 'border-destructive/40' : ''}`}>
      {hasError && (
        <div className="flex items-center gap-2 border-b border-destructive/20 bg-destructive/10 px-5 py-2.5 text-xs font-medium text-destructive">
          <AlertTriangle className="h-3.5 w-3.5" />
          账号异常，需要重新登录
        </div>
      )}
      <div className="p-5">
        <div className="flex items-start justify-between gap-3">
          <AccountIdentity account={account} large />
          <StatusBadge status={account.connection_status} />
        </div>

        <dl className="mt-5 grid grid-cols-2 gap-x-5 gap-y-3 text-sm">
          <div>
            <dt className="text-xs text-muted-foreground">登录状态</dt>
            <dd className="mt-1"><LoginState status={account.login_status} /></dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">运行时</dt>
            <dd className="mt-1"><RuntimeState status={account.runtime_status} /></dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">CDP 端口</dt>
            <dd className="mt-1 font-mono text-xs text-foreground">{account.cdp_port ? `:${account.cdp_port}` : '—'}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted-foreground">配置文件</dt>
            <dd className="mt-1 text-xs text-foreground">{account.profile_status === 'expired' ? '会话过期' : '正常'}</dd>
          </div>
          <div className="col-span-2">
            <dt className="text-xs text-muted-foreground">最近检查</dt>
            <dd className="mt-1 text-xs text-foreground">{account.last_checked}</dd>
          </div>
        </dl>

        <AccountActions account={account} {...actions} />
      </div>
    </article>
  )
}

function AccountIdentity({ account, large = false }: { account: PlatformAccount; large?: boolean }) {
  return (
    <div className="flex min-w-0 items-center gap-3">
      <div
        className={`${large ? 'h-12 w-12 rounded-xl text-base' : 'h-8 w-8 rounded-lg text-xs'} flex shrink-0 items-center justify-center font-bold text-white`}
        style={{ background: account.color }}
      >
        {platformMark(account.platform)}
      </div>
      <div className="min-w-0">
        <div className={`${large ? 'text-base' : 'text-sm'} truncate font-semibold text-foreground`}>{account.display_name}</div>
        <div className="truncate text-xs text-muted-foreground">{account.handle}</div>
      </div>
    </div>
  )
}

function LoginState({ status }: { status: string }) {
  return isLoginValid(status) ? (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700">
      <CheckCircle className="h-3.5 w-3.5" /> 登录有效
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-destructive">
      <AlertTriangle className="h-3.5 w-3.5" /> 需要重新登录
    </span>
  )
}

function RuntimeState({ status }: { status: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${isRuntimeError(status) ? 'text-destructive' : isRunning(status) ? 'text-primary' : 'text-muted-foreground'}`}>
      <span className={`h-2 w-2 rounded-full ${isRuntimeError(status) ? 'bg-destructive' : isRunning(status) ? 'bg-primary' : 'bg-muted-foreground/60'}`} />
      {runtimeLabel(status)}
    </span>
  )
}

function AccountActions({ account, onStart, onStop, onRestart, onCheckLogin, onOpenBrowser, busy = false, compact = false }: AccountActionProps & { compact?: boolean }) {
  if (compact) {
    return (
      <div className="flex items-center gap-1">
        {isRunning(account.runtime_status) ? (
          <Button variant="ghost" size="icon-sm" title="停止" onClick={onStop} disabled={busy}><Square className="h-3.5 w-3.5" /></Button>
        ) : (
          <Button variant="ghost" size="icon-sm" title="启动" onClick={onStart} disabled={busy}><Play className="h-3.5 w-3.5" /></Button>
        )}
        <Button variant="ghost" size="icon-sm" title="打开浏览器" onClick={onOpenBrowser} disabled={busy}><ExternalLink className="h-3.5 w-3.5" /></Button>
        <Button variant="ghost" size="icon-sm" title="重启" onClick={onRestart} disabled={busy}><RotateCcw className="h-3.5 w-3.5" /></Button>
        {!isLoginValid(account.login_status) && (
          <Button variant="ghost" size="icon-sm" title="检查登录" onClick={onCheckLogin} disabled={busy}><LogIn className="h-3.5 w-3.5" /></Button>
        )}
      </div>
    )
  }

  return (
    <div className="mt-5 grid grid-cols-2 gap-2 border-t pt-4 sm:grid-cols-4">
      {isRunning(account.runtime_status) ? (
        <Button variant="outline" size="sm" onClick={onStop} disabled={busy}><Square className="h-3.5 w-3.5" />停止</Button>
      ) : (
        <Button variant="outline" size="sm" onClick={onStart} disabled={busy}><Play className="h-3.5 w-3.5" />启动</Button>
      )}
      <Button variant="outline" size="sm" onClick={onOpenBrowser} disabled={busy}><ExternalLink className="h-3.5 w-3.5" />打开浏览器</Button>
      <Button variant="outline" size="sm" onClick={onRestart} disabled={busy}><RotateCcw className="h-3.5 w-3.5" />重启</Button>
      <Button variant="outline" size="sm" onClick={onCheckLogin} disabled={busy}><LogIn className="h-3.5 w-3.5" />检查登录</Button>
    </div>
  )
}

function getNoVncUrl() {
  const configured = import.meta.env.VITE_NOVNC_URL
  if (configured) return configured
  return `${window.location.protocol}//${window.location.hostname}:6080/vnc.html?autoconnect=1&resize=scale`
}

function PlatformAccountsSkeleton() {
  return (
    <div className="min-h-full p-4 md:p-6">
      <div className="mx-auto flex max-w-[1440px] flex-col gap-5">
        <div className="flex items-start justify-between gap-3">
          <div><Skeleton className="h-8 w-32" /><Skeleton className="mt-2 h-4 w-72" /></div>
          <Skeleton className="h-10 w-72" />
        </div>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 2xl:grid-cols-3">
          {[0, 1, 2, 3, 4].map((item) => <Skeleton key={item} className="h-80 rounded-2xl" />)}
        </div>
      </div>
    </div>
  )
}
