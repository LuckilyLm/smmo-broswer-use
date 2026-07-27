import { AlertTriangle, X } from 'lucide-react'

interface ConfirmModalProps {
  open: boolean
  title: string
  description?: string
  confirmLabel?: string
  cancelLabel?: string
  destructive?: boolean
  loading?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export default function ConfirmModal({
  open, title, description, confirmLabel = '确认', cancelLabel = '取消',
  destructive = false, loading = false, onConfirm, onCancel
}: ConfirmModalProps) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center">
      <div className="absolute inset-0 bg-black/30" onClick={onCancel} />
      {/* Full-width bottom sheet on mobile, centered modal on desktop */}
      <div
        className="relative bg-white rounded-t-2xl md:rounded-xl border shadow-xl w-full md:w-96 p-5 md:p-6"
        style={{ borderColor: 'var(--border)', paddingBottom: 'max(20px, env(safe-area-inset-bottom))' }}
      >
        <button className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 p-2" onClick={onCancel} style={{ minHeight: 44, minWidth: 44 }}>
          <X size={16} />
        </button>
        <div className="flex items-start gap-3 pr-8">
          {destructive && (
            <div className="p-2 rounded-full bg-red-50 shrink-0">
              <AlertTriangle size={18} className="text-red-500" />
            </div>
          )}
          <div>
            <h3 className="font-semibold text-gray-900 text-sm">{title}</h3>
            {description && <p className="mt-1.5 text-sm text-gray-500 leading-relaxed">{description}</p>}
          </div>
        </div>
        <div className="flex flex-col md:flex-row gap-2 mt-5 md:justify-end">
          <button
            className="w-full md:w-auto px-4 py-3 md:py-2 text-sm border rounded-xl md:rounded-lg hover:bg-gray-50 order-2 md:order-1"
            style={{ borderColor: 'var(--border)', minHeight: 44 }}
            onClick={onCancel}
            disabled={loading}
          >
            {cancelLabel}
          </button>
          <button
            className="w-full md:w-auto px-4 py-3 md:py-2 text-sm font-medium rounded-xl md:rounded-lg text-white flex items-center justify-center gap-2 disabled:opacity-60 order-1 md:order-2"
            style={{ background: destructive ? '#ef4444' : 'var(--primary)', minHeight: 44 }}
            onClick={onConfirm}
            disabled={loading}
          >
            {loading && <span className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
