import { Descriptions, Drawer, Progress, Space, Table, Tabs } from "antd";
import type { ApiRecord } from "../api";
import { useResource } from "../hooks/useResource";
import { StatusTag } from "./DataList";
import { useTranslation } from "react-i18next";
import type { AppLocale } from "../i18n";
import {
  formatExecutionStatus,
  formatNumber,
  formatTriggerType
} from "../utils/formatters";

export function ExecutionDetailDrawer({ execution, onClose }: { execution: ApiRecord | null; onClose: () => void }) {
  const { t, i18n } = useTranslation();
  const locale = (i18n.resolvedLanguage === "zh-CN" ? "zh-CN" : "en-US") as AppLocale;
  const { data: fresh } = useResource<ApiRecord>(execution ? `/api/executions/${execution.id}` : "", execution || {});
  const { data: keywords } = useResource<ApiRecord[]>(execution ? `/api/executions/${execution.id}/keywords` : "", []);
  const row = fresh.id ? fresh : execution;
  return (
    <Drawer open={Boolean(execution)} width={760} title={t("detail.execution")} onClose={onClose}>
      {row && <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <Descriptions column={2} bordered size="small" items={[
          { key: "trigger", label: t("execution.trigger"), children: formatTriggerType(row.trigger_type, t) },
          { key: "status", label: t("common.status"), children: <StatusTag value={row.status} formatter={formatExecutionStatus} /> },
          { key: "progress", label: t("execution.progress"), children: <Progress percent={Number(row.progress_percent || 0)} size="small" /> },
          { key: "current", label: t("detail.currentKeyword"), children: row.current_keyword || "-" },
          { key: "ok", label: t("detail.completedKeywords"), children: formatNumber(row.completed_keywords || 0, locale) },
          { key: "failed", label: t("detail.failedKeywords"), children: formatNumber(row.failed_keywords || 0, locale) },
          { key: "tokens", label: t("field.total_tokens"), children: formatNumber(row.total_tokens || 0, locale) },
          { key: "elapsed", label: t("detail.elapsed"), children: row.elapsed_ms ? t("detail.seconds", { seconds: formatNumber(Math.round(Number(row.elapsed_ms) / 1000), locale) }) : "-" }
        ]} />
        <Tabs items={[{ key: "keywords", label: t("nav.keywords"), children: <Table<ApiRecord> size="small" rowKey="id" dataSource={keywords} pagination={false} columns={[
          { title: t("nav.keywords"), dataIndex: "keyword" },
          { title: t("detail.attempt"), dataIndex: "attempt_number", render: (value) => formatNumber(value, locale) },
          { title: t("common.status"), dataIndex: "status", render: (value) => <StatusTag value={value} formatter={formatExecutionStatus} /> },
          { title: t("campaign.comments"), dataIndex: "scanned_comments", render: (value) => formatNumber(value, locale) },
          { title: t("usage.leads"), dataIndex: "lead_candidates", render: (value) => formatNumber(value, locale) },
          { title: t("usage.tokens"), dataIndex: "total_tokens", render: (value) => formatNumber(value, locale) },
          { title: t("detail.elapsed"), dataIndex: "elapsed_ms", render: (value) => value ? t("detail.seconds", { seconds: formatNumber(Math.round(Number(value) / 1000), locale) }) : "-" },
          { title: t("detail.error"), dataIndex: "error_message", ellipsis: true, render: (value) => value ? t("detail.executionError") : "-" }
        ]} /> }]} />
      </Space>}
    </Drawer>
  );
}
