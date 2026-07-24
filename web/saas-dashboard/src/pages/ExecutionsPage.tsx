import { EyeOutlined, ReloadOutlined, StopOutlined } from "@ant-design/icons";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Progress } from "antd";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { apiPost, type ApiRecord } from "../api";
import { ExecutionDetailDrawer } from "../components/ExecutionDetailDrawer";
import { Page, ResourceState } from "../components/Page";
import { useResource } from "../hooks/useResource";
import type { PaginatedResponse } from "../types";
import { businessValueEnum, formatExecutionStatus, formatNumber, formatTriggerType } from "../utils/formatters";
import type { AppLocale } from "../i18n";

export function ExecutionsPage() {
  const { t, i18n } = useTranslation();
  const locale = (i18n.resolvedLanguage === "zh-CN" ? "zh-CN" : "en-US") as AppLocale;
  const executions = useResource<PaginatedResponse<ApiRecord>>("/api/executions?limit=100&offset=0", { items: [], limit: 100, offset: 0, total: 0 });
  const [selected, setSelected] = useState<ApiRecord | null>(null);
  useEffect(() => {
    if (!executions.data.items.some((row) => ["queued", "running", "pending", "retry_waiting"].includes(String(row.status)))) return;
    const timer = window.setInterval(executions.refresh, 3000);
    return () => window.clearInterval(timer);
  }, [executions.data.items, executions.refresh]);
  const columns: ProColumns<ApiRecord>[] = [
    { title: t("execution.trigger"), dataIndex: "trigger_type", valueType: "select", valueEnum: businessValueEnum(["manual", "scheduled", "retry"], formatTriggerType, t) },
    { title: t("common.status"), dataIndex: "status", valueType: "select", valueEnum: businessValueEnum(["queued", "running", "completed", "partial", "failed", "cancelled", "retry_waiting"], formatExecutionStatus, t) },
    { title: t("execution.progress"), hideInSearch: true, render: (_, row) => <Progress percent={Number(row.progress_percent || 0)} size="small" /> },
    { title: t("execution.keyword"), dataIndex: "current_keyword", ellipsis: true, hideInSearch: true, renderText: (value) => value || "-" },
    { title: t("execution.keywords"), hideInSearch: true, renderText: (_, row) => t("execution.failedSummary", { completed: formatNumber(row.completed_keywords || 0, locale), total: formatNumber(row.total_keywords || 0, locale), failed: formatNumber(row.failed_keywords || 0, locale) }) },
    { title: t("execution.tokens"), dataIndex: "total_tokens", hideInSearch: true, renderText: (value) => formatNumber(value, locale) },
    {
      title: t("common.actions"),
      valueType: "option",
      render: (_, row) => [
        <Button key="details" type="link" icon={<EyeOutlined />} onClick={() => setSelected(row)}>{t("common.details")}</Button>,
        ...( ["queued", "running"].includes(String(row.status)) ? [<Button key="cancel" type="link" danger icon={<StopOutlined />} onClick={() => apiPost(`/api/executions/${row.id}/cancel`).then(executions.refresh)}>{t("execution.cancel")}</Button>] : [])
      ]
    }
  ];
  return (
    <Page title={t("nav.executions")} loading={executions.loading} action={
      <Button aria-label={t("common.refresh")} icon={<ReloadOutlined />} loading={executions.loading} onClick={executions.refresh}>{t("common.refresh")}</Button>
    }>
      <ResourceState loading={false} error={executions.error} empty={executions.data.items.length === 0} onRetry={executions.refresh}>
        <ProTable rowKey="id" dataSource={executions.data.items} columns={columns} pagination={{ pageSize: 20 }} options={false} columnsState={{ persistenceKey: "leadflow-execution-columns", persistenceType: "localStorage" }} />
      </ResourceState>
      <ExecutionDetailDrawer execution={selected} onClose={() => setSelected(null)} />
    </Page>
  );
}
