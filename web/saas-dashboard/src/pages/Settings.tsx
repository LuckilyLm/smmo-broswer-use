import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Globe, Info, Monitor, Shield, SlidersHorizontal } from 'lucide-react'
import { useSettings, useUpdateSettings, type Settings as SettingsData, type UpdateSettingsInput } from '../api/settings'
import PageContainer from '../components/layout/PageContainer'
import ConfirmModal from '../components/ui/ConfirmModal'
import StickySaveBar, { type SaveState } from '../components/ui/StickySaveBar'
import { ErrorState } from '../components/ui/PageState'
import { Skeleton } from '@/components/ui/skeleton'

const sectionItems = [
  { id: 'tenant', label: '租户信息', icon: <Monitor className="h-4 w-4" /> },
  { id: 'contact', label: '默认联系方式', icon: <Globe className="h-4 w-4" /> },
  { id: 'policy', label: '默认业务策略', icon: <SlidersHorizontal className="h-4 w-4" /> },
  { id: 'send-switch', label: '回复安全开关', icon: <Shield className="h-4 w-4" /> },
] as const

type SectionId = typeof sectionItems[number]['id']

type EditableSettings = Pick<
  SettingsData,
  | 'tenant_name'
  | 'timezone'
  | 'default_target_policy'
  | 'default_min_confidence'
  | 'default_daily_limit'
  | 'default_whatsapp'
  | 'default_email'
  | 'default_website'
  | 'default_contact_text'
  | 'tenant_reply_enabled'
>

const inputClass = 'h-11 w-full rounded-lg border bg-card px-3 text-sm text-foreground outline-none transition placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-primary/15'

function editableSnapshot(settings: SettingsData): EditableSettings {
  return {
    tenant_name: settings.tenant_name,
    timezone: settings.timezone,
    default_target_policy: settings.default_target_policy,
    default_min_confidence: settings.default_min_confidence,
    default_daily_limit: settings.default_daily_limit,
    default_whatsapp: settings.default_whatsapp,
    default_email: settings.default_email,
    default_website: settings.default_website,
    default_contact_text: settings.default_contact_text,
    tenant_reply_enabled: settings.tenant_reply_enabled,
  }
}

export default function Settings() {
  const { data, isLoading, error, refetch } = useSettings()
  const updateSettings = useUpdateSettings()
  const [activeSection, setActiveSection] = useState<SectionId>('tenant')
  const [form, setForm] = useState<EditableSettings | null>(null)
  const [saved, setSaved] = useState<EditableSettings | null>(null)
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const [confirmOpen, setConfirmOpen] = useState(false)

  useEffect(() => {
    if (!data) return
    const snapshot = editableSnapshot(data)
    setForm(snapshot)
    setSaved(snapshot)
    setSaveState('idle')
  }, [data])

  const dirty = useMemo(() => Boolean(form && saved && JSON.stringify(form) !== JSON.stringify(saved)), [form, saved])

  const setField = <K extends keyof EditableSettings>(key: K, value: EditableSettings[K]) => {
    setForm((current) => current ? { ...current, [key]: value } : current)
    if (saveState !== 'idle') setSaveState('idle')
  }

  const scrollTo = (id: SectionId) => {
    setActiveSection(id)
    document.getElementById(`settings-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  const handleSave = async () => {
    if (!form || !saved || !dirty) return
    const changes = Object.fromEntries(
      (Object.keys(form) as Array<keyof EditableSettings>)
        .filter((key) => form[key] !== saved[key])
        .map((key) => [key, form[key]]),
    ) as UpdateSettingsInput

    setSaveState('saving')
    try {
      await updateSettings.mutateAsync(changes)
      setSaved(form)
      setSaveState('success')
      window.setTimeout(() => setSaveState('idle'), 1800)
    } catch {
      setSaveState('error')
    }
  }

  if (isLoading) return <SettingsSkeleton />
  if (error || !data || !form || !saved) {
    return <ErrorState description="无法加载租户设置，请检查网络后重试。" onRetry={() => refetch()} />
  }

  return (
    <div className="flex h-full min-h-0 overflow-hidden">
      <aside className="hidden h-full min-h-0 w-60 shrink-0 flex-col overflow-hidden border-r bg-card md:flex">
        <div className="shrink-0 border-b px-5 py-4">
          <h1 className="text-base font-semibold">设置</h1>
          <p className="mt-1 text-xs text-muted-foreground">管理租户默认值与安全策略</p>
        </div>
        <nav data-testid="settings-nav-scroll" data-scroll-region className="min-h-0 flex-1 overflow-y-auto p-2">
          {sectionItems.map((section) => (
            <button
              key={section.id}
              type="button"
              onClick={() => scrollTo(section.id)}
              className={`mb-1 flex min-h-11 w-full items-center gap-2.5 rounded-lg px-3 text-left text-sm transition ${activeSection === section.id ? 'bg-accent font-semibold text-primary' : 'text-muted-foreground hover:bg-muted hover:text-foreground'}`}
            >
              {section.icon}
              <span className="truncate">{section.label}</span>
            </button>
          ))}
        </nav>
      </aside>

      <section className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <div className="shrink-0 border-b bg-card px-4 py-2 md:hidden">
          <select className={inputClass} value={activeSection} onChange={(event) => scrollTo(event.target.value as SectionId)}>
            {sectionItems.map((section) => <option key={section.id} value={section.id}>{section.label}</option>)}
          </select>
        </div>

        <div data-testid="settings-content-scroll" data-scroll-region className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
          <PageContainer maxWidth="form" className="flex flex-col gap-10 pb-0 md:py-8">
            <header>
              <h1 className="text-2xl font-semibold tracking-tight">租户设置</h1>
              <p className="mt-1 text-sm text-muted-foreground">配置会作为新活动和自动化流程的默认值。</p>
            </header>

            <SettingsSection id="settings-tenant" title="租户信息" description="租户名称和默认时区。">
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <Field label="租户名称">
                  <input className={inputClass} value={form.tenant_name} onChange={(event) => setField('tenant_name', event.target.value)} />
                </Field>
                <Field label="租户 ID">
                  <input className={`${inputClass} cursor-not-allowed bg-muted text-muted-foreground`} value={data.tenant_id} readOnly />
                </Field>
                <Field label="时区" className="md:col-span-2">
                  <select className={inputClass} value={form.timezone} onChange={(event) => setField('timezone', event.target.value)}>
                    <option value="Asia/Shanghai">Asia/Shanghai (UTC+8)</option>
                    <option value="UTC">UTC</option>
                    <option value="America/New_York">America/New_York</option>
                    <option value="Europe/London">Europe/London</option>
                  </select>
                </Field>
              </div>
            </SettingsSection>

            <SettingsSection id="settings-contact" title="默认联系方式" description="新建活动时自动带入，活动仍可单独覆盖。">
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <Field label="WhatsApp"><input className={inputClass} value={form.default_whatsapp} onChange={(event) => setField('default_whatsapp', event.target.value)} /></Field>
                <Field label="Email"><input type="email" className={inputClass} value={form.default_email} onChange={(event) => setField('default_email', event.target.value)} /></Field>
                <Field label="官网"><input type="url" className={inputClass} value={form.default_website} onChange={(event) => setField('default_website', event.target.value)} /></Field>
                <Field label="联系文本"><input className={inputClass} value={form.default_contact_text} onChange={(event) => setField('default_contact_text', event.target.value)} /></Field>
              </div>
            </SettingsSection>

            <SettingsSection id="settings-policy" title="默认业务策略" description="控制新活动的发现范围和默认限额。">
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <Field label="目标策略" className="md:col-span-2">
                  <select className={inputClass} value={form.default_target_policy} onChange={(event) => setField('default_target_policy', event.target.value as EditableSettings['default_target_policy'])}>
                    <option value="discovery_only">仅发现线索</option>
                    <option value="owned_only">仅自有内容</option>
                    <option value="allowlist">白名单内容</option>
                  </select>
                </Field>
                <Field label="最低置信度">
                  <input type="number" min="0" max="1" step="0.05" className={inputClass} value={form.default_min_confidence} onChange={(event) => setField('default_min_confidence', Number(event.target.value))} />
                </Field>
                <Field label="每日上限">
                  <input type="number" min="1" max="10000" className={inputClass} value={form.default_daily_limit} onChange={(event) => setField('default_daily_limit', Number(event.target.value))} />
                </Field>
              </div>
            </SettingsSection>

            <SettingsSection id="settings-send-switch" title="回复安全开关" description="租户开关受系统级发送开关共同约束。">
              <div className={`rounded-xl border p-4 ${data.system_send_enabled ? 'border-border bg-card' : 'border-amber-300 bg-amber-50'}`}>
                <div className="flex items-start gap-3">
                  <AlertTriangle className={`mt-0.5 h-5 w-5 shrink-0 ${data.system_send_enabled ? 'text-muted-foreground' : 'text-amber-600'}`} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold">系统级发送：{data.system_send_enabled ? '已开启' : '已关闭'}</p>
                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{data.reply_safety_message || '系统允许发送，但仍需租户和活动级开关同时开启。'}</p>
                  </div>
                </div>
              </div>
              <label className="flex min-h-14 items-center justify-between gap-4 rounded-xl border bg-card px-4 py-3">
                <span className="min-w-0">
                  <span className="block text-sm font-medium">允许租户回复</span>
                  <span className="mt-0.5 block text-xs text-muted-foreground">关闭后，本租户不会向平台发送真实回复。</span>
                </span>
                <button
                  type="button"
                  role="switch"
                  aria-checked={form.tenant_reply_enabled}
                  className={`relative h-7 w-12 shrink-0 rounded-full transition ${form.tenant_reply_enabled ? 'bg-primary' : 'bg-muted-foreground/35'}`}
                  onClick={() => form.tenant_reply_enabled ? setField('tenant_reply_enabled', false) : setConfirmOpen(true)}
                >
                  <span className={`absolute top-1 h-5 w-5 rounded-full bg-white shadow transition ${form.tenant_reply_enabled ? 'left-6' : 'left-1'}`} />
                </button>
              </label>
              {!data.system_send_enabled && (
                <p className="flex items-start gap-2 text-xs text-muted-foreground"><Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />即使开启租户开关，系统级发送关闭时仍不会发送真实回复。</p>
              )}
            </SettingsSection>
          </PageContainer>

          <StickySaveBar
            dirty={dirty}
            state={saveState}
            onCancel={() => { setForm(saved); setSaveState('idle') }}
            onSave={handleSave}
            className="mx-auto max-w-[960px]"
          />
        </div>
      </section>

      <ConfirmModal
        open={confirmOpen}
        title="确认允许租户回复"
        description="开启后，如果系统级开关和活动级回复模式也允许，已审批回复可能发送到真实平台。"
        confirmLabel="确认开启"
        cancelLabel="取消"
        destructive
        onConfirm={() => { setField('tenant_reply_enabled', true); setConfirmOpen(false) }}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  )
}

function SettingsSection({ id, title, description, children }: { id: string; title: string; description: string; children: React.ReactNode }) {
  return (
    <section id={id} className="scroll-mt-4">
      <div className="mb-5 border-b pb-3">
        <h2 className="text-base font-semibold">{title}</h2>
        <p className="mt-1 text-xs text-muted-foreground">{description}</p>
      </div>
      <div className="flex flex-col gap-4">{children}</div>
    </section>
  )
}

function Field({ label, children, className = '' }: { label: string; children: React.ReactNode; className?: string }) {
  return <label className={`flex min-w-0 flex-col gap-1.5 ${className}`}><span className="text-sm font-medium">{label}</span>{children}</label>
}

function SettingsSkeleton() {
  return (
    <div className="flex h-full min-h-0">
      <Skeleton className="hidden h-full w-60 rounded-none md:block" />
      <PageContainer maxWidth="form" className="flex flex-1 flex-col gap-8 md:py-8">
        <Skeleton className="h-16 w-72" />
        {[0, 1, 2, 3].map((item) => <Skeleton key={item} className="h-52 w-full" />)}
      </PageContainer>
    </div>
  )
}
