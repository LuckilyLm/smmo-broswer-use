import { useState } from 'react'
import { AlertTriangle, Shield, Globe, Bell, Lock, Monitor, Save, Info } from 'lucide-react'
import TopBar from '../components/layout/TopBar'
import ConfirmModal from '../components/ui/ConfirmModal'

const sectionItems = [
  { id: 'tenant', label: '租户信息', icon: <Monitor size={14} /> },
  { id: 'contact', label: '默认联系方式', icon: <Globe size={14} /> },
  { id: 'template', label: '默认回复模板', icon: <Globe size={14} /> },
  { id: 'send-switch', label: '回复发送开关', icon: <Shield size={14} /> },
  { id: 'locale', label: '语言与时区', icon: <Globe size={14} /> },
  { id: 'notifications', label: '通知设置', icon: <Bell size={14} /> },
  { id: 'security', label: '安全设置', icon: <Lock size={14} /> },
  { id: 'sessions', label: '会话管理', icon: <Monitor size={14} /> },
]

const inp = "w-full px-3 py-2.5 text-sm border rounded-lg bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"

function Sec({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <div id={id} className="scroll-mt-20 md:scroll-mt-6 flex flex-col gap-4">
      <div className="border-b pb-2" style={{ borderColor: 'var(--border)' }}>
        <h2 className="text-base font-semibold text-gray-900">{title}</h2>
      </div>
      {children}
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="text-sm font-medium text-gray-700">{label}</label>
      {children}
    </div>
  )
}

interface SettingsProps {
  onMenuOpen?: () => void
}

export default function Settings({ onMenuOpen }: SettingsProps) {
  const [activeSection, setActiveSection] = useState('tenant')
  const [sendEnabled, setSendEnabled] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)

  const handleSendToggle = (newVal: boolean) => {
    if (newVal) {
      setConfirmOpen(true)
    } else {
      setSendEnabled(false)
    }
  }

  const scrollTo = (id: string) => {
    setActiveSection(id)
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
  }

  return (
    <div className="flex flex-col" style={{ height: '100vh', overflow: 'hidden' }}>
      <TopBar breadcrumbs={['系统', '设置']} pageTitle="设置" onMenuOpen={onMenuOpen} />

      {/* Mobile section select */}
      <div className="md:hidden px-4 py-2 border-b bg-white shrink-0" style={{ borderColor: 'var(--border)' }}>
        <select
          className="w-full px-3 py-2.5 text-sm border rounded-xl bg-white focus:outline-none"
          style={{ borderColor: 'var(--border)', minHeight: 44 }}
          value={activeSection}
          onChange={(e) => scrollTo(e.target.value)}
        >
          {sectionItems.map((s) => (
            <option key={s.id} value={s.id}>{s.label}</option>
          ))}
        </select>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Desktop section nav */}
        <nav className="hidden md:block w-52 shrink-0 border-r bg-white py-4 px-2 overflow-y-auto" style={{ borderColor: 'var(--border)' }}>
          {sectionItems.map((s) => (
            <button
              key={s.id}
              onClick={() => scrollTo(s.id)}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-sm rounded-lg mb-0.5 text-left transition-colors"
              style={{
                color: activeSection === s.id ? 'var(--primary)' : '#374151',
                background: activeSection === s.id ? 'var(--accent)' : 'transparent',
                fontWeight: activeSection === s.id ? 600 : 400,
                minHeight: 40,
              }}
            >
              <span style={{ color: activeSection === s.id ? 'var(--primary)' : '#9ca3af' }}>{s.icon}</span>
              <span className="truncate">{s.label}</span>
            </button>
          ))}
        </nav>

        <div className="flex-1 overflow-y-auto">
          <div className="p-4 md:p-8 max-w-2xl flex flex-col gap-8">

            <Sec id="tenant" title="租户信息">
              <Field label="租户名称"><input type="text" defaultValue="科技有限公司" className={inp} /></Field>
              <Field label="租户 ID"><input type="text" defaultValue="tenant_8x9z2k" readOnly className={`${inp} bg-gray-50 text-gray-400 cursor-not-allowed`} /></Field>
              <Field label="管理邮箱"><input type="email" defaultValue="admin@company.com" className={inp} /></Field>
            </Sec>

            <Sec id="contact" title="默认联系方式">
              <p className="text-xs text-gray-500">作为新建活动的默认值，各活动可单独覆盖</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Field label="WhatsApp"><input type="text" defaultValue="+86 138 xxxx xxxx" className={inp} /></Field>
                <Field label="Email"><input type="text" defaultValue="sales@company.com" className={inp} /></Field>
                <Field label="官网"><input type="text" defaultValue="https://company.com" className={inp} /></Field>
                <Field label="联系文本"><input type="text" defaultValue="欢迎添加微信" className={inp} /></Field>
              </div>
            </Sec>

            <Sec id="template" title="默认回复模板">
              <Field label="默认模板">
                <select className={inp}>
                  <option>标准获客模板（中文）</option>
                  <option>海外通用模板（英文）</option>
                </select>
              </Field>
            </Sec>

            <Sec id="send-switch" title="回复发送开关">
              <div
                className="p-4 rounded-xl border"
                style={{ background: sendEnabled ? '#fff1f2' : '#fffbeb', borderColor: sendEnabled ? '#fca5a5' : '#fcd34d' }}
              >
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div className="flex items-start gap-3 flex-1 min-w-0">
                    <AlertTriangle size={18} className={sendEnabled ? 'text-red-500 shrink-0' : 'text-amber-500 shrink-0'} />
                    <div className="min-w-0">
                      <div className="font-semibold text-sm" style={{ color: sendEnabled ? '#991b1b' : '#92400e' }}>
                        回复发送开关
                      </div>
                      <div className="text-xs mt-1 leading-relaxed" style={{ color: sendEnabled ? '#b91c1c' : '#b45309' }}>
                        {sendEnabled
                          ? '开关已开启。已审批的回复将实际发送至社媒平台。请确保您已了解相关平台规则。'
                          : '开关当前关闭。系统只会生成候选和计划，不会向真实平台发送任何内容。'
                        }
                      </div>
                      {sendEnabled && (
                        <div className="mt-2 flex items-start gap-1.5 text-xs text-red-600">
                          <Info size={11} className="mt-0.5 shrink-0" />
                          <span>各活动的回复模式仍独立控制，活动级别的设置优先于此开关。</span>
                        </div>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-xs font-medium" style={{ color: sendEnabled ? '#ef4444' : '#6b7280' }}>
                      {sendEnabled ? '已开启' : '已关闭'}
                    </span>
                    <div
                      className="w-11 h-6 rounded-full relative cursor-pointer transition-colors"
                      style={{ background: sendEnabled ? '#ef4444' : '#d1d5db', minWidth: 44, minHeight: 44, display: 'flex', alignItems: 'center' }}
                      onClick={() => handleSendToggle(!sendEnabled)}
                    >
                      <div
                        className="absolute top-1 w-4 h-4 rounded-full bg-white transition-all"
                        style={{ left: sendEnabled ? 26 : 4 }}
                      />
                    </div>
                  </div>
                </div>
              </div>
            </Sec>

            <Sec id="locale" title="语言与时区">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Field label="界面语言">
                  <select className={inp}>
                    <option>简体中文</option>
                    <option>English</option>
                  </select>
                </Field>
                <Field label="时区">
                  <select className={inp}>
                    <option>Asia/Shanghai (UTC+8)</option>
                    <option>America/New_York (UTC-5)</option>
                    <option>Europe/London (UTC+0)</option>
                  </select>
                </Field>
              </div>
            </Sec>

            <Sec id="notifications" title="通知设置">
              {[
                { label: '执行异常通知', desc: '当活动执行失败时发送通知' },
                { label: '登录失效提醒', desc: '当平台账号需要重新登录时提醒' },
                { label: '待审批回复提醒', desc: '有新的待审批回复计划时通知' },
                { label: '线索量异常预警', desc: '当线索量大幅波动时发送预警' },
              ].map(({ label, desc }) => (
                <div key={label} className="flex items-center justify-between py-2 border-b last:border-0" style={{ borderColor: 'var(--border)', minHeight: 52 }}>
                  <div className="min-w-0 mr-3">
                    <div className="text-sm text-gray-800">{label}</div>
                    <div className="text-xs text-gray-400 break-words">{desc}</div>
                  </div>
                  <div className="w-9 h-5 rounded-full relative cursor-pointer shrink-0" style={{ background: 'var(--primary)', minWidth: 36, minHeight: 36, display: 'flex', alignItems: 'center' }}>
                    <div className="absolute top-0.5 w-4 h-4 rounded-full bg-white" style={{ left: 20 }} />
                  </div>
                </div>
              ))}
            </Sec>

            <Sec id="security" title="安全设置">
              <Field label="双因素认证">
                <div className="flex items-center gap-3 flex-wrap">
                  <span className="text-xs px-2 py-1 rounded bg-green-100 text-green-700">已启用</span>
                  <button className="text-xs text-indigo-600 hover:underline" style={{ minHeight: 36 }}>管理 2FA 设备</button>
                </div>
              </Field>
              <Field label="IP 白名单">
                <textarea rows={3} placeholder="每行一个 IP 地址或 CIDR..." className={`${inp} font-mono`} defaultValue="203.0.113.0/24" />
              </Field>
              <Field label="登录通知">
                <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer" style={{ minHeight: 44 }}>
                  <input type="checkbox" defaultChecked />
                  新设备登录时发送 Email 通知
                </label>
              </Field>
            </Sec>

            <Sec id="sessions" title="会话管理">
              {[
                { device: 'Chrome · macOS', location: '上海, 中国', current: true, time: '当前会话' },
                { device: 'Safari · iPhone', location: '北京, 中国', current: false, time: '1 天前' },
                { device: 'Chrome · Windows', location: '广州, 中国', current: false, time: '3 天前' },
              ].map((s, i) => (
                <div key={i} className="flex items-center justify-between py-2.5 border-b last:border-0 gap-3" style={{ borderColor: 'var(--border)', minHeight: 52 }}>
                  <div className="flex items-center gap-3 min-w-0">
                    <Monitor size={16} className="text-gray-400 shrink-0" />
                    <div className="min-w-0">
                      <div className="text-sm text-gray-800 flex items-center gap-2 flex-wrap">
                        <span className="truncate">{s.device}</span>
                        {s.current && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-green-100 text-green-700 shrink-0">当前</span>}
                      </div>
                      <div className="text-xs text-gray-400">{s.location} · {s.time}</div>
                    </div>
                  </div>
                  {!s.current && (
                    <button className="text-xs text-red-500 hover:underline shrink-0" style={{ minHeight: 44 }}>终止会话</button>
                  )}
                </div>
              ))}
              <button className="text-xs text-red-500 hover:underline mt-1" style={{ minHeight: 44 }}>终止其他所有会话</button>
            </Sec>

            {/* Bottom save button */}
            <div className="flex justify-end pb-4">
              <button
                className="flex items-center gap-1.5 px-5 py-2.5 text-sm font-medium rounded-lg text-white hover:opacity-90"
                style={{ background: 'var(--primary)', minHeight: 44 }}
              >
                <Save size={13} />
                保存所有设置
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Mobile sticky save button */}
      <div
        className="md:hidden border-t bg-white px-4 py-3 shrink-0"
        style={{ borderColor: 'var(--border)', paddingBottom: 'max(12px, env(safe-area-inset-bottom))' }}
      >
        <button
          className="w-full flex items-center justify-center gap-1.5 py-3 text-sm font-medium rounded-xl text-white hover:opacity-90"
          style={{ background: 'var(--primary)', minHeight: 44 }}
        >
          <Save size={13} />
          保存所有设置
        </button>
      </div>

      <ConfirmModal
        open={confirmOpen}
        title="确认开启回复发送"
        description="开启后，已审批的回复计划将会实际发送至社媒平台。系统级开关开启不代表所有活动都会自动发送，各活动的回复模式需单独配置。"
        confirmLabel="我已了解风险，确认开启"
        cancelLabel="取消"
        destructive
        onConfirm={() => { setSendEnabled(true); setConfirmOpen(false) }}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  )
}
