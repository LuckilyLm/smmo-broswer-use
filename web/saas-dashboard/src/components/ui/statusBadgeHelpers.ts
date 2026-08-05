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
