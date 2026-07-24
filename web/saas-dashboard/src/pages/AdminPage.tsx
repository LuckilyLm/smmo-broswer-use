import { ProCard, ProTable, StatisticCard, type ProColumns } from "@ant-design/pro-components";
import { Button, Select } from "antd";
import { useTranslation } from "react-i18next";
import { apiPatch, type ApiRecord } from "../api";
import { Page, ResourceState } from "../components/Page";
import { useResource } from "../hooks/useResource";
import type { PaginatedResponse, Plan } from "../types";
import { businessValueEnum, formatNumber, formatSubscriptionStatus } from "../utils/formatters";
import type { AppLocale } from "../i18n";

export function AdminPage() {
  const { t, i18n } = useTranslation();
  const locale = (i18n.resolvedLanguage === "zh-CN" ? "zh-CN" : "en-US") as AppLocale;
  const tenants = useResource<PaginatedResponse<ApiRecord>>("/api/admin/tenants?limit=100&offset=0", { items: [], limit: 100, offset: 0, total: 0 });
  const plans = useResource<Plan[]>("/api/admin/plans", []);
  const usage = useResource<ApiRecord>("/api/admin/system/usage", {});
  const columns: ProColumns<ApiRecord>[] = [
    { title: t("nav.tenants"), dataIndex: "name", copyable: true },
    { title: t("common.status"), dataIndex: "status", valueType: "select", valueEnum: businessValueEnum(["trial", "active", "past_due", "suspended", "cancelled"], formatSubscriptionStatus, t) },
    { title: t("nav.plans"), dataIndex: ["plan", "code"], valueType: "select", render: (_, row) => <Select value={row.plan?.code} className="plan-select" options={plans.data.map((plan) => ({ value: plan.code, label: plan.name }))} onChange={(plan_code) => apiPatch(`/api/admin/tenants/${row.id}/subscription`, { plan_code }).then(tenants.refresh)} /> },
    { title: t("usage.executions"), hideInSearch: true, renderText: (_, row) => formatNumber(row.usage?.monthly_executions || 0, locale) },
    { title: t("common.actions"), valueType: "option", render: (_, row) => <Button type="link" danger={row.status === "active"} onClick={() => apiPatch(`/api/admin/tenants/${row.id}/subscription`, { plan_code: row.plan.code, tenant_status: row.status === "active" ? "suspended" : "active" }).then(tenants.refresh)}>{row.status === "active" ? t("common.suspend") : t("common.reactivate")}</Button> }
  ];
  return (
    <Page title={t("nav.adminDashboard")} loading={tenants.loading || usage.loading}>
      <ProCard>
        <StatisticCard.Group>
          <StatisticCard statistic={{ title: t("nav.tenants"), value: formatNumber(usage.data.tenants || 0, locale) }} />
          <StatisticCard statistic={{ title: t("common.users"), value: formatNumber(usage.data.users || 0, locale) }} />
          <StatisticCard statistic={{ title: t("usage.executions"), value: formatNumber(usage.data.executions || 0, locale) }} />
          <StatisticCard statistic={{ title: t("usage.tokens"), value: formatNumber(usage.data.tokens || 0, locale) }} />
        </StatisticCard.Group>
      </ProCard>
      <ResourceState loading={false} error={tenants.error} empty={tenants.data.items.length === 0} onRetry={tenants.refresh}>
        <ProTable rowKey="id" dataSource={tenants.data.items} columns={columns} pagination={{ pageSize: 20 }} options={{ reload: tenants.refresh }} search={{ labelWidth: "auto" }} />
      </ResourceState>
    </Page>
  );
}
