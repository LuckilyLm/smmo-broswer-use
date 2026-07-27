import { AlertTriangle, X, Settings } from 'lucide-react'
import { useState } from 'react'

interface SafetyAlertProps {
  onViewSettings?: () => void
}

export default function SafetyAlert({ onViewSettings }: SafetyAlertProps) {
  const [dismissed, setDismissed] = useState(false)
  if (dismissed) return null
  return (
    <div
      className="flex items-start gap-3 px-4 py-3 rounded-xl border"
      style={{ background: '#fffbeb', borderColor: '#fcd34d' }}
    >
      <AlertTriangle size={16} className="shrink-0 mt-0.5" style={{ color: '#d97706' }} />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold" style={{ color: '#92400e' }}>
          回复发送当前处于关闭状态
        </div>
        <div className="text-xs mt-0.5" style={{ color: '#b45309' }}>
          系统目前只会生成回复候选和待审批计划，不会向真实社媒平台发送回复
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <button
          className="flex items-center gap-1 text-xs font-medium px-2.5 py-1.5 rounded-lg border transition-colors hover:bg-amber-100"
          style={{ borderColor: '#fcd34d', color: '#92400e' }}
          onClick={onViewSettings}
        >
          <Settings size={12} />
          查看安全设置
        </button>
        <button
          className="text-amber-400 hover:text-amber-600 transition-colors"
          onClick={() => setDismissed(true)}
        >
          <X size={14} />
        </button>
      </div>
    </div>
  )
}
