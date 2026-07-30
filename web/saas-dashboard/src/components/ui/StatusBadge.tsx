interface StatusBadgeProps {
  status: string
  label?: string
  variant?: 'default' | 'dot'
}

const statusConfig: Record<string, { bg: string; text: string; dot: string }> = {
  // Campaign statuses
  'active': { bg: '#dcfce7', text: '#15803d', dot: '#16a34a' },
  'paused': { bg: '#fef9c3', text: '#a16207', dot: '#ca8a04' },
  'draft': { bg: '#f3f4f6', text: '#4b5563', dot: '#9ca3af' },
  'archived': { bg: '#f3f4f6', text: '#9ca3af', dot: '#d1d5db' },
  // Reply mode
  'disabled': { bg: '#f3f4f6', text: '#4b5563', dot: '#9ca3af' },
  'manual_approval': { bg: '#eff6ff', text: '#1d4ed8', dot: '#3b82f6' },
  'automatic': { bg: '#fef3c7', text: '#d97706', dot: '#f59e0b' },
  // Connection / Login statuses
  'connected': { bg: '#dcfce7', text: '#15803d', dot: '#16a34a' },
  'logged_in': { bg: '#dcfce7', text: '#15803d', dot: '#16a34a' },
  'login_required': { bg: '#fee2e2', text: '#dc2626', dot: '#ef4444' },
  'not_connected': { bg: '#f3f4f6', text: '#4b5563', dot: '#9ca3af' },
  // Runtime
  'running': { bg: '#dbeafe', text: '#1d4ed8', dot: '#3b82f6' },
  'starting': { bg: '#dbeafe', text: '#1d4ed8', dot: '#3b82f6' },
  'stopped': { bg: '#f3f4f6', text: '#4b5563', dot: '#9ca3af' },
  'unhealthy': { bg: '#fee2e2', text: '#dc2626', dot: '#ef4444' },
  // Reply records
  'sent': { bg: '#dcfce7', text: '#15803d', dot: '#16a34a' },
  'verified': { bg: '#dbeafe', text: '#1d4ed8', dot: '#3b82f6' },
  'failed': { bg: '#fee2e2', text: '#dc2626', dot: '#ef4444' },
  'blocked': { bg: '#fef3c7', text: '#d97706', dot: '#f59e0b' },
  // Tasks
  'pending_approval': { bg: '#fef9c3', text: '#a16207', dot: '#ca8a04' },
  'approved': { bg: '#dcfce7', text: '#15803d', dot: '#16a34a' },
  'executed': { bg: '#f0fdf4', text: '#15803d', dot: '#16a34a' },
  'rejected': { bg: '#fee2e2', text: '#dc2626', dot: '#ef4444' },
  'completed': { bg: '#f0fdf4', text: '#15803d', dot: '#16a34a' },
  'cancelled': { bg: '#f3f4f6', text: '#4b5563', dot: '#9ca3af' },
  // Execution
  'queued': { bg: '#f3f4f6', text: '#4b5563', dot: '#9ca3af' },
  'partial': { bg: '#fef3c7', text: '#d97706', dot: '#f59e0b' },
  'retry_waiting': { bg: '#fef9c3', text: '#a16207', dot: '#ca8a04' },
  // Intent
  'high': { bg: '#fee2e2', text: '#dc2626', dot: '#ef4444' },
  'medium': { bg: '#fef9c3', text: '#a16207', dot: '#ca8a04' },
  'low': { bg: '#f3f4f6', text: '#4b5563', dot: '#9ca3af' },
  'unknown': { bg: '#f3f4f6', text: '#9ca3af', dot: '#d1d5db' },
}

const statusLabels: Record<string, string> = {
  active: '运行中', paused: '已暂停', draft: '草稿', archived: '已归档',
  disabled: '已关闭', manual_approval: '人工审批', automatic: '自动执行',
  connected: '已连接', logged_in: '已登录', login_required: '需要登录', not_connected: '未连接',
  running: '运行中', starting: '启动中', stopped: '已停止', unhealthy: '异常',
  sent: '已发送', verified: '已验证', failed: '失败', blocked: '已阻止',
  pending_approval: '待审批', approved: '已批准', executed: '已执行', rejected: '已拒绝', completed: '已完成', cancelled: '已取消',
  queued: '排队中', partial: '部分完成', retry_waiting: '等待重试',
  high: '高意向', medium: '中意向', low: '低意向', unknown: '未知', error: '异常',
}

export function getStatusLabel(status: string) {
  return statusLabels[status] || status
}

export default function StatusBadge({ status, label, variant = 'default' }: StatusBadgeProps) {
  const config = statusConfig[status] ?? { bg: '#f3f4f6', text: '#374151', dot: '#9ca3af' }
  return (
    <span
      className="inline-flex items-center gap-1 whitespace-nowrap px-2 py-0.5 rounded text-xs font-medium"
      style={{ background: config.bg, color: config.text }}
    >
      {variant === 'dot' && (
        <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: config.dot }} />
      )}
      {label || getStatusLabel(status)}
    </span>
  )
}
