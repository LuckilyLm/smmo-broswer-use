import { EyeOutlined } from "@ant-design/icons";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Descriptions, Drawer } from "antd";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Page, ResourceState } from "../components/Page";
import { useResource } from "../hooks/useResource";
import type { AuditLog, PaginatedResponse } from "../types";
import type { AppLocale } from "../i18n";
import {
  formatAuditAction,
  formatAuditResource,
  formatDateTime
} from "../utils/formatters";

export function AuditLogsPage() {
  const { t, i18n } = useTranslation();
  const locale = (i18n.resolvedLanguage === "zh-CN" ? "zh-CN" : "en-US") as AppLocale;
  const logs = useResource<PaginatedResponse<AuditLog & { metadata?: unknown }>>("/api/audit-logs?limit=200&offset=0", { items: [], limit: 200, offset: 0, total: 0 });
  const [selected, setSelected] = useState<(AuditLog & { metadata?: unknown }) | null>(null);
  const actorName = (row: AuditLog) => {
    if (row.user_display_name) return row.user_display_name;
    if (!row.user_id || ["scheduler", "startup", "worker"].includes(row.user_id)) return t("common.system");
    return t("audit.formerUser");
  };
  const columns: ProColumns<AuditLog & { metadata?: unknown }>[] = [
    { title: t("audit.time"), dataIndex: "created_at", sorter: (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(), renderText: (value) => formatDateTime(value, locale) },
    { title: t("audit.user"), dataIndex: "user_display_name", render: (_, row) => actorName(row) },
    { title: t("audit.action"), dataIndex: "action", renderText: (value) => formatAuditAction(value, t) },
    { title: t("audit.resource"), dataIndex: "resource_type", valueType: "select", renderText: (value) => formatAuditResource(value, t) },
    { title: t("common.actions"), valueType: "option", render: (_, row) => <Button type="link" icon={<EyeOutlined />} onClick={() => setSelected(row)}>{t("common.details")}</Button> }
  ];
  return (
    <Page title={t("nav.audit")} loading={logs.loading}>
      <ResourceState loading={false} error={logs.error} empty={logs.data.items.length === 0} onRetry={logs.refresh}>
        <ProTable rowKey="id" dataSource={logs.data.items} columns={columns} pagination={{ pageSize: 20 }} options={{ reload: logs.refresh }} search={{ labelWidth: "auto" }} />
      </ResourceState>
      <Drawer width={560} title={t("audit.metadata")} open={Boolean(selected)} onClose={() => setSelected(null)}>
        {selected && <Descriptions column={1} items={[
          { key: "time", label: t("audit.time"), children: formatDateTime(selected.created_at, locale) },
          { key: "user", label: t("audit.user"), children: actorName(selected) },
          { key: "action", label: t("audit.action"), children: formatAuditAction(selected.action, t) },
          { key: "resource", label: t("audit.resource"), children: formatAuditResource(selected.resource_type, t) },
          { key: "resourceId", label: t("audit.resourceId"), children: selected.resource_id || "-" },
          { key: "metadata", label: t("audit.metadata"), children: selected.metadata ? t("audit.detailsRecorded") : t("common.noData") }
        ]} />}
      </Drawer>
    </Page>
  );
}
