import { useState } from 'react'
import { Save, X, AlertTriangle, ChevronRight, Info, Plus, Trash2, CheckCircle, Loader2 } from 'lucide-react'
import TopBar from '../components/layout/TopBar'

const sections = [
  { id: 'basic', label: '基础信息' },
  { id: 'account', label: '平台账号' },
  { id: 'keywords', label: '搜索关键词' },
  { id: 'strategy', label: '目标内容策略' },
  { id: 'leads', label: '线索识别' },
  { id: 'reply', label: '回复自动化' },
  { id: 'contact', label: '联系方式' },
  { id: 'rate', label: '速率限制' },
  { id: 'schedule', label: '调度设置' },
]

type SaveState = 'idle' | 'saving' | 'success' | 'error'

interface CampaignSettingsProps {
  onNavigate: (page: string) => void
  onMenuOpen?: () => void
}

export default function CampaignSettings({ onNavigate, onMenuOpen }: CampaignSettingsProps) {
  const [activeSection, setActiveSection] = useState('basic')
  const [replyMode, setReplyMode] = useState<'off' | 'manual' | 'auto'>('manual')
  const [leadMode, setLeadMode] = useState<'rules' | 'hybrid' | 'ai'>('rules')
  const [llmEnabled, setLlmEnabled] = useState(false)
  const [hasChanges, setHasChanges] = useState(true)
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const [keywords, setKeywords] = useState(['跨境电商', '独立站', '代购', '海淘', '采购'])
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [navOpen, setNavOpen] = useState(false)

  const [formValues, setFormValues] = useState({
    name: '跨境电商引流 – Facebook',
    description: '针对 Facebook 跨境电商兴趣用户，通过关键词匹配挖掘潜在买家。',
    region: '东南亚、欧美',
    whatsapp: '+86 138 xxxx xxxx',
    email: 'sales@company.com',
    website: 'https://www.company.com',
    contact: '欢迎添加微信咨询',
    dailyLimit: '50',
    hourlyLimit: '10',
    minuteLimit: '2',
    intervalSecs: '30',
  })

  const setField = (key: string, value: string) => {
    setFormValues((prev) => ({ ...prev, [key]: value }))
    setHasChanges(true)
    if (errors[key]) setErrors((prev) => { const e = { ...prev }; delete e[key]; return e })
  }

  const validate = () => {
    const e: Record<string, string> = {}
    if (!formValues.name.trim()) e.name = '活动名称不能为空'
    if (keywords.length === 0) e.keywords = '至少需要一个关键词'
    if (formValues.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formValues.email)) e.email = '邮箱格式不正确'
    return e
  }

  const handleSave = async () => {
    const e = validate()
    if (Object.keys(e).length > 0) { setErrors(e); return }
    setSaveState('saving')
    await new Promise((r) => setTimeout(r, 1200))
    // Simulate occasional error
    if (Math.random() < 0.15) {
      setSaveState('error')
      setTimeout(() => setSaveState('idle'), 3000)
      return
    }
    setSaveState('success')
    setHasChanges(false)
    setTimeout(() => setSaveState('idle'), 2000)
  }

  const scrollTo = (id: string) => {
    setActiveSection(id)
    setNavOpen(false)
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div className="flex flex-col min-h-screen">
      <TopBar breadcrumbs={['获客管理', '营销活动', '活动设置']} pageTitle="活动设置" onMenuOpen={onMenuOpen} />
      <div className="flex-1 flex" style={{ minHeight: 0 }}>
        {/* Desktop section nav */}
        <nav className="hidden md:flex flex-col w-48 shrink-0 border-r bg-white py-4 px-2 sticky overflow-y-auto" style={{ borderColor: 'var(--border)', top: 52, height: 'calc(100vh - 52px)' }}>
          {sections.map((s) => (
            <button
              key={s.id}
              onClick={() => scrollTo(s.id)}
              className="flex items-center gap-2 px-3 py-2 text-sm rounded-lg mb-0.5 transition-colors text-left"
              style={{
                color: activeSection === s.id ? 'var(--primary)' : '#374151',
                background: activeSection === s.id ? 'var(--accent)' : 'transparent',
                fontWeight: activeSection === s.id ? 600 : 400,
              }}
            >
              <ChevronRight size={12} style={{ color: activeSection === s.id ? 'var(--primary)' : '#d1d5db' }} />
              {s.label}
            </button>
          ))}
        </nav>

        {/* Mobile section nav: select */}
        <div className="md:hidden w-full sticky top-[52px] z-20 bg-white border-b px-4 py-2" style={{ borderColor: 'var(--border)' }}>
          <select
            value={activeSection}
            onChange={(e) => scrollTo(e.target.value)}
            className="w-full px-3 py-2 text-sm border rounded-lg bg-white focus:outline-none"
            style={{ borderColor: 'var(--border)', minHeight: 40 }}
          >
            {sections.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </div>

        {/* Form content */}
        <div className="flex-1 overflow-y-auto pb-28">
          <div className="max-w-3xl mx-auto p-4 md:p-8 flex flex-col gap-6 md:gap-8">

            <Section id="basic" title="基础信息">
              <Field label="活动名称" required error={errors.name}>
                <input type="text" value={formValues.name} onChange={(e) => setField('name', e.target.value)} className={`${inputClass(!!errors.name)}`} />
              </Field>
              <Field label="活动描述">
                <textarea rows={3} value={formValues.description} onChange={(e) => setField('description', e.target.value)} className={inputClass(false)} />
              </Field>
              <Field label="目标地区">
                <input type="text" value={formValues.region} onChange={(e) => setField('region', e.target.value)} className={inputClass(false)} />
              </Field>
            </Section>

            <Section id="account" title="平台账号">
              <Field label="目标平台">
                <select className={inputClass(false)} onChange={() => setHasChanges(true)}>
                  {['Facebook', 'Instagram', 'TikTok', 'X', 'YouTube'].map((p) => <option key={p}>{p}</option>)}
                </select>
              </Field>
              <Field label="绑定账号">
                <select className={inputClass(false)} onChange={() => setHasChanges(true)}>
                  <option>@smmo_business（Facebook · 登录有效）</option>
                  <option>@smmo_official（Instagram · 登录有效）</option>
                </select>
              </Field>
            </Section>

            <Section id="keywords" title="搜索关键词">
              <Field label="关键词列表" hint="每行一个，系统将在目标平台搜索包含这些关键词的内容" error={errors.keywords}>
                <div className="flex flex-col gap-2">
                  {keywords.map((kw, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <input
                        type="text"
                        value={kw}
                        onChange={(e) => { const k = [...keywords]; k[i] = e.target.value; setKeywords(k); setHasChanges(true) }}
                        className={`${inputClass(false)} flex-1`}
                      />
                      <button className="p-2 text-gray-400 hover:text-red-400" style={{ minHeight: 44, minWidth: 44 }} onClick={() => { setKeywords(keywords.filter((_, j) => j !== i)); setHasChanges(true) }}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))}
                  <button
                    className="flex items-center gap-1.5 text-sm px-3 py-2 border rounded-lg hover:bg-gray-50 w-fit"
                    style={{ borderColor: 'var(--border)', color: 'var(--primary)', minHeight: 44 }}
                    onClick={() => { setKeywords([...keywords, '']); setHasChanges(true) }}
                  >
                    <Plus size={13} /> 添加关键词
                  </button>
                </div>
              </Field>
            </Section>

            <Section id="strategy" title="目标内容策略">
              <Field label="扫描内容类型">
                <div className="flex flex-col gap-2">
                  {['帖子评论', '视频评论', '话题讨论', '产品评测'].map((t) => (
                    <label key={t} className="flex items-center gap-2 cursor-pointer text-sm text-gray-700" style={{ minHeight: 44 }}>
                      <input type="checkbox" defaultChecked className="rounded" onChange={() => setHasChanges(true)} />
                      {t}
                    </label>
                  ))}
                </div>
              </Field>
              <Field label="内容语言">
                <div className="flex flex-wrap gap-4">
                  {['中文', '英文', '不限'].map((l) => (
                    <label key={l} className="flex items-center gap-1.5 text-sm text-gray-700 cursor-pointer" style={{ minHeight: 44 }}>
                      <input type="radio" name="lang" defaultChecked={l === '不限'} onChange={() => setHasChanges(true)} />
                      {l}
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
                  ].map((opt) => (
                    <label
                      key={opt.value}
                      className="flex items-start gap-3 p-3 border rounded-lg cursor-pointer transition-colors"
                      style={{
                        borderColor: leadMode === opt.value ? 'var(--primary)' : 'var(--border)',
                        background: leadMode === opt.value ? 'var(--accent)' : 'white',
                        minHeight: 44,
                      }}
                    >
                      <input type="radio" name="leadMode" value={opt.value} checked={leadMode === opt.value} onChange={() => { setLeadMode(opt.value as typeof leadMode); setHasChanges(true) }} className="mt-0.5" />
                      <div>
                        <div className="text-sm font-medium text-gray-800">{opt.label}</div>
                        <div className="text-xs text-gray-500 mt-0.5">{opt.desc}</div>
                      </div>
                    </label>
                  ))}
                </div>
              </Field>
            </Section>

            <Section id="reply" title="回复自动化">
              <Field label="回复模式">
                <div className="flex rounded-lg border overflow-hidden w-full md:w-fit" style={{ borderColor: 'var(--border)' }}>
                  {[
                    { value: 'off', label: '关闭' },
                    { value: 'manual', label: '人工审批' },
                    { value: 'auto', label: '自动执行' },
                  ].map((opt, i, arr) => (
                    <button
                      key={opt.value}
                      onClick={() => { setReplyMode(opt.value as typeof replyMode); setHasChanges(true) }}
                      className="flex-1 md:flex-none px-3 md:px-4 py-2.5 text-sm font-medium transition-colors flex items-center justify-center gap-1.5"
                      style={{
                        background: replyMode === opt.value ? (opt.value === 'auto' ? '#fef3c7' : 'var(--primary)') : 'white',
                        color: replyMode === opt.value ? (opt.value === 'auto' ? '#d97706' : 'white') : '#374151',
                        borderRight: i < arr.length - 1 ? '1px solid var(--border)' : 'none',
                        minHeight: 44,
                      }}
                    >
                      {opt.value === 'auto' && <AlertTriangle size={12} />}
                      {opt.label}
                    </button>
                  ))}
                </div>
                {replyMode === 'auto' && (
                  <div className="mt-2 flex items-start gap-2 p-3 rounded-lg border" style={{ background: '#fffbeb', borderColor: '#fcd34d' }}>
                    <AlertTriangle size={14} className="text-amber-500 shrink-0 mt-0.5" />
                    <div className="text-xs text-amber-700">自动执行模式将在系统级发送开关开启时直接发送回复，无需人工审批。请谨慎使用。</div>
                  </div>
                )}
              </Field>
              <Field label="默认回复模板">
                <select className={inputClass(false)} onChange={() => setHasChanges(true)}>
                  <option>标准获客模板（中文）</option>
                  <option>海外通用模板（英文）</option>
                </select>
              </Field>
              <Field label="可选 LLM 增强" hint="使用 AI 优化回复内容的语气和相关性，默认关闭">
                <label className="flex items-center gap-2 cursor-pointer" style={{ minHeight: 44 }}>
                  <div
                    className="w-9 h-5 rounded-full relative transition-colors"
                    style={{ background: llmEnabled ? 'var(--primary)' : '#d1d5db' }}
                    onClick={() => { setLlmEnabled(!llmEnabled); setHasChanges(true) }}
                  >
                    <div className="absolute top-0.5 w-4 h-4 rounded-full bg-white transition-all" style={{ left: llmEnabled ? 20 : 2 }} />
                  </div>
                  <span className="text-sm text-gray-700">启用 AI 增强回复</span>
                  {llmEnabled && <span className="text-xs text-amber-600">将消耗 LLM Token</span>}
                </label>
              </Field>
            </Section>

            <Section id="contact" title="联系方式">
              <p className="text-xs text-gray-500 -mt-2">这些值将替换回复模板中的变量，如 {'{{whatsapp}}'}  </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Field label="WhatsApp"><input type="text" value={formValues.whatsapp} onChange={(e) => setField('whatsapp', e.target.value)} className={inputClass(false)} /></Field>
                <Field label="Email" error={errors.email}>
                  <input type="text" value={formValues.email} onChange={(e) => setField('email', e.target.value)} className={inputClass(!!errors.email)} />
                </Field>
                <Field label="官网地址"><input type="text" value={formValues.website} onChange={(e) => setField('website', e.target.value)} className={inputClass(false)} /></Field>
                <Field label="联系文本"><input type="text" value={formValues.contact} onChange={(e) => setField('contact', e.target.value)} className={inputClass(false)} /></Field>
              </div>
              <div className="mt-2 p-3 rounded-lg bg-gray-50 border" style={{ borderColor: 'var(--border)' }}>
                <div className="text-xs font-medium text-gray-600 mb-2">可用模板变量</div>
                <div className="flex flex-wrap gap-1.5">
                  {['{{whatsapp}}', '{{email}}', '{{website}}', '{{contact}}', '{{campaign_name}}', '{{keyword}}', '{{author_name}}'].map((v) => (
                    <span key={v} className="px-2 py-0.5 bg-white border rounded text-xs font-mono text-indigo-600" style={{ borderColor: 'var(--border)' }}>{v}</span>
                  ))}
                </div>
              </div>
            </Section>

            <Section id="rate" title="速率限制">
              <div className="grid grid-cols-2 gap-4">
                <Field label="每日回复上限"><input type="number" value={formValues.dailyLimit} onChange={(e) => setField('dailyLimit', e.target.value)} min={1} className={inputClass(false)} /></Field>
                <Field label="每小时上限"><input type="number" value={formValues.hourlyLimit} onChange={(e) => setField('hourlyLimit', e.target.value)} min={1} className={inputClass(false)} /></Field>
                <Field label="每分钟上限"><input type="number" value={formValues.minuteLimit} onChange={(e) => setField('minuteLimit', e.target.value)} min={1} className={inputClass(false)} /></Field>
                <Field label="最小间隔（秒）"><input type="number" value={formValues.intervalSecs} onChange={(e) => setField('intervalSecs', e.target.value)} min={5} className={inputClass(false)} /></Field>
              </div>
            </Section>

            <Section id="schedule" title="调度设置">
              <Field label="执行频率">
                <select className={inputClass(false)} onChange={() => setHasChanges(true)}>
                  <option>每小时</option><option>每 2 小时</option><option>每 4 小时</option><option>每天一次</option><option>手动触发</option>
                </select>
              </Field>
              <Field label="执行时间段" hint="仅在指定时间段内执行">
                <div className="flex items-center gap-3 flex-wrap">
                  <input type="time" defaultValue="09:00" className={`${inputClass(false)} w-full md:w-32`} onChange={() => setHasChanges(true)} />
                  <span className="text-gray-400 text-sm hidden md:block">至</span>
                  <input type="time" defaultValue="22:00" className={`${inputClass(false)} w-full md:w-32`} onChange={() => setHasChanges(true)} />
                </div>
              </Field>
              <Field label="时区">
                <select className={inputClass(false)} onChange={() => setHasChanges(true)}>
                  <option>Asia/Shanghai (UTC+8)</option>
                  <option>America/New_York (UTC-5)</option>
                </select>
              </Field>
            </Section>
          </div>
        </div>
      </div>

      {/* Save bar */}
      {hasChanges && (
        <div
          className="fixed bottom-0 left-0 right-0 flex items-center gap-3 px-4 md:px-6 py-3 border-t bg-white z-40"
          style={{ borderColor: 'var(--border)', paddingBottom: 'max(12px, env(safe-area-inset-bottom))' }}
        >
          {saveState === 'error' && (
            <div className="flex items-center gap-1.5 text-sm text-red-600">
              <AlertTriangle size={14} />
              保存失败，请重试
            </div>
          )}
          {saveState === 'success' && (
            <div className="flex items-center gap-1.5 text-sm text-green-600">
              <CheckCircle size={14} />
              已保存
            </div>
          )}
          {saveState === 'idle' && (
            <div className="flex items-center gap-1.5 text-sm text-amber-600">
              <Info size={14} />
              <span className="hidden md:inline">有未保存的更改</span>
            </div>
          )}
          <div className="flex gap-2 ml-auto">
            <button
              className="px-3 md:px-4 py-2 text-sm border rounded-lg hover:bg-gray-50"
              style={{ borderColor: 'var(--border)', minHeight: 44 }}
              onClick={() => setHasChanges(false)}
              disabled={saveState === 'saving'}
            >
              取消
            </button>
            <button
              className="px-3 md:px-4 py-2 text-sm font-medium rounded-lg text-white hover:opacity-90 flex items-center gap-1.5 disabled:opacity-60"
              style={{ background: saveState === 'error' ? '#ef4444' : 'var(--primary)', minHeight: 44 }}
              onClick={handleSave}
              disabled={saveState === 'saving'}
            >
              {saveState === 'saving' ? <><Loader2 size={13} className="animate-spin" /> 保存中…</> : <><Save size={13} /> 保存更改</>}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function inputClass(hasError: boolean) {
  return `w-full px-3 py-2.5 text-sm border rounded-lg bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500 ${hasError ? 'border-red-400' : ''}`
}

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <div id={id} className="flex flex-col gap-4 scroll-mt-24 md:scroll-mt-6">
      <div className="border-b pb-2" style={{ borderColor: 'var(--border)' }}>
        <h2 className="text-base font-semibold text-gray-900">{title}</h2>
      </div>
      {children}
    </div>
  )
}

function Field({ label, children, required, hint, error }: { label: string; children: React.ReactNode; required?: boolean; hint?: string; error?: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-sm font-medium text-gray-700">
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      {hint && <p className="text-xs text-gray-400">{hint}</p>}
      {children}
      {error && <p className="text-xs text-red-500 flex items-center gap-1"><AlertTriangle size={11} />{error}</p>}
    </div>
  )
}
