import { useState } from 'react'
import { Plus, Search, Edit3, Trash2, X, CheckCircle, XCircle, AlertTriangle } from 'lucide-react'
import TopBar from '../components/layout/TopBar'
import StatusBadge from '../components/ui/StatusBadge'
import ConfirmModal from '../components/ui/ConfirmModal'

const rules = [
  { id: 1, name: '价格意向强匹配', campaign: '跨境电商引流', priority: 1, conditions: '包含：价格, 多少钱, 报价', template: '标准获客模板', enabled: true, matchCount: 847, updated: '2025-07-20' },
  { id: 2, name: '海外代购需求', campaign: '跨境电商引流', priority: 2, conditions: '包含任意：代购, 海淘, 海外购', template: '标准获客模板', enabled: true, matchCount: 412, updated: '2025-07-18' },
  { id: 3, name: '合作意向识别', campaign: '海外招商合作', priority: 3, conditions: '包含全部：合作, 意向 | 排除：诈骗, 垃圾', template: '商务合作模板', enabled: true, matchCount: 203, updated: '2025-07-15' },
  { id: 4, name: '低质量评论过滤', campaign: '全部活动', priority: 4, conditions: '正则：(广告|推销|骗)\\w*', template: '—', enabled: false, matchCount: 1204, updated: '2025-07-12' },
  { id: 5, name: '英文询盘回复', campaign: '独立站获客', priority: 5, conditions: '包含任意：quote, price, order, buy', template: '海外通用模板', enabled: true, matchCount: 331, updated: '2025-07-10' },
]

const inp = "w-full px-3 py-2.5 text-sm border rounded-lg bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"

function Field({ label, children, span }: { label: string; children: React.ReactNode; span?: number }) {
  return (
    <div className={`flex flex-col gap-1${span === 2 ? ' col-span-2' : ''}`}>
      <label className="text-xs font-medium text-gray-600">{label}</label>
      {children}
    </div>
  )
}

function RuleDrawer({ onClose }: { onClose: () => void }) {
  const [testComment, setTestComment] = useState('')
  const [testResult, setTestResult] = useState<'matched' | 'not_matched' | 'blocked' | null>(null)

  const runTest = () => {
    if (!testComment) return
    const kws = ['价格', '多少钱', '报价']
    const matched = kws.some((k) => testComment.includes(k))
    const blocked = testComment.includes('广告') || testComment.includes('骗')
    setTestResult(blocked ? 'blocked' : matched ? 'matched' : 'not_matched')
  }

  return (
    <div className="fixed inset-0 md:inset-y-0 md:right-0 md:left-auto md:w-[480px] bg-white border-l flex flex-col z-40 shadow-xl" style={{ borderColor: 'var(--border)' }}>
      <div className="flex items-center justify-between px-4 py-3 border-b shrink-0" style={{ borderColor: 'var(--border)' }}>
        <h3 className="font-semibold text-gray-900">编辑匹配规则</h3>
        <button className="text-gray-400 hover:text-gray-600 p-2" onClick={onClose} style={{ minHeight: 44, minWidth: 44 }}><X size={16} /></button>
      </div>
      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-3">
          <Field label="规则名称" span={2}><input type="text" defaultValue="价格意向强匹配" className={inp} /></Field>
          <Field label="关联活动">
            <select className={inp}>
              <option>跨境电商引流</option>
              <option>全部活动</option>
            </select>
          </Field>
          <Field label="优先级"><input type="number" defaultValue={1} min={1} className={inp} /></Field>
          <Field label="回复模板" span={2}>
            <select className={inp}>
              <option>标准获客模板（中文）</option>
              <option>海外通用模板（英文）</option>
            </select>
          </Field>
        </div>

        <div className="border-t pt-4" style={{ borderColor: 'var(--border)' }}>
          <div className="text-sm font-semibold text-gray-800 mb-3">匹配条件</div>
          <div className="flex flex-col gap-3">
            <Field label="包含任意关键词"><input type="text" placeholder="关键词1, 关键词2" defaultValue="价格, 多少钱, 报价" className={inp} /></Field>
            <Field label="包含全部关键词"><input type="text" placeholder="关键词1, 关键词2" className={inp} /></Field>
            <Field label="正则表达式"><input type="text" placeholder="例：(价格|报价)\d+" className={`${inp} font-mono`} /></Field>
            <Field label="排除作者"><input type="text" placeholder="@spam_user, @bot123" className={inp} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="评论语言">
                <select className={inp}>
                  {['不限', '中文', '英文'].map((v) => <option key={v}>{v}</option>)}
                </select>
              </Field>
              <Field label="最小字符数"><input type="number" defaultValue={5} min={1} className={inp} /></Field>
            </div>
          </div>
        </div>

        {/* Rule tester */}
        <div className="border rounded-xl p-4" style={{ background: '#f8f9fb', borderColor: 'var(--border)' }}>
          <div className="text-sm font-semibold text-gray-800 mb-3">规则测试</div>
          <div className="flex flex-col gap-3">
            <Field label="测试评论内容">
              <textarea
                value={testComment}
                onChange={(e) => setTestComment(e.target.value)}
                placeholder="请输入一段评论内容..."
                rows={3}
                className={`${inp} resize-none`}
              />
            </Field>
          </div>
          <button
            className="mt-3 px-4 py-2.5 text-sm font-medium rounded-lg text-white hover:opacity-90 w-full"
            style={{ background: 'var(--primary)', minHeight: 44 }}
            onClick={runTest}
          >
            运行测试
          </button>
          {testResult && (
            <div
              className="mt-3 flex items-center gap-2 p-3 rounded-lg text-sm font-medium"
              style={{
                background: testResult === 'matched' ? '#ecfdf5' : testResult === 'blocked' ? '#fffbeb' : '#f3f4f6',
                color: testResult === 'matched' ? '#15803d' : testResult === 'blocked' ? '#d97706' : '#4b5563',
              }}
            >
              {testResult === 'matched' && <><CheckCircle size={14} /> 规则匹配 · 将使用「标准获客模板」</>}
              {testResult === 'not_matched' && <><XCircle size={14} /> 未匹配</>}
              {testResult === 'blocked' && <><AlertTriangle size={14} /> 已阻断（负向规则命中）</>}
            </div>
          )}
        </div>
      </div>
      <div className="border-t p-4 flex flex-col md:flex-row justify-end gap-2 shrink-0" style={{ borderColor: 'var(--border)', paddingBottom: 'max(16px, env(safe-area-inset-bottom))' }}>
        <button className="w-full md:w-auto px-4 py-3 md:py-2 text-sm border rounded-xl md:rounded-lg hover:bg-gray-50" style={{ borderColor: 'var(--border)', minHeight: 44 }} onClick={onClose}>取消</button>
        <button className="w-full md:w-auto px-4 py-3 md:py-2 text-sm font-medium rounded-xl md:rounded-lg text-white hover:opacity-90" style={{ background: 'var(--primary)', minHeight: 44 }} onClick={onClose}>保存规则</button>
      </div>
    </div>
  )
}

interface MatchingRulesProps {
  onMenuOpen?: () => void
}

export default function MatchingRules({ onMenuOpen }: MatchingRulesProps) {
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const filtered = rules.filter((r) => !search || r.name.toLowerCase().includes(search.toLowerCase()))

  return (
    <div className="flex flex-col min-h-screen">
      <TopBar breadcrumbs={['回复自动化', '匹配规则']} pageTitle="匹配规则" onMenuOpen={onMenuOpen} />
      <div className="flex-1 p-4 md:p-6 flex flex-col gap-4">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold text-gray-900">匹配规则</h1>
            <p className="text-sm text-gray-500 mt-0.5 hidden md:block">通过确定性规则筛选潜在线索，负向关键词和排除条件优先执行。</p>
          </div>
          <button
            className="flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium rounded-lg text-white hover:opacity-90 shrink-0"
            style={{ background: 'var(--primary)', minHeight: 44 }}
            onClick={() => setDrawerOpen(true)}
          >
            <Plus size={14} /> 新建规则
          </button>
        </div>

        <div className="relative" style={{ maxWidth: 260 }}>
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="搜索规则..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8 pr-3 py-2.5 text-sm border rounded-lg bg-white focus:outline-none w-full"
            style={{ borderColor: 'var(--border)', minHeight: 44 }}
          />
        </div>

        {/* Desktop table */}
        <div className="hidden md:block bg-white border rounded-xl overflow-hidden" style={{ borderColor: 'var(--border)' }}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[700px]">
              <thead>
                <tr className="border-b text-left" style={{ borderColor: 'var(--border)', background: '#fafafa' }}>
                  {['优先级', '规则名称', '关联活动', '匹配条件', '回复模板', '命中次数', '状态', '操作'].map((h) => (
                    <th key={h} className="px-4 py-3 text-xs font-semibold text-gray-500">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr key={r.id} className="border-b hover:bg-gray-50 transition-colors" style={{ borderColor: 'var(--border)' }}>
                    <td className="px-4 py-3 text-gray-500 text-center font-mono">{r.priority}</td>
                    <td className="px-4 py-3 font-medium text-gray-800 max-w-[180px] truncate">{r.name}</td>
                    <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{r.campaign}</td>
                    <td className="px-4 py-3 text-gray-500 text-xs max-w-[200px] truncate">{r.conditions}</td>
                    <td className="px-4 py-3 text-gray-600 whitespace-nowrap">{r.template}</td>
                    <td className="px-4 py-3 text-gray-700 font-medium">{r.matchCount.toLocaleString()}</td>
                    <td className="px-4 py-3"><StatusBadge status={r.enabled ? '已启用' : '已停用'} /></td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <button className="p-2 text-gray-400 hover:text-indigo-600 rounded-lg" style={{ minHeight: 36, minWidth: 36 }} onClick={() => setDrawerOpen(true)}><Edit3 size={13} /></button>
                        <button className="p-2 text-gray-400 hover:text-red-600 rounded-lg" style={{ minHeight: 36, minWidth: 36 }} onClick={() => setDeleteId(r.id)}><Trash2 size={13} /></button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Mobile cards */}
        <div className="md:hidden flex flex-col gap-3">
          {filtered.map((r) => (
            <div key={r.id} className="bg-white border rounded-xl p-4" style={{ borderColor: 'var(--border)' }}>
              <div className="flex items-start justify-between gap-2 mb-1">
                <div className="min-w-0">
                  <span className="font-medium text-sm text-gray-800 break-words">{r.name}</span>
                  <div className="text-xs text-gray-500 mt-0.5 truncate">{r.conditions}</div>
                </div>
                <StatusBadge status={r.enabled ? '已启用' : '已停用'} />
              </div>
              <div className="flex items-center gap-3 mt-2 text-xs text-gray-400 flex-wrap">
                <span>优先级 {r.priority}</span>
                <span>·</span>
                <span>{r.campaign}</span>
                <span>·</span>
                <span>命中 {r.matchCount.toLocaleString()}</span>
              </div>
              <div className="flex gap-2 mt-3">
                <button className="flex-1 py-2.5 text-xs border rounded-xl flex items-center justify-center gap-1.5 text-gray-600" style={{ borderColor: 'var(--border)', minHeight: 44 }} onClick={() => setDrawerOpen(true)}>
                  <Edit3 size={12} /> 编辑
                </button>
                <button className="flex-1 py-2.5 text-xs border rounded-xl flex items-center justify-center gap-1.5 text-red-500" style={{ borderColor: '#fca5a5', minHeight: 44 }} onClick={() => setDeleteId(r.id)}>
                  <Trash2 size={12} /> 删除
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {drawerOpen && (
        <>
          <div className="fixed inset-0 bg-black/20 z-30" onClick={() => setDrawerOpen(false)} />
          <RuleDrawer onClose={() => setDrawerOpen(false)} />
        </>
      )}

      <ConfirmModal
        open={deleteId !== null}
        title="删除规则"
        description="删除后将无法恢复，正在使用此规则的活动将停止匹配。"
        confirmLabel="删除"
        destructive
        onConfirm={() => setDeleteId(null)}
        onCancel={() => setDeleteId(null)}
      />
    </div>
  )
}
