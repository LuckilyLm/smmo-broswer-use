import type { CampaignTargetPolicy } from '../api/campaigns'

export function buildReplyPreflightWarnings({
  replyMode,
  targetPolicy,
  selectedTemplateId,
  selectedAccount,
  keywordCount,
  enabledRuleCount,
}: {
  replyMode: 'off' | 'manual' | 'auto'
  targetPolicy: CampaignTargetPolicy
  selectedTemplateId: string
  selectedAccount?: { login_status: string; connection_status: string; runtime_status: string }
  keywordCount: number
  enabledRuleCount: number
}) {
  if (replyMode === 'off') return []
  const warnings: string[] = []
  if (targetPolicy === 'discovery_only') warnings.push('当前为“仅发现”：系统会识别线索，但所有回复都会被来源策略阻止。')
  if (!selectedTemplateId) warnings.push('尚未绑定默认回复模板，且匹配规则可能无法生成回复内容。')
  if (enabledRuleCount === 0) warnings.push('当前活动没有已启用的匹配规则，请先配置规则再开启回复。')
  if (keywordCount === 0) warnings.push('尚未配置搜索关键词，活动无法发现目标内容。')
  if (!selectedAccount) warnings.push('尚未绑定平台账号。')
  else {
    if (selectedAccount.connection_status !== 'connected' || selectedAccount.login_status !== 'logged_in') warnings.push('绑定账号尚未连接并登录，请先完成账号检查。')
    if (selectedAccount.runtime_status !== 'running') warnings.push('绑定账号的浏览器运行时未运行，请先启动或重启运行时。')
  }
  return warnings
}
