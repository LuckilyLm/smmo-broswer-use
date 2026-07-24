import { afterEach, describe, expect, it } from "vitest";
import i18n from "../i18n";
import {
  formatApprovalMode,
  formatAuditAction,
  formatAuditResource,
  formatCampaignStatus,
  formatConnectionStatus,
  formatDate,
  formatDateTime,
  formatEmpty,
  formatExecutionStatus,
  formatIntentLevel,
  formatInvitationStatus,
  formatLeadStatus,
  formatLoginStatus,
  formatMemberRole,
  formatNotificationSeverity,
  formatNumber,
  formatOwnershipStatus,
  formatRuntimeStatus,
  formatRuntimeType,
  formatScheduleType,
  formatStatus,
  formatSubscriptionStatus,
  formatTargetPolicy,
  formatTriggerType
} from "./formatters";

describe("business value formatters", () => {
  afterEach(async () => {
    await i18n.changeLanguage("en-US");
  });

  it("translates customer-facing enum values in both locales", async () => {
    await i18n.changeLanguage("zh-CN");
    expect(formatExecutionStatus("retry_waiting", i18n.t)).toBe("等待重试");
    expect(formatCampaignStatus("active", i18n.t)).toBe("启用");
    expect(formatTargetPolicy("discovery_only", i18n.t)).toBe("仅发现线索");
    expect(formatIntentLevel("high", i18n.t)).toBe("高意向");

    await i18n.changeLanguage("en-US");
    expect(formatExecutionStatus("retry_waiting", i18n.t)).toBe("Waiting to retry");
    expect(formatCampaignStatus("active", i18n.t)).toBe("Active");
    expect(formatTargetPolicy("discovery_only", i18n.t)).toBe("Discovery only");
    expect(formatIntentLevel("high", i18n.t)).toBe("High intent");
  });

  it("covers every customer-facing enum domain and known backend value", async () => {
    await i18n.changeLanguage("en-US");
    const cases: Array<[string[], (value: unknown, t: typeof i18n.t) => string]> = [
      [["queued", "running", "completed", "partial", "failed", "cancelled", "retry_waiting"], formatExecutionStatus],
      [["active", "draft", "paused", "archived"], formatCampaignStatus],
      [["discovery_only", "owned_only", "allowlist"], formatTargetPolicy],
      [["manual", "interval", "daily"], formatScheduleType],
      [["logged_in", "logged_out", "login_required", "checkpoint", "captcha", "error"], formatLoginStatus],
      [["connected", "not_connected", "login_required", "error"], formatConnectionStatus],
      [["starting", "running", "stopped", "unhealthy", "error"], formatRuntimeStatus],
      [["high", "medium", "low"], formatIntentLevel],
      [["new", "qualified", "blocked", "archived"], formatLeadStatus],
      [["trial", "active", "past_due", "suspended", "cancelled", "expired"], formatSubscriptionStatus],
      [["pending", "accepted", "revoked", "expired"], formatInvitationStatus],
      [["owner", "admin", "member", "viewer"], formatMemberRole],
      [["error", "warning", "info", "success"], formatNotificationSeverity],
      [["manual", "scheduled", "retry"], formatTriggerType],
      [["manual", "required", "auto"], formatApprovalMode],
      [["owned", "allowlisted", "discovered", "third_party"], formatOwnershipStatus],
      [["tenant", "membership", "invitation", "campaign", "platform_account", "subscription", "execution", "plan", "quota", "session", "user", "api"], formatAuditResource],
      [["admin.plan_create", "member.invite", "auth.login_success", "api.post", "api.put", "api.patch", "api.delete"], formatAuditAction],
      [["local", "local_chrome_cdp", "windows_host"], formatRuntimeType],
      [["active", "inactive", "completed", "connected", "online", "running", "queued", "pending", "paused", "blocked", "failed", "offline"], formatStatus]
    ];

    for (const [values, formatter] of cases) {
      for (const value of values) expect(formatter(value, i18n.t), value).not.toBe("Unknown");
    }
  });

  it("formats dates, date-times, and numbers for the selected locale", () => {
    const value = "2026-07-01T14:30:00";

    expect(formatDate(value, "zh-CN")).toBe("2026-07-01");
    expect(formatDateTime(value, "zh-CN")).toBe("2026-07-01 14:30");
    expect(formatDate(value, "en-US")).toBe("Jul 1, 2026");
    expect(formatDateTime(value, "en-US")).toBe("Jul 1, 2026, 2:30 PM");
    expect(formatNumber(1234567, "en-US")).toBe("1,234,567");
    expect(formatDateTime("not-a-date", "zh-CN")).toBe("未知");
    expect(formatDateTime("", "zh-CN", "notChecked")).toBe("未检查");
    expect(formatNumber("not-a-number", "en-US")).toBe("Unknown");
    expect(formatEmpty("zh-CN", "none")).toBe("暂无");
  });
});
