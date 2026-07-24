import type { TFunction } from "i18next";
import type { AppLocale } from "../i18n";

type BusinessGroup =
  | "executionStatus"
  | "campaignStatus"
  | "targetPolicy"
  | "scheduleType"
  | "loginStatus"
  | "connectionStatus"
  | "runtimeStatus"
  | "intentLevel"
  | "leadStatus"
  | "subscriptionStatus"
  | "invitationStatus"
  | "memberRole"
  | "notificationSeverity"
  | "triggerType"
  | "approvalMode"
  | "ownershipStatus"
  | "auditResource"
  | "auditAction"
  | "runtimeType"
  | "genericStatus";

export type BusinessFormatter = (value: unknown, t: TFunction) => string;

function formatBusinessValue(group: BusinessGroup, value: unknown, t: TFunction): string {
  const normalized = String(value || "unknown");
  return t(`business.${group}.${normalized}`, {
    defaultValue: t("business.unknown")
  });
}

export function formatExecutionStatus(value: unknown, t: TFunction) {
  return formatBusinessValue("executionStatus", value, t);
}

export function formatCampaignStatus(value: unknown, t: TFunction) {
  return formatBusinessValue("campaignStatus", value, t);
}

export function formatTargetPolicy(value: unknown, t: TFunction) {
  return formatBusinessValue("targetPolicy", value, t);
}

export function formatIntentLevel(value: unknown, t: TFunction) {
  return formatBusinessValue("intentLevel", value, t);
}

export function formatScheduleType(value: unknown, t: TFunction) {
  return formatBusinessValue("scheduleType", value, t);
}

export function formatLoginStatus(value: unknown, t: TFunction) {
  return formatBusinessValue("loginStatus", value, t);
}

export function formatConnectionStatus(value: unknown, t: TFunction) {
  return formatBusinessValue("connectionStatus", value, t);
}

export function formatRuntimeStatus(value: unknown, t: TFunction) {
  return formatBusinessValue("runtimeStatus", value, t);
}

export function formatLeadStatus(value: unknown, t: TFunction) {
  return formatBusinessValue("leadStatus", value, t);
}

export function formatSubscriptionStatus(value: unknown, t: TFunction) {
  return formatBusinessValue("subscriptionStatus", value, t);
}

export function formatInvitationStatus(value: unknown, t: TFunction) {
  return formatBusinessValue("invitationStatus", value, t);
}

export function formatMemberRole(value: unknown, t: TFunction) {
  return formatBusinessValue("memberRole", value, t);
}

export function formatNotificationSeverity(value: unknown, t: TFunction) {
  return formatBusinessValue("notificationSeverity", value, t);
}

export function formatNotificationTitle(type: unknown, t: TFunction): string {
  const normalized = String(type || "unknown");
  return t(`notification.type.${normalized}.title`, {
    defaultValue: t("notification.type.unknown.title")
  });
}

export function formatNotificationMessage(type: unknown, t: TFunction): string {
  const normalized = String(type || "unknown");
  return t(`notification.type.${normalized}.message`, {
    defaultValue: t("notification.type.unknown.message")
  });
}

export function formatTriggerType(value: unknown, t: TFunction) {
  return formatBusinessValue("triggerType", value, t);
}

export function formatApprovalMode(value: unknown, t: TFunction) {
  return formatBusinessValue("approvalMode", value, t);
}

export function formatOwnershipStatus(value: unknown, t: TFunction) {
  return formatBusinessValue("ownershipStatus", value, t);
}

export function formatAuditResource(value: unknown, t: TFunction) {
  return formatBusinessValue("auditResource", value, t);
}

export function formatAuditAction(value: unknown, t: TFunction) {
  return formatBusinessValue("auditAction", String(value || "unknown").replace(/\./g, "_"), t);
}

export function formatRuntimeType(value: unknown, t: TFunction) {
  return formatBusinessValue("runtimeType", value, t);
}

export function formatStatus(value: unknown, t: TFunction) {
  return formatBusinessValue("genericStatus", value, t);
}

export function businessOptions(values: readonly string[], formatter: BusinessFormatter, t: TFunction) {
  return values.map((value) => ({ value, label: formatter(value, t) }));
}

const semanticStatuses: Record<string, "Success" | "Processing" | "Warning" | "Error" | "Default"> = {
  active: "Success",
  accepted: "Success",
  completed: "Success",
  connected: "Success",
  logged_in: "Success",
  online: "Success",
  qualified: "Success",
  running: "Processing",
  starting: "Processing",
  queued: "Default",
  draft: "Default",
  pending: "Warning",
  retry_waiting: "Warning",
  login_required: "Warning",
  logged_out: "Warning",
  unknown: "Default",
  paused: "Warning",
  partial: "Warning",
  revoked: "Error",
  expired: "Error",
  blocked: "Error",
  failed: "Error",
  error: "Error",
  unhealthy: "Error",
  offline: "Error",
  stopped: "Default",
  cancelled: "Default",
  archived: "Default"
};

export function businessValueEnum(values: readonly string[], formatter: BusinessFormatter, t: TFunction) {
  return Object.fromEntries(values.map((value) => [
    value,
    { text: formatter(value, t), status: semanticStatuses[value] || "Default" }
  ]));
}

export function statusColor(value: unknown): string {
  const status = semanticStatuses[String(value || "unknown")] || "Default";
  return {
    Success: "green",
    Processing: "blue",
    Warning: "gold",
    Error: "red",
    Default: "default"
  }[status];
}

const englishDateFormatter = new Intl.DateTimeFormat("en-US", {
  year: "numeric",
  month: "short",
  day: "numeric"
});

const englishDateTimeFormatter = new Intl.DateTimeFormat("en-US", {
  year: "numeric",
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit"
});

const numberFormatters: Record<AppLocale, Intl.NumberFormat> = {
  "en-US": new Intl.NumberFormat("en-US"),
  "zh-CN": new Intl.NumberFormat("zh-CN")
};

type EmptyState = "none" | "notChecked" | "unknown";

export function formatEmpty(locale: AppLocale, state: EmptyState = "unknown"): string {
  const labels: Record<AppLocale, Record<EmptyState, string>> = {
    "zh-CN": {
      none: "暂无",
      notChecked: "未检查",
      unknown: "未知"
    },
    "en-US": {
      none: "None",
      notChecked: "Not checked",
      unknown: "Unknown"
    }
  };
  return labels[locale][state];
}

function parseDate(value: unknown): Date | null {
  if (!value) return null;
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? null : date;
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

export function formatDate(value: unknown, locale: AppLocale, emptyState: EmptyState = "unknown"): string {
  const date = parseDate(value);
  if (!date) return formatEmpty(locale, emptyState);
  if (locale === "zh-CN") {
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  }
  return englishDateFormatter.format(date);
}

export function formatDateTime(value: unknown, locale: AppLocale, emptyState: EmptyState = "unknown"): string {
  const date = parseDate(value);
  if (!date) return formatEmpty(locale, emptyState);
  if (locale === "zh-CN") {
    return `${formatDate(date, locale)} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
  }
  return englishDateTimeFormatter.format(date);
}

export function formatNumber(value: unknown, locale: AppLocale): string {
  const number = Number(value);
  return Number.isFinite(number) ? numberFormatters[locale].format(number) : formatEmpty(locale);
}
