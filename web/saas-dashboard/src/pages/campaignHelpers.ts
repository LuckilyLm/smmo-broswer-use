import type { Execution } from '../api/executions'

export function campaignStatusLabel(status: string) {
  return ({ active: '已启用', paused: '已暂停', draft: '草稿', archived: '已归档', error: '异常' } as Record<string, string>)[status] || status
}

export function executionStatusLabel(status?: string) {
  if (!status) return '尚未执行'
  return ({ queued: '排队中', running: '执行中', completed: '已完成', partial: '部分完成', failed: '失败', cancelled: '已取消' } as Record<string, string>)[status] || status
}

export function latestExecutionsByCampaign(executions: Execution[]) {
  return executions.reduce<Record<string, Execution>>((latest, execution) => {
    const previous = latest[execution.campaign_id]
    const timestamp = Date.parse(execution.created_at || execution.started_at || '') || 0
    const previousTimestamp = previous ? Date.parse(previous.created_at || previous.started_at || '') || 0 : -1
    if (!previous || timestamp > previousTimestamp) latest[execution.campaign_id] = execution
    return latest
  }, {})
}
