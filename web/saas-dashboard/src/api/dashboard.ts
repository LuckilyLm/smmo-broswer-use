import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./client";

export type DashboardRange = "7d" | "14d" | "30d";

interface RawCampaignPerformance {
  campaign_id?: string;
  campaign_name?: string;
  platform?: string;
  status?: string;
  lead_count?: number;
  pending_reply_count?: number;
  last_execution_at?: string | null;
}

interface RawExecution {
  id?: string;
  execution_id?: string;
  campaign_id?: string;
  campaign_name?: string;
  status?: string;
  scanned_comments?: number;
  comments_scanned?: number;
  lead_candidates?: number;
  leads_found?: number;
}

interface RawPlatformStatus {
  account_id?: string;
  platform?: string;
  display_name?: string;
  handle?: string;
  connection_status?: string;
  login_status?: string | null;
  runtime_status?: string | null;
}

interface RawPendingReply {
  id?: string;
  campaign_id?: string;
  campaign_name?: string;
  author_name?: string;
  author?: string;
  comment_text?: string;
  original_comment?: string;
  matched_rule_name?: string;
  matched_keyword?: string;
  rendered_reply_text?: string;
  reply_preview?: string;
  created_at?: string;
}

interface RawDashboardResponse {
  active_campaigns?: number;
  connected_platform_accounts?: number;
  connected_accounts?: number;
  comments_scanned_today?: number;
  leads_today?: number;
  high_intent_leads?: number;
  pending_replies?: number;
  today_replied?: number;
  failed_tasks_today?: number;
  today_failed?: number;
  tokens_today?: number;
  tokens_this_month?: number;
  system_send_enabled?: boolean;
  reply_safety_message?: string;
  lead_trend?: Array<{ date?: string; day?: string; leads?: number; comments_scanned?: number; scanned?: number }>;
  intent_distribution?: Array<{ name?: string; value?: number; color?: string; intent_level?: string; count?: number }>;
  campaign_performance?: RawCampaignPerformance[];
  recent_executions?: RawExecution[];
  pending_reply_items?: RawPendingReply[];
  pending_replies_list?: RawPendingReply[];
  platform_status?: RawPlatformStatus[];
}

export interface DashboardSummary {
  active_campaigns: number;
  connected_accounts: number;
  comments_scanned_today: number;
  leads_today: number;
  high_intent_leads: number;
  pending_replies: number;
  today_replied: number;
  failed_tasks_today: number;
  tokens_today: number;
  tokens_this_month: number;
  system_send_enabled: boolean;
  reply_safety_message: string;
  lead_trend: Array<{ day: string; leads: number; scanned: number }>;
  intent_distribution: Array<{ name: string; value: number; color: string }>;
  campaign_performance: Array<{ id: string; name: string; platform: string; status: string; leads: number; pending: number; lastRun: string }>;
  recent_executions: Array<{ id: string; campaign: string; status: string; comments: number; leads: number }>;
  pending_replies_list: Array<{ id: string; author: string; comment: string; keyword: string; preview: string; campaign: string; time: string }>;
  platform_status: Array<{ id: string; name: string; displayName: string; handle: string; connectionStatus: string; loginStatus: string; runtimeStatus: string }>;
}

const intentColors: Record<string, string> = {
  high: "#ef4444",
  medium: "#f59e0b",
  low: "#4a6fa5",
  unknown: "#94a3b8",
};

const intentLabels: Record<string, string> = {
  high: "高意向",
  medium: "中意向",
  low: "低意向",
  unknown: "未知",
};

function mapDefined<T, U>(items: T[], transform: (item: T) => U | undefined): U[] {
  const result: U[] = [];
  items.forEach((item) => {
    const transformed = transform(item);
    if (transformed !== undefined) result.push(transformed);
  });
  return result;
}

function safeNumber(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

const dashboardDateTimeFormatter = new Intl.DateTimeFormat("zh-CN", {
  year: "numeric",
  month: "numeric",
  day: "numeric",
  hour: "numeric",
  minute: "numeric",
  second: "numeric",
});

function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : dashboardDateTimeFormatter.format(date);
}

export function normalizeDashboardData(raw: RawDashboardResponse | null | undefined): DashboardSummary {
  const source = raw || {};
  const pendingItems = Array.isArray(source.pending_reply_items)
    ? source.pending_reply_items
    : Array.isArray(source.pending_replies_list) ? source.pending_replies_list : [];

  return {
    active_campaigns: safeNumber(source.active_campaigns),
    connected_accounts: safeNumber(source.connected_accounts ?? source.connected_platform_accounts),
    comments_scanned_today: safeNumber(source.comments_scanned_today),
    leads_today: safeNumber(source.leads_today),
    high_intent_leads: safeNumber(source.high_intent_leads),
    pending_replies: safeNumber(source.pending_replies),
    today_replied: safeNumber(source.today_replied),
    failed_tasks_today: safeNumber(source.failed_tasks_today ?? source.today_failed),
    tokens_today: safeNumber(source.tokens_today),
    tokens_this_month: safeNumber(source.tokens_this_month),
    system_send_enabled: source.system_send_enabled === true,
    reply_safety_message: source.reply_safety_message || "",
    lead_trend: mapDefined(Array.isArray(source.lead_trend) ? source.lead_trend : [], (item) => {
      const day = String(item.day || item.date || "");
      return day ? {
        day,
        leads: safeNumber(item.leads),
        scanned: safeNumber(item.scanned ?? item.comments_scanned),
      } : undefined;
    }),
    intent_distribution: mapDefined(Array.isArray(source.intent_distribution) ? source.intent_distribution : [], (item) => {
      const key = String(item.intent_level || item.name || "unknown").toLowerCase();
      const value = safeNumber(item.value ?? item.count);
      return value > 0 ? {
        name: item.name || intentLabels[key] || intentLabels.unknown,
        value,
        color: item.color || intentColors[key] || intentColors.unknown,
      } : undefined;
    }),
    campaign_performance: (Array.isArray(source.campaign_performance) ? source.campaign_performance : []).map((item) => ({
      id: item.campaign_id || item.campaign_name || "",
      name: item.campaign_name || "未命名活动",
      platform: item.platform || "unknown",
      status: item.status || "unknown",
      leads: safeNumber(item.lead_count),
      pending: safeNumber(item.pending_reply_count),
      lastRun: formatDateTime(item.last_execution_at),
    })),
    recent_executions: (Array.isArray(source.recent_executions) ? source.recent_executions : []).map((item) => ({
      id: item.id || item.execution_id || "—",
      campaign: item.campaign_name || (item.campaign_id ? `活动 ${item.campaign_id.slice(0, 8)}` : "未知活动"),
      status: item.status || "unknown",
      comments: safeNumber(item.scanned_comments ?? item.comments_scanned),
      leads: safeNumber(item.lead_candidates ?? item.leads_found),
    })),
    pending_replies_list: pendingItems.map((item) => ({
      id: item.id || `${item.campaign_id || "reply"}-${item.created_at || ""}`,
      author: item.author_name || item.author || "未知作者",
      comment: item.comment_text || item.original_comment || "",
      keyword: item.matched_rule_name || item.matched_keyword || "—",
      preview: item.rendered_reply_text || item.reply_preview || "",
      campaign: item.campaign_name || (item.campaign_id ? `活动 ${item.campaign_id.slice(0, 8)}` : "未知活动"),
      time: formatDateTime(item.created_at),
    })),
    platform_status: (Array.isArray(source.platform_status) ? source.platform_status : []).map((item) => ({
      id: item.account_id || item.display_name || item.platform || "",
      name: item.platform || "unknown",
      displayName: item.display_name || item.handle || "未命名账号",
      handle: item.handle || "",
      connectionStatus: item.connection_status || "unknown",
      loginStatus: item.login_status || "unknown",
      runtimeStatus: item.runtime_status || "unknown",
    })),
  };
}

export function useDashboardSummary(range: DashboardRange = "7d") {
  return useQuery({
    queryKey: ["dashboard", "summary", range],
    queryFn: async () => normalizeDashboardData(await apiGet<RawDashboardResponse>(`/api/dashboard/summary?range=${range}`)),
    staleTime: 30 * 1000,
    refetchInterval: 60 * 1000,
  });
}
