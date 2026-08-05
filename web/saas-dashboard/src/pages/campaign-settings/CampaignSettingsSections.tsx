import { cloneElement, isValidElement, useId } from 'react'
import { AlertTriangle, Plus, Trash2 } from 'lucide-react'
import type { CampaignTargetPolicy } from '../../api/campaigns'
import type { PlatformAccount } from '../../api/platform-accounts'
import type { ReplyTemplate } from '../../api/reply-templates'

export interface CampaignSettingsFormValues {
  name: string
  description: string
  region: string
  whatsapp: string
  email: string
  website: string
  contact: string
  dailyLimit: string
  hourlyLimit: string
  minuteLimit: string
  intervalSecs: string
}

interface CampaignSettingsSectionsProps {
  formValues: CampaignSettingsFormValues
  errors: Record<string, string>
  platformAccounts: PlatformAccount[]
  selectedAccountId: string
  keywords: Array<{ id: number; value: string }>
  targetPolicy: CampaignTargetPolicy
  leadMode: 'rules' | 'hybrid' | 'ai'
  replyMode: 'off' | 'manual' | 'auto'
  preflightWarnings: string[]
  templates: ReplyTemplate[]
  selectedTemplateId: string
  llmEnabled: boolean
  onFieldChange: (key: keyof CampaignSettingsFormValues, value: string) => void
  onAccountChange: (value: string) => void
  onKeywordsChange: (value: Array<{ id: number; value: string }>) => void
  onAddKeyword: () => void
  onTargetPolicyChange: (value: CampaignTargetPolicy) => void
  onLeadModeChange: (value: 'rules' | 'hybrid' | 'ai') => void
  onReplyModeChange: (value: 'off' | 'manual' | 'auto') => void
  onTemplateChange: (value: string) => void
  onLlmEnabledChange: (value: boolean) => void
  onMarkChanged: () => void
}

const targetPolicyOptions: Array<{ value: CampaignTargetPolicy; label: string; description: string }> = [
  { value: 'discovery_only', label: '仅发现', description: '只收集和识别线索，不允许发送回复' },
  { value: 'owned_only', label: '仅自有来源', description: '仅允许回复归属当前账号的内容' },
  { value: 'allowlist', label: '白名单来源', description: '仅允许回复运行环境白名单中的来源' },
]

export default function CampaignSettingsSections(props: CampaignSettingsSectionsProps) {
  const {
    formValues, errors, platformAccounts, selectedAccountId, keywords, targetPolicy, leadMode,
    replyMode, preflightWarnings, templates, selectedTemplateId, llmEnabled, onFieldChange,
    onAccountChange, onKeywordsChange, onAddKeyword, onTargetPolicyChange, onLeadModeChange,
    onReplyModeChange, onTemplateChange, onLlmEnabledChange, onMarkChanged,
  } = props

  return (
    <>
      <Section id="basic" title="基础信息">
        <Field label="活动名称" required error={errors.name}>
          <input type="text" value={formValues.name} onChange={(event) => onFieldChange('name', event.target.value)} className={inputClass(Boolean(errors.name))} />
        </Field>
        <Field label="活动描述">
          <textarea rows={3} value={formValues.description} onChange={(event) => onFieldChange('description', event.target.value)} className={inputClass(false)} />
        </Field>
        <Field label="目标地区">
          <input type="text" value={formValues.region} onChange={(event) => onFieldChange('region', event.target.value)} className={inputClass(false)} />
        </Field>
      </Section>

      <Section id="account" title="平台账号">
        <Field label="目标平台">
          <select className={inputClass(false)} onChange={onMarkChanged}>
            {['Facebook', 'Instagram', 'TikTok', 'X', 'YouTube'].map((platform) => <option key={platform}>{platform}</option>)}
          </select>
        </Field>
        <Field label="绑定账号" required error={errors.account}>
          <select className={inputClass(Boolean(errors.account))} value={selectedAccountId} onChange={(event) => onAccountChange(event.target.value)}>
            {platformAccounts.length === 0 && <option value="">暂无平台账号</option>}
            {platformAccounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.display_name}（{account.platform} · {account.login_status === 'logged_in' ? '已登录' : account.login_status === 'login_required' ? '需要登录' : '登录状态未知'} · {account.runtime_status === 'running' ? '运行中' : account.runtime_status === 'starting' ? '启动中' : account.runtime_status === 'unhealthy' ? '运行异常' : '已停止'}）
              </option>
            ))}
          </select>
        </Field>
      </Section>

      <Section id="keywords" title="搜索关键词">
        <Field label="关键词列表" hint="每行一个，系统将在目标平台搜索包含这些关键词的内容" error={errors.keywords}>
          <div className="flex flex-col gap-2">
            {keywords.map((keyword) => (
              <div key={keyword.id} className="flex items-center gap-2">
                <input
                  type="text"
                  aria-label="关键词"
                  value={keyword.value}
                  onChange={(event) => onKeywordsChange(keywords.map((item) => item.id === keyword.id ? { ...item, value: event.target.value } : item))}
                  className={`${inputClass(false)} flex-1`}
                />
                <button type="button" aria-label={`删除关键词 ${keyword.value || '空白项'}`} className="p-2 text-gray-400 hover:text-red-400" style={{ minHeight: 44, minWidth: 44 }} onClick={() => onKeywordsChange(keywords.filter((item) => item.id !== keyword.id))}>
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
            <button type="button" className="flex w-fit items-center gap-1.5 rounded-lg border px-3 py-2 text-sm hover:bg-gray-50" style={{ borderColor: 'var(--border)', color: 'var(--primary)', minHeight: 44 }} onClick={onAddKeyword}>
              <Plus size={13} /> 添加关键词
            </button>
          </div>
        </Field>
      </Section>

      <Section id="strategy" title="目标内容策略">
        <Field label="来源回复策略" hint="决定哪些来源可发送回复；此设置会随活动保存。">
          <div className="grid gap-2 md:grid-cols-3">
            {targetPolicyOptions.map((option) => (
              <label key={option.value} className="cursor-pointer rounded-lg border p-3" style={{ borderColor: targetPolicy === option.value ? 'var(--primary)' : 'var(--border)', background: targetPolicy === option.value ? 'var(--accent)' : 'white' }}>
                <div className="flex items-center gap-2 text-sm font-medium text-gray-800">
                  <input type="radio" name="targetPolicy" value={option.value} checked={targetPolicy === option.value} onChange={() => onTargetPolicyChange(option.value)} />
                  {option.label}
                </div>
                <p className="mt-1 text-xs text-gray-500">{option.description}</p>
              </label>
            ))}
          </div>
          {(targetPolicy === 'owned_only' || targetPolicy === 'allowlist') && (
            <div className="mt-2 rounded-lg border border-blue-200 bg-blue-50 p-3 text-xs text-blue-700">
              当前活动数据模型只持久化来源策略，不包含自有来源 ID 或白名单 URL 字段。请在运行环境中配置对应来源清单；本页面不会创建或伪造这些字段。
            </div>
          )}
        </Field>
        <Field label="扫描内容类型">
          <div className="flex flex-col gap-2">
            {['帖子评论', '视频评论', '话题讨论', '产品评测'].map((type) => (
              <label key={type} className="flex cursor-pointer items-center gap-2 text-sm text-gray-700" style={{ minHeight: 44 }}>
                <input type="checkbox" defaultChecked className="rounded" onChange={onMarkChanged} />
                {type}
              </label>
            ))}
          </div>
        </Field>
        <Field label="内容语言">
          <div className="flex flex-wrap gap-4">
            {['中文', '英文', '不限'].map((language) => (
              <label key={language} className="flex cursor-pointer items-center gap-1.5 text-sm text-gray-700" style={{ minHeight: 44 }}>
                <input type="radio" name="lang" defaultChecked={language === '不限'} onChange={onMarkChanged} />
                {language}
              </label>
            ))}
          </div>
        </Field>
      </Section>

      <Section id="leads" title="线索识别">
        <Field label="意向识别模式">
          <div className="flex flex-col gap-2">
            {[
              { value: 'rules', label: '仅使用规则', desc: '通过关键词和匹配规则识别潜在线索，速度快、可预期' },
              { value: 'hybrid', label: '规则匹配后使用 AI 复核', desc: '先用规则过滤，再由 AI 判断意向强度' },
              { value: 'ai', label: '仅使用 AI', desc: '完全依赖 LLM 判断，需要消耗较多 Token' },
            ].map((option) => (
              <label key={option.value} className="flex cursor-pointer items-start gap-3 rounded-lg border p-3 transition-colors" style={{ borderColor: leadMode === option.value ? 'var(--primary)' : 'var(--border)', background: leadMode === option.value ? 'var(--accent)' : 'white', minHeight: 44 }}>
                <input type="radio" name="leadMode" value={option.value} checked={leadMode === option.value} onChange={() => onLeadModeChange(option.value as 'rules' | 'hybrid' | 'ai')} className="mt-0.5" />
                <div><div className="text-sm font-medium text-gray-800">{option.label}</div><div className="mt-0.5 text-xs text-gray-500">{option.desc}</div></div>
              </label>
            ))}
          </div>
        </Field>
      </Section>

      <Section id="reply" title="回复自动化">
        <Field label="回复模式">
          <div className="flex w-full overflow-hidden rounded-lg border md:w-fit" style={{ borderColor: 'var(--border)' }}>
            {[
              { value: 'off', label: '关闭' },
              { value: 'manual', label: '人工审批' },
              { value: 'auto', label: '自动执行' },
            ].map((option, index, items) => (
              <button type="button" key={option.value} onClick={() => onReplyModeChange(option.value as 'off' | 'manual' | 'auto')} className="flex flex-1 items-center justify-center gap-1.5 px-3 py-2.5 text-sm font-medium transition-colors md:flex-none md:px-4" style={{ background: replyMode === option.value ? (option.value === 'auto' ? '#fef3c7' : 'var(--primary)') : 'white', color: replyMode === option.value ? (option.value === 'auto' ? '#d97706' : 'white') : '#374151', borderRight: index < items.length - 1 ? '1px solid var(--border)' : 'none', minHeight: 44 }}>
                {option.value === 'auto' && <AlertTriangle size={12} />}{option.label}
              </button>
            ))}
          </div>
          {replyMode === 'auto' && <div className="mt-2 flex items-start gap-2 rounded-lg border p-3" style={{ background: '#fffbeb', borderColor: '#fcd34d' }}><AlertTriangle size={14} className="mt-0.5 shrink-0 text-amber-500" /><div className="text-xs text-amber-700">自动执行模式将在系统级发送开关开启时直接发送回复，无需人工审批。请谨慎使用。</div></div>}
          {preflightWarnings.length > 0 && <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-3"><div className="flex items-center gap-1.5 text-xs font-semibold text-amber-800"><AlertTriangle size={13} />回复预检提示</div><ul className="mt-1.5 list-disc space-y-1 pl-5 text-xs text-amber-700">{preflightWarnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>}
        </Field>
        <Field label="默认回复模板">
          <select className={inputClass(false)} value={selectedTemplateId} onChange={(event) => onTemplateChange(event.target.value)}><option value="">不绑定模板</option>{templates.map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}</select>
        </Field>
        <Field label="可选 LLM 增强" hint="使用 AI 优化回复内容的语气和相关性，默认关闭">
          <div className="flex items-center gap-2" style={{ minHeight: 44 }}>
            <button type="button" role="switch" aria-checked={llmEnabled} aria-label="启用 AI 增强回复" className="relative h-5 w-9 rounded-full transition-colors" style={{ background: llmEnabled ? 'var(--primary)' : '#d1d5db' }} onClick={() => onLlmEnabledChange(!llmEnabled)}><span className="absolute top-0.5 h-4 w-4 rounded-full bg-white transition-[left]" style={{ left: llmEnabled ? 20 : 2 }} /></button>
            <span className="text-sm text-gray-700">启用 AI 增强回复</span>{llmEnabled && <span className="text-xs text-amber-600">将消耗 LLM Token</span>}
          </div>
        </Field>
      </Section>

      <Section id="contact" title="联系方式">
        <p className="-mt-2 text-xs text-gray-500">这些值将替换回复模板中的变量，如 {'{{whatsapp}}'}  </p>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Field label="WhatsApp"><input type="text" value={formValues.whatsapp} onChange={(event) => onFieldChange('whatsapp', event.target.value)} className={inputClass(false)} /></Field>
          <Field label="Email" error={errors.email}><input type="text" value={formValues.email} onChange={(event) => onFieldChange('email', event.target.value)} className={inputClass(Boolean(errors.email))} /></Field>
          <Field label="官网地址"><input type="text" value={formValues.website} onChange={(event) => onFieldChange('website', event.target.value)} className={inputClass(false)} /></Field>
          <Field label="联系文本"><input type="text" value={formValues.contact} onChange={(event) => onFieldChange('contact', event.target.value)} className={inputClass(false)} /></Field>
        </div>
        <div className="mt-2 rounded-lg border bg-gray-50 p-3" style={{ borderColor: 'var(--border)' }}><div className="mb-2 text-xs font-medium text-gray-600">可用模板变量</div><div className="flex flex-wrap gap-1.5">{['{{whatsapp}}', '{{email}}', '{{website}}', '{{contact}}', '{{campaign_name}}', '{{keyword}}', '{{author_name}}'].map((variable) => <span key={variable} className="rounded border bg-white px-2 py-0.5 font-mono text-xs text-indigo-600" style={{ borderColor: 'var(--border)' }}>{variable}</span>)}</div></div>
      </Section>

      <Section id="rate" title="速率限制"><div className="grid grid-cols-2 gap-4">
        <Field label="每日回复上限"><input type="number" value={formValues.dailyLimit} onChange={(event) => onFieldChange('dailyLimit', event.target.value)} min={1} className={inputClass(false)} /></Field>
        <Field label="每小时上限"><input type="number" value={formValues.hourlyLimit} onChange={(event) => onFieldChange('hourlyLimit', event.target.value)} min={1} className={inputClass(false)} /></Field>
        <Field label="每分钟上限"><input type="number" value={formValues.minuteLimit} onChange={(event) => onFieldChange('minuteLimit', event.target.value)} min={1} className={inputClass(false)} /></Field>
        <Field label="最小间隔（秒）"><input type="number" value={formValues.intervalSecs} onChange={(event) => onFieldChange('intervalSecs', event.target.value)} min={5} className={inputClass(false)} /></Field>
      </div></Section>

      <Section id="schedule" title="调度设置">
        <Field label="执行频率"><select className={inputClass(false)} onChange={onMarkChanged}><option>每小时</option><option>每 2 小时</option><option>每 4 小时</option><option>每天一次</option><option>手动触发</option></select></Field>
        <Field label="执行时间段" hint="仅在指定时间段内执行"><div className="flex flex-wrap items-center gap-3"><input type="time" defaultValue="09:00" className={`${inputClass(false)} w-full md:w-32`} onChange={onMarkChanged} /><span className="hidden text-sm text-gray-400 md:block">至</span><input type="time" defaultValue="22:00" className={`${inputClass(false)} w-full md:w-32`} onChange={onMarkChanged} /></div></Field>
        <Field label="时区"><select className={inputClass(false)} onChange={onMarkChanged}><option>Asia/Shanghai (UTC+8)</option><option>America/New_York (UTC-5)</option></select></Field>
      </Section>
    </>
  )
}

function inputClass(hasError: boolean) {
  return `w-full px-3 py-2.5 text-sm border rounded-lg bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500 ${hasError ? 'border-red-400' : ''}`
}

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return <div id={id} className="flex scroll-mt-24 flex-col gap-4 md:scroll-mt-6"><div className="border-b pb-2" style={{ borderColor: 'var(--border)' }}><h2 className="text-base font-semibold text-gray-900">{title}</h2></div>{children}</div>
}

function Field({ label, children, required, hint, error }: { label: string; children: React.ReactNode; required?: boolean; hint?: string; error?: string }) {
  const id = useId()
  const control = isValidElement<{ id?: string; 'aria-describedby'?: string }>(children) ? cloneElement(children, { id: children.props.id || id, 'aria-describedby': error ? `${id}-error` : children.props['aria-describedby'] }) : children
  return <div className="flex flex-col gap-1.5"><label htmlFor={id} className="text-sm font-medium text-gray-700">{label}{required && <span className="ml-0.5 text-red-500">*</span>}</label>{hint && <p className="text-xs text-gray-400">{hint}</p>}{control}{error && <p id={`${id}-error`} className="flex items-center gap-1 text-xs text-red-500"><AlertTriangle size={11} />{error}</p>}</div>
}
