import { useEffect, useReducer, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useParams } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import { useCampaign, useCreateCampaign, useUpdateCampaign, type CampaignPayload, type CampaignTargetPolicy } from '../api/campaigns'
import { useMatchingRules } from '../api/matching-rules'
import { usePlatformAccounts } from '../api/platform-accounts'
import { useReplyTemplates } from '../api/reply-templates'
import StickySaveBar, { type SaveState } from '../components/ui/StickySaveBar'
import { buildReplyPreflightWarnings } from './campaignSettingsHelpers'
import CampaignSettingsSections, { type CampaignSettingsFormValues } from './campaign-settings/CampaignSettingsSections'

const targetPolicyOptions: Array<{ value: CampaignTargetPolicy; label: string; description: string }> = [
  { value: 'discovery_only', label: '仅发现', description: '只收集和识别线索，不允许发送回复' },
  { value: 'owned_only', label: '仅自有来源', description: '仅允许回复归属当前账号的内容' },
  { value: 'allowlist', label: '白名单来源', description: '仅允许回复运行环境白名单中的来源' },
]

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

interface CampaignSettingsProps {
  onNavigate?: (page: string) => void
  onMenuOpen?: () => void
}

interface CampaignFormState {
  replyMode: 'off' | 'manual' | 'auto'
  leadMode: 'rules' | 'hybrid' | 'ai'
  llmEnabled: boolean
  keywords: Array<{ id: number; value: string }>
  selectedAccountId: string
  selectedTemplateId: string
  targetPolicy: CampaignTargetPolicy
  formValues: CampaignSettingsFormValues
}

const initialFormState: CampaignFormState = {
  replyMode: 'manual',
  leadMode: 'rules',
  llmEnabled: false,
  keywords: [],
  selectedAccountId: '',
  selectedTemplateId: '',
  targetPolicy: 'discovery_only',
  formValues: {
    name: '',
    description: '',
    region: '',
    whatsapp: '',
    email: '',
    website: '',
    contact: '',
    dailyLimit: '30',
    hourlyLimit: '10',
    minuteLimit: '1',
    intervalSecs: '60',
  },
}

function formReducer(state: CampaignFormState, action: { type: 'replace'; value: CampaignFormState } | { type: 'patch'; value: Partial<CampaignFormState> }): CampaignFormState {
  return action.type === 'replace' ? action.value : { ...state, ...action.value }
}

export default function CampaignSettings({ onNavigate }: CampaignSettingsProps) {
  const navigate = useNavigate()
  const { campaignId } = useParams()
  const { data: platformAccounts = [] } = usePlatformAccounts()
  const { data: templates = [] } = useReplyTemplates()
  const { data: campaignDetail } = useCampaign(campaignId || '')
  const { data: matchingRules = [] } = useMatchingRules(campaignId || undefined)
  const createCampaign = useCreateCampaign()
  const updateCampaign = useUpdateCampaign()
  const [activeSection, setActiveSection] = useState('basic')
  const [formState, dispatchForm] = useReducer(formReducer, initialFormState)
  const { replyMode, leadMode, llmEnabled, keywords, selectedAccountId, selectedTemplateId, targetPolicy, formValues } = formState
  const setReplyMode = (value: CampaignFormState['replyMode']) => dispatchForm({ type: 'patch', value: { replyMode: value } })
  const setLeadMode = (value: CampaignFormState['leadMode']) => dispatchForm({ type: 'patch', value: { leadMode: value } })
  const setLlmEnabled = (value: boolean) => dispatchForm({ type: 'patch', value: { llmEnabled: value } })
  const setKeywords = (update: CampaignFormState['keywords'] | ((current: CampaignFormState['keywords']) => CampaignFormState['keywords'])) => dispatchForm({ type: 'patch', value: { keywords: typeof update === 'function' ? update(keywords) : update } })
  const setSelectedAccountId = (value: string) => dispatchForm({ type: 'patch', value: { selectedAccountId: value } })
  const setSelectedTemplateId = (value: string) => dispatchForm({ type: 'patch', value: { selectedTemplateId: value } })
  const setTargetPolicy = (value: CampaignTargetPolicy) => dispatchForm({ type: 'patch', value: { targetPolicy: value } })
  const setFormValues = (update: CampaignFormState['formValues'] | ((current: CampaignFormState['formValues']) => CampaignFormState['formValues'])) => dispatchForm({ type: 'patch', value: { formValues: typeof update === 'function' ? update(formValues) : update } })

  const [hasChanges, setHasChanges] = useState(false)
  const [saveState, setSaveState] = useState<SaveState>('idle')
  const keywordId = useRef(0)
  const [errors, setErrors] = useState<Record<string, string>>({})

  useEffect(() => {
    if (!campaignDetail) return
    const loadedKeywords = (campaignDetail.keywords || []).flatMap((item: any) => {
      if (!item.keyword) return []
      const keyword = { id: keywordId.current, value: item.keyword }
      keywordId.current += 1
      return [keyword]
    })
    dispatchForm({
      type: 'replace',
      value: {
        formValues: {
          name: campaignDetail.name || '',
          description: campaignDetail.description || '',
          region: (campaignDetail.target_regions_json || []).join('、'),
          whatsapp: campaignDetail.default_whatsapp || '',
          email: campaignDetail.default_email || '',
          website: campaignDetail.default_website || '',
          contact: campaignDetail.default_contact_text || '',
          dailyLimit: String(campaignDetail.reply_daily_limit || campaignDetail.daily_limit || 30),
          hourlyLimit: String(campaignDetail.reply_per_hour_limit || 10),
          minuteLimit: String(campaignDetail.reply_per_minute_limit || 1),
          intervalSecs: String(campaignDetail.reply_min_interval_seconds || 60),
        },
        selectedAccountId: campaignDetail.platform_account_id,
        keywords: loadedKeywords,
        replyMode: campaignDetail.reply_mode === 'automatic' ? 'auto' : campaignDetail.reply_mode === 'disabled' ? 'off' : 'manual',
        leadMode: campaignDetail.lead_detection_mode === 'rules_with_llm' ? 'hybrid' : 'rules',
        llmEnabled: Boolean(campaignDetail.llm_enabled),
        selectedTemplateId: campaignDetail.default_reply_template_id || '',
        targetPolicy: campaignDetail.target_policy || 'discovery_only',
      },
    })
  }, [campaignDetail])

  const setField = (key: string, value: string) => {
    setFormValues((prev) => ({ ...prev, [key]: value }))
    setHasChanges(true)
    if (errors[key]) setErrors((prev) => { const e = { ...prev }; delete e[key]; return e })
  }

  const validate = () => {
    const e: Record<string, string> = {}
    if (!formValues.name.trim()) e.name = '活动名称不能为空'
    if (!selectedAccountId && platformAccounts.length === 0) e.account = '请先创建或选择一个平台账号'
    if (keywords.filter(({ value }) => value.trim()).length === 0) e.keywords = '至少需要一个关键词'
    if (formValues.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formValues.email)) e.email = '邮箱格式不正确'
    return e
  }

  const selectedAccount = platformAccounts.find((account) => account.id === selectedAccountId)
  const preflightWarnings = buildReplyPreflightWarnings({
    replyMode,
    targetPolicy,
    selectedTemplateId,
    selectedAccount,
    keywordCount: keywords.filter(({ value }) => value.trim()).length,
    enabledRuleCount: campaignId ? matchingRules.filter((rule) => rule.status === 'active' && rule.campaign_id === campaignId).length : 0,
  })

  const handleSave = async () => {
    const e = validate()
    if (Object.keys(e).length > 0) { setErrors(e); return }
    const platformAccountId = selectedAccountId || platformAccounts[0]?.id
    if (!platformAccountId) {
      setErrors({ account: '请先创建或选择一个平台账号' })
      return
    }
    setSaveState('saving')
    const payload: CampaignPayload = {
      name: formValues.name.trim(),
      description: formValues.description.trim() || null,
      platform_account_id: platformAccountId,
      status: 'active',
      target_policy: targetPolicy,
      max_contents: 2,
      max_comments: 30,
      min_confidence: leadMode === 'rules' ? 0.75 : 0.7,
      max_leads: 5,
      daily_limit: Number(formValues.dailyLimit) || 5,
      llm_enabled: llmEnabled || leadMode === 'hybrid' || leadMode === 'ai',
      lead_detection_mode: leadMode === 'rules' ? 'rules_only' : 'rules_with_llm',
      reply_mode: replyMode === 'auto' ? 'automatic' : replyMode === 'manual' ? 'manual_approval' : 'disabled',
      default_reply_template_id: selectedTemplateId || null,
      positive_keywords_json: keywords.flatMap(({ value }) => {
        const keyword = value.trim()
        return keyword ? [keyword] : []
      }),
      negative_keywords_json: [],
      default_whatsapp: formValues.whatsapp.trim() || null,
      default_email: formValues.email.trim() || null,
      default_website: formValues.website.trim() || null,
      default_contact_text: formValues.contact.trim() || null,
      reply_daily_limit: Number(formValues.dailyLimit) || 30,
      reply_per_hour_limit: Number(formValues.hourlyLimit) || 10,
      reply_per_minute_limit: Number(formValues.minuteLimit) || 1,
      reply_min_interval_seconds: Number(formValues.intervalSecs) || 60,
      target_regions_json: formValues.region.split(/[、,]/).flatMap((item) => {
        const region = item.trim()
        return region ? [region] : []
      }),
      content_types_json: ['post_comments', 'video_comments'],
      content_language: 'any',
      initial_keywords: keywords.flatMap(({ value }) => {
        const keyword = value.trim()
        return keyword ? [keyword] : []
      }),
    }
    try {
      if (campaignId) {
        const { initial_keywords, ...updatePayload } = payload
        await updateCampaign.mutateAsync({ id: campaignId, data: updatePayload })
      } else {
        await createCampaign.mutateAsync(payload)
      }
      setSaveState('success')
      setHasChanges(false)
      setTimeout(() => navigate('/campaigns'), 600)
    } catch {
      setSaveState('error')
      setTimeout(() => setSaveState('idle'), 3000)
      return
    }
  }

  const scrollTo = (id: string) => {
    setActiveSection(id)
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <div className="flex h-full min-h-0 overflow-hidden">
      <div className="flex min-h-0 flex-1">
        {/* Desktop section nav */}
        <nav data-scroll-region className="hidden min-h-0 w-60 shrink-0 flex-col overflow-y-auto border-r bg-card px-2 py-4 md:flex">
          {sections.map((s) => (
            <button
              type="button"
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
        <div className="absolute inset-x-0 top-0 z-20 border-b bg-card px-4 py-2 md:hidden">
          <select
            aria-label="活动设置章节"
            value={activeSection}
            onChange={(e) => scrollTo(e.target.value)}
            className="w-full px-3 py-2 text-sm border rounded-lg bg-white focus:outline-none"
            style={{ borderColor: 'var(--border)', minHeight: 40 }}
          >
            {sections.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </div>

        {/* Form content */}
        <div data-scroll-region className="min-h-0 flex-1 overflow-y-auto overscroll-contain pt-16 md:pt-0">
          <div className="max-w-3xl mx-auto p-4 md:p-8 flex flex-col gap-6 md:gap-8">

            <CampaignSettingsSections
              formValues={formValues}
              errors={errors}
              platformAccounts={platformAccounts}
              selectedAccountId={selectedAccountId}
              keywords={keywords}
              targetPolicy={targetPolicy}
              leadMode={leadMode}
              replyMode={replyMode}
              preflightWarnings={preflightWarnings}
              templates={templates}
              selectedTemplateId={selectedTemplateId}
              llmEnabled={llmEnabled}
              onFieldChange={setField}
              onAccountChange={(value) => { setSelectedAccountId(value); setHasChanges(true) }}
              onKeywordsChange={(value) => { setKeywords(value); setHasChanges(true) }}
              onAddKeyword={() => { const id = keywordId.current; keywordId.current += 1; setKeywords((items) => [...items, { id, value: '' }]); setHasChanges(true) }}
              onTargetPolicyChange={(value) => { setTargetPolicy(value); setHasChanges(true) }}
              onLeadModeChange={(value) => { setLeadMode(value); setHasChanges(true) }}
              onReplyModeChange={(value) => { setReplyMode(value); setHasChanges(true) }}
              onTemplateChange={(value) => { setSelectedTemplateId(value); setHasChanges(true) }}
              onLlmEnabledChange={(value) => { setLlmEnabled(value); setHasChanges(true) }}
              onMarkChanged={() => setHasChanges(true)}
            />
          </div>
          <StickySaveBar
            dirty={hasChanges}
            state={saveState}
            onCancel={() => { setHasChanges(false); setSaveState('idle') }}
            onSave={handleSave}
          />
        </div>
      </div>
    </div>
  )
}