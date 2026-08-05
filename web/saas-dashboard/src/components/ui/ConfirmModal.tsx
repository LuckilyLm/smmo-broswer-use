import { useEffect, useId, useRef, type ReactNode } from 'react'
import { AlertTriangle, X } from 'lucide-react'

interface ModalDialogProps {
  open: boolean
  onClose: () => void
  labelledBy?: string
  describedBy?: string
  ariaLabel?: string
  role?: 'dialog' | 'alertdialog'
  children: ReactNode
  className?: string
  panelClassName?: string
  panelStyle?: React.CSSProperties
  closeLabel?: string
}

export function ModalDialog({
  open,
  onClose,
  labelledBy,
  describedBy,
  ariaLabel,
  role = 'dialog',
  children,
  className = '',
  panelClassName = '',
  panelStyle,
  closeLabel = '关闭对话框',
}: ModalDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const returnFocusRef = useRef<HTMLElement | null>(null)
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  }, [onClose])

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog || !open) return

    returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null
    if (typeof dialog.showModal === 'function') {
      if (!dialog.open) dialog.showModal()
    } else {
      dialog.setAttribute('open', '')
    }

    const initialFocus = dialog.querySelector<HTMLElement>('[autofocus], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')
    initialFocus?.focus()

    return () => {
      if (dialog.open && typeof dialog.close === 'function') dialog.close()
      else dialog.removeAttribute('open')
      returnFocusRef.current?.focus()
    }
  }, [open])

  if (!open) return null

  return (
    <dialog
      ref={dialogRef}
      role={role}
      aria-labelledby={labelledBy}
      aria-describedby={describedBy}
      aria-label={ariaLabel}
      className={`fixed inset-0 z-50 m-0 h-full max-h-none w-full max-w-none border-0 bg-transparent p-0 ${className}`}
      onCancel={(event) => {
        event.preventDefault()
        onCloseRef.current()
      }}
    >
      <button type="button" aria-label={closeLabel} className="absolute inset-0 h-full w-full cursor-default bg-transparent" onClick={() => onCloseRef.current()} />
      <div className={`relative z-10 ${panelClassName}`} style={panelStyle}>{children}</div>
    </dialog>
  )
}

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
  const id = useId()
  const titleId = `${id}-title`
  const descriptionId = description ? `${id}-description` : undefined

  return (
    <ModalDialog
      role="alertdialog"
      open={open}
      onClose={onCancel}
      labelledBy={titleId}
      describedBy={descriptionId}
      closeLabel="关闭确认对话框"
      className="flex items-end justify-center backdrop:bg-black/30 md:items-center"
      panelClassName="relative z-10 w-full rounded-t-2xl border bg-white p-5 shadow-xl md:w-96 md:rounded-xl md:p-6"
      panelStyle={{ borderColor: 'var(--border)', paddingBottom: 'max(20px, env(safe-area-inset-bottom))' }}
    >
      <button type="button" aria-label="关闭" className="absolute right-4 top-4 p-2 text-gray-400 hover:text-gray-600" onClick={onCancel} style={{ minHeight: 44, minWidth: 44 }} disabled={loading}>
        <X size={16} />
      </button>
      <div className="flex items-start gap-3 pr-8">
        {destructive && (
          <div className="shrink-0 rounded-full bg-red-50 p-2" aria-hidden="true">
            <AlertTriangle size={18} className="text-red-500" />
          </div>
        )}
        <div>
          <h2 id={titleId} className="text-sm font-semibold text-gray-900">{title}</h2>
          {description && <p id={descriptionId} className="mt-1.5 text-sm leading-relaxed text-gray-500">{description}</p>}
        </div>
      </div>
      <div className="mt-5 flex flex-col gap-2 md:flex-row md:justify-end">
        <button
          type="button"
          className="order-2 w-full rounded-xl border px-4 py-3 text-sm hover:bg-gray-50 md:order-1 md:w-auto md:rounded-lg md:py-2"
          style={{ borderColor: 'var(--border)', minHeight: 44 }}
          onClick={onCancel}
          disabled={loading}
        >
          {cancelLabel}
        </button>
        <button
          type="button"
          className="order-1 flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 text-sm font-medium text-white disabled:opacity-60 md:order-2 md:w-auto md:rounded-lg md:py-2"
          style={{ background: destructive ? '#ef4444' : 'var(--primary)', minHeight: 44 }}
          onClick={onConfirm}
          disabled={loading}
        >
          {loading && <span aria-hidden="true" className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />}
          {confirmLabel}
        </button>
      </div>
    </ModalDialog>
  )
}
