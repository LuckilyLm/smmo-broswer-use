import { ProCard, StatisticCard } from "@ant-design/pro-components";
import { useTranslation } from "react-i18next";
import type { ApiRecord } from "../api";
import { DataList } from "../components/DataList";
import { Page, ResourceState } from "../components/Page";
import { useResource } from "../hooks/useResource";
import type { AppLocale } from "../i18n";
import { formatNumber } from "../utils/formatters";

export function TokenUsagePage() {
  const { t, i18n } = useTranslation();
  const locale = (i18n.resolvedLanguage === "zh-CN" ? "zh-CN" : "en-US") as AppLocale;
  const summary = useResource<ApiRecord>("/api/token-usage/summary", {});
  const details = useResource<ApiRecord>("/api/token-usage/details?limit=50&offset=0", { by_model: [], by_campaign: [] });
  const campaignRows = (details.data.by_campaign || []).map((row: ApiRecord) => ({
    ...row,
    campaign_name: row.campaign_name || t("business.unknown")
  }));
  return (
    <Page title={t("nav.tokenUsage")} loading={summary.loading}>
      <ResourceState loading={false} error={summary.error} empty={false} onRetry={summary.refresh}>
        <StatisticCard.Group>
          <StatisticCard statistic={{ title: t("tokenUsage.today"), value: formatNumber(summary.data.today || 0, locale) }} />
          <StatisticCard statistic={{ title: t("tokenUsage.last7Days"), value: formatNumber(summary.data.last_7_days || 0, locale) }} />
          <StatisticCard statistic={{ title: t("tokenUsage.thisMonth"), value: formatNumber(summary.data.this_month || 0, locale) }} />
        </StatisticCard.Group>
        <div className="wide-grid">
          <ProCard title={t("tokenUsage.byModel")}><DataList rows={details.data.by_model || []} fields={["model", "total_tokens"]} /></ProCard>
          <ProCard title={t("tokenUsage.byCampaign")}><DataList rows={campaignRows} fields={["campaign_name", "total_tokens"]} /></ProCard>
        </div>
      </ResourceState>
    </Page>
  );
}
