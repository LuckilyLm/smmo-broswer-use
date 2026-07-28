import { useEffect, useState } from 'react'
import { AlertCircle, CheckCircle, Edit3, Eye, Plus, Search, Trash2, X } from 'lucide-react'

import { useCreateReplyTemplate, useDeleteReplyTemplate, useReplyTemplates, useUpdateReplyTemplate, type ReplyTemplate } from '../api/reply-templates'
import ConfirmModal from '../components/ui/ConfirmModal'
import StatusBadge from '../components/ui/StatusBadge'

const VALID_VARS = ['{{whatsapp}}', '{{email}}', '{{website}}', '{{contact}}', '{{campaign_name}}', '{{keyword}}', '{{author_name}}']
const defaultContent = `您好 {{author_name}}，感谢您的留言。

我们看到您对相关业务感兴趣，可以通过以下方式联系我们：
WhatsApp：{{whatsapp}}
Email：{{email}}
官网：{{website}}`

function validateContent(content: string) {
  const matches = content.match(/\{\{[^}]+\}\}/g) || []
  return matches.filter((m) => !VALID_VARS.includes(m))
}

function renderPreview(content: string) {
  return content
    .replace(/\{\{author_name\}\}/g, '张三')
    .replace(/\{\{whatsapp\}\}/g, '+86 138 xxxx xxxx')
    .replace(/\{\{email\}\}/g, 'sales@company.com')
    .replace(/\{\{website\}\}/g, 'https://company.com')
    .replace(/\{\{contact\}\}/g, '欢迎添加微信')
    .replace(/\{\{campaign_name\}\}/g, '铝型材供应商获客')
    .replace(/\{\{keyword\}\}/g, 'aluminum extrusion supplier')
}

function TemplateEditor({ template, onClose }: { template?: ReplyTemplate | null; onClose: () => void }) {
  const createTemplate = useCreateReplyTemplate()
  const updateTemplate = useUpdateReplyTemplate()
  const [content, setContent] = useState(template?.content || defaultContent)
  const [name, setName] = useState(template?.name || '新建模板')
  const [tab, setTab] = useState<'edit' | 'preview'>('edit')
  const invalidVars = validateContent(content)

  useEffect(() => {
    setName(template?.name || '新建模板')
    setContent(template?.content || defaultContent)
  }, [template])

  const save = async () => {
    if (invalidVars.length > 0) return
    if (template) {
      await updateTemplate.mutateAsync({ id: template.id, data: { name, content, status: 'active' } })
    } else {
      await createTemplate.mutateAsync({ name, content, platform: 'facebook', language: 'zh-CN' })
    }
    onClose()
  }

  return (
    <div className="fixed inset-0 z-40 flex min-h-0 flex-col overflow-hidden bg-white shadow-xl md:inset-y-0 md:left-auto md:right-0 md:w-[540px] md:border-l" style={{ borderColor: 'var(--border)' }}>
      <div className="flex shrink-0 items-center justify-between border-b px-4 py-3" style={{ borderColor: 'var(--border)' }}>
        <h3 className="font-semibold text-gray-900">{template ? '编辑回复模板' : '新建回复模板'}</h3>
        <button className="p-2 text-gray-400 hover:text-gray-600" onClick={onClose} style={{ minHeight: 44, minWidth: 44 }}><X size={16} /></button>
      </div>
      <div className="flex shrink-0 border-b md:hidden" style={{ borderColor: 'var(--border)' }}>
        {(['edit', 'preview'] as const).map((t) => <button key={t} className="flex-1 border-b-2 py-2.5 text-sm font-medium" style={{ borderBottomColor: tab === t ? 'var(--primary)' : 'transparent', color: tab === t ? 'var(--primary)' : '#6b7280' }} onClick={() => setTab(t)}>{t === 'edit' ? '编辑' : '预览'}</button>)}
      </div>
      <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
        <div className={tab === 'preview' ? 'hidden md:block' : ''}>
          <div className="flex flex-col gap-3">
            <Field label="模板名称"><input value={name} onChange={(e) => setName(e.target.value)} className={inp} /></Field>
            <div>
              <div className="mb-1.5 text-xs font-medium text-gray-600">插入变量</div>
              <div className="flex flex-wrap gap-1.5">
                {VALID_VARS.map((v) => <button key={v} className="rounded border border-indigo-100 bg-indigo-50 px-2 py-1.5 font-mono text-xs text-indigo-600 hover:bg-indigo-100" style={{ minHeight: 36 }} onClick={() => setContent((prev) => prev + v)}>{v}</button>)}
              </div>
            </div>
            <Field label="模板内容">
              <textarea value={content} onChange={(e) => setContent(e.target.value)} rows={10} className={`${inp} resize-none font-mono`} style={{ borderColor: invalidVars.length > 0 ? '#ef4444' : 'var(--border)' }} />
              {invalidVars.length > 0 && <div className="mt-1 flex items-center gap-1.5 text-xs text-red-500"><AlertCircle size={12} />未知变量：{invalidVars.join(', ')}</div>}
            </Field>
          </div>
        </div>
        <div className={tab === 'edit' ? 'hidden md:block' : ''}>
          <div className="rounded-xl border p-4" style={{ background: '#f8f9fb', borderColor: 'var(--border)' }}>
            <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-gray-500"><Eye size={12} />实时预览</div>
            <div className="whitespace-pre-wrap break-words text-sm leading-relaxed text-gray-700">{renderPreview(content)}</div>
          </div>
        </div>
      </div>
      <div className="flex shrink-0 flex-col justify-end gap-2 border-t p-4 md:flex-row" style={{ borderColor: 'var(--border)' }}>
        <button className="rounded-xl border px-4 py-3 text-sm hover:bg-gray-50 md:rounded-lg md:py-2" style={{ borderColor: 'var(--border)', minHeight: 44 }} onClick={onClose}>取消</button>
        <button className="flex items-center justify-center gap-1.5 rounded-xl px-4 py-3 text-sm font-medium text-white disabled:opacity-50 md:rounded-lg md:py-2" style={{ background: invalidVars.length > 0 ? '#9ca3af' : 'var(--primary)', minHeight: 44 }} disabled={invalidVars.length > 0 || createTemplate.isPending || updateTemplate.isPending} onClick={save}><CheckCircle size={13} />保存模板</button>
      </div>
    </div>
  )
}

export default function ReplyTemplates() {
  const { data: templates = [], isLoading, error } = useReplyTemplates()
  const deleteTemplate = useDeleteReplyTemplate()
  const [search, setSearch] = useState('')
  const [editing, setEditing] = useState<ReplyTemplate | null | undefined>(undefined)
  const [deleteId, setDeleteId] = useState<string | null>(null)
  const filtered = templates.filter((t) => !search || t.name.toLowerCase().includes(search.toLowerCase()) || t.content.toLowerCase().includes(search.toLowerCase()))

  return (
    <div className="flex min-h-full flex-col">
      <div className="flex flex-1 flex-col gap-4 p-4 md:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div><h1 className="text-xl font-semibold text-gray-900">回复模板</h1><p className="mt-0.5 hidden text-sm text-gray-500 md:block">创建真实可复用回复内容，供匹配规则和回复计划使用。</p></div>
          <button className="flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2.5 text-sm font-medium text-white" style={{ background: 'var(--primary)', minHeight: 44 }} onClick={() => setEditing(null)}><Plus size={14} />新建模板</button>
        </div>
        <div className="relative" style={{ maxWidth: 280 }}>
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="搜索模板..." className="w-full rounded-lg border bg-white py-2.5 pl-8 pr-3 text-sm focus:outline-none" style={{ borderColor: 'var(--border)', minHeight: 44 }} />
        </div>
        {error && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">模板加载失败，请刷新重试</div>}
        <div className="hidden overflow-hidden rounded-xl border bg-white md:block" style={{ borderColor: 'var(--border)' }}>
          {isLoading ? <div className="p-4 text-sm text-gray-500">正在加载模板...</div> : (
            <table className="w-full min-w-[640px] text-sm">
              <thead><tr className="border-b text-left" style={{ borderColor: 'var(--border)' }}>{['模板名称', '变量', '状态', '最近更新', '操作'].map((h) => <th key={h} className="px-4 py-3 text-xs font-semibold text-gray-500">{h}</th>)}</tr></thead>
              <tbody>{filtered.map((t) => <tr key={t.id} className="border-b last:border-0 hover:bg-gray-50" style={{ borderColor: 'var(--border)' }}>
                <td className="px-4 py-3"><div className="font-medium text-gray-800">{t.name}</div><div className="max-w-md truncate text-xs text-gray-400">{t.content}</div></td>
                <td className="px-4 py-3 text-xs text-gray-500">{t.variables.length ? t.variables.join(', ') : '—'}</td>
                <td className="px-4 py-3"><StatusBadge status={t.status === 'active' ? '已启用' : t.status === 'archived' ? '已归档' : '草稿'} /></td>
                <td className="px-4 py-3 text-xs text-gray-400">{formatDate(t.updated_at)}</td>
                <td className="px-4 py-3"><div className="flex gap-1"><button className="rounded-lg p-2 text-gray-400 hover:bg-indigo-50 hover:text-indigo-600" onClick={() => setEditing(t)}><Edit3 size={13} /></button><button className="rounded-lg p-2 text-gray-400 hover:bg-red-50 hover:text-red-600" onClick={() => setDeleteId(t.id)}><Trash2 size={13} /></button></div></td>
              </tr>)}</tbody>
            </table>
          )}
          {!isLoading && filtered.length === 0 && <div className="p-8 text-center text-sm text-gray-400">暂无模板</div>}
        </div>
        <div className="flex flex-col gap-3 md:hidden">
          {filtered.map((t) => <div key={t.id} className="rounded-xl border bg-white p-4" style={{ borderColor: 'var(--border)' }}><div className="flex justify-between gap-2"><div className="min-w-0"><div className="truncate font-medium text-gray-800">{t.name}</div><div className="mt-1 line-clamp-2 text-xs text-gray-400">{t.content}</div></div><StatusBadge status={t.status === 'active' ? '已启用' : '草稿'} /></div><div className="mt-3 flex gap-2"><button className="flex-1 rounded-xl border py-2.5 text-xs" style={{ borderColor: 'var(--border)' }} onClick={() => setEditing(t)}>编辑</button><button className="flex-1 rounded-xl border py-2.5 text-xs text-red-500" style={{ borderColor: '#fca5a5' }} onClick={() => setDeleteId(t.id)}>删除</button></div></div>)}
        </div>
      </div>
      {editing !== undefined && <><div className="fixed inset-0 z-30 bg-black/20" onClick={() => setEditing(undefined)} /><TemplateEditor template={editing} onClose={() => setEditing(undefined)} /></>}
      <ConfirmModal open={deleteId !== null} title="删除模板" description="删除后将无法恢复，使用此模板的规则可能需要重新选择模板。" confirmLabel="删除" destructive onConfirm={() => { if (deleteId) deleteTemplate.mutate(deleteId); setDeleteId(null) }} onCancel={() => setDeleteId(null)} />
    </div>
  )
}

const inp = "w-full rounded-lg border bg-white px-3 py-2.5 text-sm focus:outline-none focus:ring-1 focus:ring-indigo-500"
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="flex flex-col gap-1.5"><label className="text-xs font-medium text-gray-600">{label}</label>{children}</div>
}
function formatDate(value?: string) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
