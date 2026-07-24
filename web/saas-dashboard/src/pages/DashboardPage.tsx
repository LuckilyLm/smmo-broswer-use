import { ReloadOutlined } from "@ant-design/icons";
import { ProCard, StatisticCard } from "@ant-design/pro-components";
import { Button, Progress, Tag } from "antd";
import { useTranslation } from "react-i18next";
import type { ApiRecord } from "../api";
import { DataList } from "../components/DataList";
import { Page, ResourceState } from "../components/Page";
import { useResource } from "../hooks/useResource";
import type { UsageSummary } from "../types";
import { formatNumber } from "../utils/formatters";
import type { AppLocale } from "../i18n";

const emptyUsage: UsageSummary = {
  plan: { id: "", code: "", name: "", allow_scheduler: false, allow_multi_keyword: false, allow_advanced_reports: false },
  subscription: {},
  usage: {},
  limits: {},
  remaining: {}
};

const statistics = [
  ["active_campaigns", "dashboard.activeCampaigns"],
  ["leads_today", "dashboard.leadsToday"],
  ["high_intent_leads", "dashboard.highIntent"],
  ["tokens_this_month", "dashboard.tokensMonth"],
  ["queued_tasks", "dashboard.queuedTasks"],
  ["running_tasks", "dashboard.runningTasks"],
  ["auto_tasks_today", "dashboard.autoTasksToday"],
  ["failed_tasks", "dashboard.failedTasks"]
] as const;

export function DashboardPage() {
  const { t, i18n } = useTranslation();
  const locale = (i18n.resolvedLanguage === "zh-CN" ? "zh-CN" : "en-US") as AppLocale;
  const summary = useResource<ApiRecord>("/api/dashboard/summary", {});
  const worker = useResource<ApiRecord>("/api/system/worker-status", {});
  const scheduler = useResource<ApiRecord>("/api/system/scheduler-status", {});
  const usage = useResource<UsageSummary>("/api/usage/summary", emptyUsage);
  return (
    <Page title={t("nav.dashboard")} loading={summary.loading} action={
      <Button aria-label={t("common.refresh")} icon={<ReloadOutlined />} loading={summary.loading} onClick={summary.refresh}>{t("common.refresh")}</Button>
    }>
      <ResourceState loading={false} error={summary.error} empty={false} onRetry={summary.refresh}>
        <ProCard className="plan-strip" title={t("dashboard.currentPlan")} extra={<Tag color="green">{usage.data.plan.name || "-"}</Tag>}>
          <div className="plan-meters">
            {(["monthly_executions", "monthly_tokens", "monthly_leads"] as const).map((key) => {
              const used = usage.data.usage[key] || 0;
              const limit = usage.data.limits[key];
              return <div key={key}><span>{t(`usage.${key.replace("monthly_", "")}`)}</span><Progress percent={limit ? Math.min(100, Math.round(used * 100 / limit)) : 0} format={() => `${formatNumber(used, locale)} / ${limit == null ? t("common.unlimited") : formatNumber(limit, locale)}`} /></div>;
            })}
          </div>
        </ProCard>
        <StatisticCard.Group className="dashboard-statistics">
          {statistics.map(([key, label]) => <StatisticCard key={key} statistic={{ title: t(label), value: formatNumber(summary.data[key] || 0, locale) }} />)}
          <StatisticCard statistic={{ title: t("dashboard.worker"), value: worker.data.online ? t("dashboard.online") : t("dashboard.offline"), status: worker.data.online ? "success" : "error" }} />
          <StatisticCard statistic={{ title: t("dashboard.scheduler"), value: scheduler.data.online ? t("dashboard.online") : t("dashboard.offline"), status: scheduler.data.online ? "success" : "error" }} />
        </StatisticCard.Group>
        <div className="wide-grid">
          <ProCard title={t("dashboard.recentExecutions")}><DataList rows={summary.data.recent_executions || []} fields={["run_id", "status", "selected_count"]} /></ProCard>
          <ProCard title={t("dashboard.latestLeads")}><DataList rows={summary.data.latest_leads || []} fields={["author_name", "final_intent_level", "status"]} /></ProCard>
        </div>
      </ResourceState>
    </Page>
  );
}
