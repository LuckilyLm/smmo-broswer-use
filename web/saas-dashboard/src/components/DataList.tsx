import { Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import type { ApiRecord } from "../api";
import type { AppLocale } from "../i18n";
import {
  formatIntentLevel,
  formatNumber,
  formatStatus,
  statusColor,
  type BusinessFormatter
} from "../utils/formatters";

export function DataList({ rows, fields }: { rows: ApiRecord[]; fields: string[] }) {
  const { t, i18n } = useTranslation();
  const locale = (i18n.resolvedLanguage === "zh-CN" ? "zh-CN" : "en-US") as AppLocale;
  const columns: ColumnsType<ApiRecord> = useMemo(() => fields.map((field) => ({
    title: t(`field.${field}`, { defaultValue: t("common.unknown") }),
    dataIndex: field,
    render: (value) => {
      if (field === "status") return <StatusTag value={value} />;
      if (field === "final_intent_level") return formatIntentLevel(value, t);
      if (["selected_count", "total_tokens"].includes(field)) return formatNumber(value, locale);
      return value || "-";
    }
  })), [fields, locale, t]);
  return <Table size="small" rowKey={(row) => row.id || row.model || row.campaign_id || row.run_id} dataSource={rows} columns={columns} pagination={false} />;
}

export function StatusTag({ value, formatter = formatStatus }: { value: unknown; formatter?: BusinessFormatter }) {
  const { t } = useTranslation();
  return <Tag color={statusColor(value)}>{formatter(value, t)}</Tag>;
}
