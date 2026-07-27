import { useState } from 'react'
import { Plus, Search, Edit3, Trash2, X, Eye, CheckCircle, AlertCircle } from 'lucide-react'
import TopBar from '../components/layout/TopBar'
import StatusBadge from '../components/ui/StatusBadge'
import ConfirmModal from '../components/ui/ConfirmModal'

const templates = [
  { id: 1, name: '标准获客模板（中文）', platform: '通用', language: '中文', preview: '您好 {{author_name}}，感谢您的留言...', priority: 1, isDefault: true, enabled: true, updated: '2025-07-20' },
  { id: 2, name: '海外通用模板（英文）', platform: '通用', language: '英文', preview: 'Hi {{author_name}}, thanks for your comment!...', priority: 2, isDefault: false, enabled: true, updated: '2025-07-18' },
  { id: 3, name: 'Facebook 专用回复', platform: 'Facebook', language: '中文', preview: '您好！感谢在 Facebook 上关注我们...', priority: 3, isDefault: false, enabled: true, updated: '2025-07-15' },
  { id: 4, name: '产品咨询回复', platform: '通用', language: '中文', preview: '感谢您询问我们的产品，我们提供...', priority: 4, isDefault: false, enabled: false, updated: '2025-07-10' },
  { id: 5, name: 'TikTok 评论回复', platform: 'TikTok', language: '中英双语', preview: '您好 / Hi {{author_name}}，感谢关注!...', priority: 5, isDefault: false, enabled: true, updated: '2025-07-08' },
]

const defaultContent = `您好 {{author_name}}，感谢您的留言。

我们看到您对跨境电商业务感兴趣，很高兴为您提供进一步的信息。

您可以通过以下方式联系我们：
📱 WhatsApp：{{whatsapp}}
📧 Email：{{email}}
🌐 官网：{{website}}

期待与您合作！`

const VALID_VARS = ['{{whatsapp}}', '{{email}}', '{{website}}', '{{contact}}', '{{campaign_name}}', '{{keyword}}', '{{author_name}}']

function validateContent(content: string) {
  const matches = content.match(/\{\{[^}]+\}\}/g) || []
  return matches.filter((m) => !VALID_VARS.includes(m))
}

interface TemplateEditorProps {
  onClose: () => void
}

function TemplateEditor({ onClose }: TemplateEditorProps) {
  const [content, setContent] = useState(defaultContent)
  const [name, setName] = useState('新建模板')
  const [tab, setTab] = useState<'edit' | 'preview'>('edit')
  const invalidVars = validateContent(content)

  const insertVar = (v: string) => setContent((prev) => prev + v)

  return (
    <div className="fixed inset-0 md:inset-y-0 md:right-0 md:left-auto md:w-[540px] bg-white border-l flex flex-col z-40 shadow-xl" style={{ borderColor: 'var(--border)' }}>
      <div className="flex items-center justify-between px-4 py-3 border-b shrink-0" style={{ borderColor: 'var(--border)' }}>
        <h3 className="font-semibold text-gray-900">编辑回复模板</h3>
        <button className="text-gray-400 hover:text-gray-600 p-2" onClick={onClose} style={{ minHeight: 44, minWidth: 44 }}><X size={16} /></button>
      </div>

      {/* Mobile edit/preview tabs */}
      <div className="md:hidden flex border-b shrink-0" style={{ borderColor: 'var(--border)' }}>
        {(['edit', 'preview'] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className="flex-1 py-2.5 text-sm font-medium border-b-2 transition-colors"
            style={{ borderBottomColor: tab === t ? 'var(--primary)' : 'transparent', color: tab === t ? 'var(--primary)' : '#6b7280', minHeight: 44 }}
          >
            {t === 'edit' ? '编辑' : '预览'}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
        {/* Edit panel — hidden on mobile when preview tab is active */}
        <div className={tab === 'preview' ? 'hidden' : ''}>
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-xs font-medium text-gray-600">模板名称</label>
              <input value={name} onChange={(e) => setName(e.target.value)} className="px-3 py-2.5 text-sm border rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500" style={{ borderColor: 'var(--border)', minHeight: 44 }} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-gray-600">平台</label>
                <select className="px-3 py-2.5 text-sm border rounded-lg focus:outline-none" style={{ borderColor: 'var(--border)', minHeight: 44 }}>
                  {['通用', 'Facebook', 'Instagram', 'TikTok', 'X', 'YouTube'].map((p) => <option key={p}>{p}</option>)}
                </select>
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-xs font-medium text-gray-600">语言</label>
                <select className="px-3 py-2.5 text-sm border rounded-lg focus:outline-none" style={{ borderColor: 'var(--border)', minHeight: 44 }}>
                  {['中文', '英文', '中英双语'].map((l) => <option key={l}>{l}</option>)}
                </select>
              </div>
            </div>

            <div>
              <div className="text-xs font-medium text-gray-600 mb-1.5">插入变量</div>
              <div className="flex flex-wrap gap-1.5">
                {VALID_VARS.map((v) => (
                  <button
                    key={v}
                    className="px-2 py-1.5 bg-indigo-50 border border-indigo-100 rounded text-xs font-mono text-indigo-600 hover:bg-indigo-100 transition-colors"
                    onClick={() => insertVar(v)}
                    style={{ minHeight: 36 }}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-gray-600">模板内容</label>
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                rows={8}
                className="px-3 py-2.5 text-sm border rounded-lg font-mono focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-none"
                style={{ borderColor: invalidVars.length > 0 ? '#ef4444' : 'var(--border)' }}
              />
              {invalidVars.length > 0 && (
                <div className="flex items-center gap-1.5 text-xs text-red-500">
                  <AlertCircle size={12} />
                  未知变量：{invalidVars.join(', ')}
                </div>
              )}
            </div>

            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 cursor-pointer text-sm text-gray-700" style={{ minHeight: 44 }}>
                <input type="checkbox" defaultChecked />
                启用
              </label>
              <label className="flex items-center gap-2 cursor-pointer text-sm text-gray-700" style={{ minHeight: 44 }}>
                <input type="checkbox" />
                设为默认
              </label>
            </div>
          </div>
        </div>

        {/* Preview panel — always visible on desktop, conditional on mobile */}
        <div className={`${tab === 'edit' ? 'hidden md:block' : ''}`}>
          <div className="border rounded-xl p-4" style={{ background: '#f8f9fb', borderColor: 'var(--border)' }}>
            <div className="flex items-center gap-1.5 mb-2 text-xs font-medium text-gray-500">
              <Eye size={12} />
              实时预览
            </div>
            <div className="text-sm text-gray-700 whitespace-pre-wrap break-words">
              {content
                .replace(/\{\{author_name\}\}/g, '张三')
                .replace(/\{\{whatsapp\}\}/g, '+86 138 xxxx xxxx')
                .replace(/\{\{email\}\}/g, 'sales@company.com')
                .replace(/\{\{website\}\}/g, 'https://company.com')
                .replace(/\{\{contact\}\}/g, '欢迎添加微信')
                .replace(/\{\{campaign_name\}\}/g, '跨境电商引流')
                .replace(/\{\{keyword\}\}/g, '代购')
              }
            </div>
          </div>
        </div>
      </div>

      <div className="border-t p-4 flex flex-col md:flex-row justify-end gap-2 shrink-0" style={{ borderColor: 'var(--border)', paddingBottom: 'max(16px, env(safe-area-inset-bottom))' }}>
        <button className="w-full md:w-auto px-4 py-3 md:py-2 text-sm border rounded-xl md:rounded-lg hover:bg-gray-50" style={{ borderColor: 'var(--border)', minHeight: 44 }} onClick={onClose}>取消</button>
        <button
          className="w-full md:w-auto px-4 py-3 md:py-2 text-sm font-medium rounded-xl md:rounded-lg text-white hover:opacity-90 flex items-center justify-center gap-1.5"
          style={{ background: invalidVars.length > 0 ? '#9ca3af' : 'var(--primary)', minHeight: 44 }}
          disabled={invalidVars.length > 0}
          onClick={onClose}
        >
          <CheckCircle size={13} />
          保存模板
        </button>
      </div>
    </div>
  )
}

interface ReplyTemplatesProps {
  onMenuOpen?: () => void
}

export default function ReplyTemplates({ onMenuOpen }: ReplyTemplatesProps) {
  const [search, setSearch] = useState('')
  const [editorOpen, setEditorOpen] = useState(false)
  const [deleteId, setDeleteId] = useState<number | null>(null)

  const filtered = templates.filter((t) =>
    !search || t.name.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div className="flex flex-col min-h-screen">
      <TopBar breadcrumbs={['回复自动化', '回复模板']} pageTitle="回复模板" onMenuOpen={onMenuOpen} />
      <div className="flex-1 p-4 md:p-6 flex flex-col gap-4">
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="min-w-0">
            <h1 className="text-xl font-semibold text-gray-900">回复模板</h1>
            <p className="text-sm text-gray-500 mt-0.5 hidden md:block">创建可复用的固定回复内容，并通过变量插入联系方式和活动信息。</p>
          </div>
          <button
            className="flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium rounded-lg text-white hover:opacity-90 shrink-0"
            style={{ background: 'var(--primary)', minHeight: 44 }}
            onClick={() => setEditorOpen(true)}
          >
            <Plus size={14} />
            新建模板
          </button>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <div className="relative flex-1 min-w-0" style={{ maxWidth: 260 }}>
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              placeholder="搜索模板..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 pr-3 py-2.5 text-sm border rounded-lg bg-white focus:outline-none w-full"
              style={{ borderColor: 'var(--border)', minHeight: 44 }}
            />
          </div>
          <select className="px-3 py-2.5 text-sm border rounded-lg bg-white focus:outline-none" style={{ borderColor: 'var(--border)', minHeight: 44 }}>
            {['全部平台', 'Facebook', 'Instagram', 'TikTok', '通用'].map((p) => <option key={p}>{p}</option>)}
          </select>
        </div>

        {/* Desktop table */}
        <div className="hidden md:block bg-white border rounded-xl overflow-hidden" style={{ borderColor: 'var(--border)' }}>
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[640px]">
              <thead>
                <tr className="border-b text-left" style={{ borderColor: 'var(--border)' }}>
                  {['模板名称', '平台', '语言', '状态', '最近更新', '操作'].map((h) => (
                    <th key={h} className="px-4 py-3 text-xs font-semibold text-gray-500">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((t) => (
                  <tr key={t.id} className="border-b hover:bg-gray-50 transition-colors" style={{ borderColor: 'var(--border)' }}>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="font-medium text-gray-800 truncate">{t.name}</span>
                        {t.isDefault && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-indigo-100 text-indigo-700 shrink-0">默认</span>}
                      </div>
                      <div className="text-xs text-gray-400 truncate max-w-xs">{t.preview}</div>
                    </td>
                    <td className="px-4 py-3 text-gray-600">{t.platform}</td>
                    <td className="px-4 py-3 text-gray-600">{t.language}</td>
                    <td className="px-4 py-3"><StatusBadge status={t.enabled ? '已启用' : '已停用'} /></td>
                    <td className="px-4 py-3 text-gray-400">{t.updated}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1">
                        <button className="p-2 text-gray-400 hover:text-indigo-600 rounded-lg hover:bg-indigo-50" style={{ minHeight: 36, minWidth: 36 }} onClick={() => setEditorOpen(true)}><Edit3 size={13} /></button>
                        <button className="p-2 text-gray-400 hover:text-red-600 rounded-lg hover:bg-red-50" style={{ minHeight: 36, minWidth: 36 }} onClick={() => setDeleteId(t.id)}><Trash2 size={13} /></button>
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
          {filtered.map((t) => (
            <div key={t.id} className="bg-white border rounded-xl p-4" style={{ borderColor: 'var(--border)' }}>
              <div className="flex items-start justify-between gap-2 mb-1">
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="font-medium text-sm text-gray-800 truncate">{t.name}</span>
                    {t.isDefault && <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-indigo-100 text-indigo-700 shrink-0">默认</span>}
                  </div>
                  <div className="text-xs text-gray-400 mt-0.5 line-clamp-2">{t.preview}</div>
                </div>
                <StatusBadge status={t.enabled ? '已启用' : '已停用'} />
              </div>
              <div className="flex items-center gap-3 mt-2 text-xs text-gray-400">
                <span>{t.platform}</span>
                <span>·</span>
                <span>{t.language}</span>
                <span>·</span>
                <span>{t.updated}</span>
              </div>
              <div className="flex gap-2 mt-3">
                <button className="flex-1 py-2.5 text-xs border rounded-xl flex items-center justify-center gap-1.5 text-gray-600" style={{ borderColor: 'var(--border)', minHeight: 44 }} onClick={() => setEditorOpen(true)}>
                  <Edit3 size={12} /> 编辑
                </button>
                <button className="flex-1 py-2.5 text-xs border rounded-xl flex items-center justify-center gap-1.5 text-red-500" style={{ borderColor: '#fca5a5', minHeight: 44 }} onClick={() => setDeleteId(t.id)}>
                  <Trash2 size={12} /> 删除
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {editorOpen && (
        <>
          <div className="fixed inset-0 bg-black/20 z-30" onClick={() => setEditorOpen(false)} />
          <TemplateEditor onClose={() => setEditorOpen(false)} />
        </>
      )}

      <ConfirmModal
        open={deleteId !== null}
        title="删除模板"
        description="删除后将无法恢复，且使用此模板的活动将恢复默认。"
        confirmLabel="删除"
        destructive
        onConfirm={() => setDeleteId(null)}
        onCancel={() => setDeleteId(null)}
      />
    </div>
  )
}
