import { CheckCircleOutlined, CloseCircleOutlined } from "@ant-design/icons";
import { ProCard, StatisticCard } from "@ant-design/pro-components";
import { Descriptions, Progress } from "antd";
import { useTranslation } from "react-i18next";
import { Page, ResourceState } from "../components/Page";
import { StatusTag } from "../components/DataList";
import { useResource } from "../hooks/useResource";
import type { AppLocale } from "../i18n";
import type { UsageSummary } from "../types";
import { formatDate, formatNumber, formatSubscriptionStatus } from "../utils/formatters";

const resources = [
  ["monthly_executions", "usage.executions"],
  ["monthly_tokens", "usage.tokens"],
  ["monthly_leads", "usage.leads"],
  ["users", "usage.members"],
  ["platform_accounts", "usage.platforms"],
  ["campaigns", "usage.campaigns"]
] as const;

export function UsagePage() {
  const { t, i18n } = useTranslation();
  const locale = (i18n.resolvedLanguage === "zh-CN" ? "zh-CN" : "en-US") as AppLocale;
  const usage = useResource<UsageSummary>("/api/usage/summary", {
    plan: { id: "", code: "", name: "", allow_scheduler: false, allow_multi_keyword: false, allow_advanced_reports: false },
    subscription: {},
    usage: {},
    limits: {},
    remaining: {}
  });
  return (
    <Page title={t("nav.usage")} loading={usage.loading}>
      <ResourceState loading={false} error={usage.error} empty={!usage.data.plan.id} onRetry={usage.refresh}>
        <ProCard title={usage.data.plan.name} extra={<StatusTag value={usage.data.subscription.status || "active"} formatter={formatSubscriptionStatus} />}>
          <StatisticCard.Group className="usage-statistics">
            {resources.map(([key, label]) => {
              const used = usage.data.usage[key] || 0;
              const limit = usage.data.limits[key];
              const percent = limit ? Math.min(100, Math.round(used / limit * 100)) : 0;
              return <StatisticCard key={key} statistic={{ title: t(label), value: formatNumber(used, locale), suffix: limit == null ? t("common.unlimited") : `/ ${formatNumber(limit, locale)}` }} chart={limit != null ? <Progress percent={percent} showInfo={false} status={percent >= 100 ? "exception" : "normal"} /> : undefined} />;
            })}
          </StatisticCard.Group>
          <Descriptions className="usage-descriptions" title={t("usage.period")} column={{ xs: 1, sm: 2 }} items={[
            { key: "start", label: t("common.start"), children: formatDate(usage.data.subscription.current_period_start, locale) },
            { key: "end", label: t("common.end"), children: formatDate(usage.data.subscription.current_period_end, locale) }
          ]} />
          <Descriptions title={t("usage.features")} column={{ xs: 1, sm: 3 }} items={[
            ["scheduler", "usage.featureScheduler", usage.data.plan.allow_scheduler],
            ["multi_keyword", "usage.featureMultiKeyword", usage.data.plan.allow_multi_keyword],
            ["advanced_reports", "usage.featureAdvancedReports", usage.data.plan.allow_advanced_reports]
          ].map(([key, label, enabled]) => ({ key: String(key), label: t(String(label)), children: enabled ? <CheckCircleOutlined className="success-icon" /> : <CloseCircleOutlined className="muted" /> }))} />
        </ProCard>
      </ResourceState>
    </Page>
  );
}
