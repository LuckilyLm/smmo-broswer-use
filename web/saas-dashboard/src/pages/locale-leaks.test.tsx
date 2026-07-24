import { cleanup, render } from "@testing-library/react";
import { ConfigProvider } from "antd";
import enUS from "antd/locale/en_US";
import zhCN from "antd/locale/zh_CN";
import type { ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import i18n from "../i18n";
import { AuditLogsPage } from "./AuditLogsPage";
import { CampaignsPage } from "./CampaignsPage";
import { DashboardPage } from "./DashboardPage";
import { ExecutionsPage } from "./ExecutionsPage";
import { KeywordsPage } from "./KeywordsPage";
import { LeadsPage } from "./LeadsPage";
import { MembersPage } from "./MembersPage";
import { PlatformAccountsPage } from "./PlatformAccountsPage";
import { ReplyRulesPage } from "./ReplyRulesPage";
import { SettingsPage } from "./SettingsPage";
import { TokenUsagePage } from "./TokenUsagePage";
import { UsagePage } from "./UsagePage";

vi.mock("../hooks/useResource", () => ({
  useResource: (url: string, initial: unknown) => {
    const usage = {
      plan: {
        id: "plan-1",
        code: "pro",
        name: "Growth",
        allow_scheduler: true,
        allow_multi_keyword: true,
        allow_advanced_reports: false
      },
      subscription: {
        status: "trial",
        current_period_start: "2026-07-01T00:00:00",
        current_period_end: "2026-07-31T23:59:59"
      },
      usage: { monthly_executions: 1200, monthly_tokens: 987654, monthly_leads: 420, users: 5, platform_accounts: 1, campaigns: 1 },
      limits: { monthly_executions: 5000, monthly_tokens: 2000000, monthly_leads: 1000, users: 10, platform_accounts: 5, campaigns: 20 },
      remaining: { monthly_executions: 3800, monthly_tokens: 1012346, monthly_leads: 580 }
    };
    const campaign = {
      id: "campaign-1",
      name: "Massage Chair Leads",
      status: "active",
      target_policy: "discovery_only",
      max_comments: 1200,
      min_confidence: 0.85,
      schedule: { enabled: false, schedule_type: "manual" }
    };
    let data = initial;
    if (url.startsWith("/api/campaigns?")) data = { items: [campaign], limit: 100, offset: 0, total: 1 };
    else if (url === "/api/campaigns/campaign-1/keywords") data = [{ id: "keyword-1", keyword: "massage chair", enabled: true, priority: 1 }];
    else if (url === "/api/dashboard/summary") data = {
      active_campaigns: 1,
      leads_today: 1200,
      high_intent_leads: 320,
      tokens_this_month: 987654,
      queued_tasks: 2,
      running_tasks: 1,
      auto_tasks_today: 0,
      failed_tasks: 0,
      recent_executions: [{ run_id: "run-1", status: "retry_waiting", selected_count: 1200 }],
      latest_leads: [{ author_name: "Alice", final_intent_level: "high", status: "qualified" }]
    };
    else if (url === "/api/system/worker-status" || url === "/api/system/scheduler-status") data = { online: true };
    else if (url === "/api/usage/summary") data = usage;
    else if (url === "/api/platform-accounts") data = [{
      id: "account-1",
      display_name: "Facebook Sales Account",
      platform: "Facebook",
      connection_status: "connected",
      login_status: "error",
      last_login_check_at: "2026-07-01T14:30:00",
      runtime: { status: "running" }
    }];
    else if (url === "/api/system/runtime-capabilities") data = {
      runtime_host: "windows_host",
      runtime_available: true,
      browser_platform: "windows",
      local_browser_supported: true
    };
    else if (url.startsWith("/api/leads?")) data = {
      items: [{ id: "lead-1", author_name: "Alice", comment_text: "Interested in this product", final_intent_level: "high", status: "qualified", reply_allowed: true }],
      limit: 100,
      offset: 0,
      total: 1
    };
    else if (url === "/api/reply-rules") data = [{ id: "rule-1", name: "High intent review", intent_type: "high", min_confidence: 0.85, approval_mode: "required", enabled: true }];
    else if (url.startsWith("/api/executions?")) data = {
      items: [{ id: "execution-1", trigger_type: "scheduled", status: "retry_waiting", progress_percent: 50, current_keyword: "massage chair", completed_keywords: 1, total_keywords: 2, failed_keywords: 1, total_tokens: 12345 }],
      limit: 100,
      offset: 0,
      total: 1
    };
    else if (url === "/api/token-usage/summary") data = { today: 12345, last_7_days: 456789, this_month: 987654 };
    else if (url.startsWith("/api/token-usage/details")) data = {
      by_model: [{ model: "gpt-5", total_tokens: 456789 }],
      by_campaign: [{ campaign_id: "campaign-1", campaign_name: "Massage Chair Leads", total_tokens: 987654 }]
    };
    else if (url.startsWith("/api/tenant/members")) data = {
      items: [{ id: "membership-1", user_id: "user-1", display_name: "Alice", email: "alice@example.com", role: "owner", status: "inactive" }],
      limit: 200,
      offset: 0,
      total: 1
    };
    else if (url.startsWith("/api/tenant/invitations")) data = {
      items: [{ id: "invitation-1", email: "bob@example.com", role: "member", status: "pending", expires_at: "2026-07-31T23:59:59" }],
      limit: 200,
      offset: 0,
      total: 1
    };
    else if (url.startsWith("/api/audit-logs")) data = {
      items: [{ id: "audit-1", created_at: "2026-07-01T14:30:00", user_id: "user-1", user_display_name: "Alice", action: "api.patch", resource_type: "campaign", resource_id: "campaign-1" }],
      limit: 200,
      offset: 0,
      total: 1
    };
    else if (url === "/api/settings") data = {
      tenant: { name: "Sales Workspace", timezone: "Asia/Shanghai", default_target_policy: "discovery_only", default_min_confidence: 0.85, default_daily_limit: 1200 }
    };
    else if (url === "/api/version") data = { app_version: "7.6.2", git_commit: "abc1234", build_time: "2026-07-01T14:30:00" };
    return { data, loading: false, error: "", refresh: vi.fn() };
  }
}));

const pages: Array<[string, () => ReactElement]> = [
  ["dashboard", () => <DashboardPage />],
  ["platform accounts", () => <PlatformAccountsPage />],
  ["campaigns", () => <CampaignsPage />],
  ["keywords", () => <KeywordsPage />],
  ["leads", () => <LeadsPage />],
  ["reply rules", () => <ReplyRulesPage />],
  ["executions", () => <ExecutionsPage />],
  ["token usage", () => <TokenUsagePage />],
  ["plan usage", () => <UsagePage />],
  ["members", () => <MembersPage currentUserId="user-1" role="owner" />],
  ["audit logs", () => <AuditLogsPage />],
  ["settings", () => <SettingsPage />]
];

describe("rendered page locale safety", () => {
  afterEach(async () => {
    cleanup();
    await i18n.changeLanguage("en-US");
  });

  it.each(pages)("renders %s in English without Chinese or raw backend fields", async (_name, page) => {
    await i18n.changeLanguage("en-US");
    const text = render(<ConfigProvider locale={enUS}>{page()}</ConfigProvider>).container.textContent || "";
    expect(text).not.toMatch(/[\u3400-\u9fff]/);
    expect(text).not.toMatch(/\b(?:send_disabled|discovery_only|retry_waiting|past_due|user_id|campaign_id)\b/);
    expect(text).not.toMatch(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/);
  });

  it.each(pages)("renders %s in Chinese without known English copy leaks or raw backend fields", async (_name, page) => {
    await i18n.changeLanguage("zh-CN");
    const text = render(<ConfigProvider locale={zhCN}>{page()}</ConfigProvider>).container.textContent || "";
    expect(text.toLowerCase()).not.toMatch(/run id|selected count|author name|final intent level|campaign id|total tokens|multi keyword|advanced reports/);
    expect(text).not.toMatch(/\b(?:Runtime Host|Browser Runtime|Worker|Scheduler|CDP|PID|send_disabled|discovery_only|retry_waiting|past_due|user_id|campaign_id|snake_case)\b/);
    expect(text).not.toMatch(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/);
  });
});
