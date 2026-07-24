import { EyeOutlined, ReloadOutlined } from "@ant-design/icons";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button } from "antd";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { ApiRecord } from "../api";
import { LeadDetailDrawer } from "../components/LeadDetailDrawer";
import { Page, ResourceState } from "../components/Page";
import { useResource } from "../hooks/useResource";
import type { PaginatedResponse } from "../types";
import { businessValueEnum, formatIntentLevel, formatLeadStatus } from "../utils/formatters";

export function LeadsPage() {
  const { t } = useTranslation();
  const leads = useResource<PaginatedResponse<ApiRecord>>("/api/leads?limit=100&offset=0", { items: [], limit: 100, offset: 0, total: 0 });
  const [selected, setSelected] = useState<ApiRecord | null>(null);
  const columns: ProColumns<ApiRecord>[] = [
    { title: t("lead.author"), dataIndex: "author_name", copyable: true },
    { title: t("lead.comment"), dataIndex: "comment_text", ellipsis: true },
    { title: t("lead.intent"), dataIndex: "final_intent_level", valueType: "select", valueEnum: businessValueEnum(["high", "medium", "low", "unknown"], formatIntentLevel, t) },
    { title: t("common.status"), dataIndex: "status", valueType: "select", valueEnum: businessValueEnum(["new", "qualified", "blocked", "archived"], formatLeadStatus, t) },
    { title: t("lead.allowed"), dataIndex: "reply_allowed", valueType: "select", valueEnum: { true: { text: t("common.yes"), status: "Success" }, false: { text: t("common.no"), status: "Warning" } } },
    { title: t("common.actions"), valueType: "option", render: (_, row) => <Button type="link" icon={<EyeOutlined />} onClick={() => setSelected(row)}>{t("common.details")}</Button> }
  ];
  return (
    <Page title={t("nav.leads")} loading={leads.loading} action={<Button aria-label={t("common.refresh")} icon={<ReloadOutlined />} loading={leads.loading} onClick={leads.refresh}>{t("common.refresh")}</Button>}>
      <ResourceState loading={false} error={leads.error} empty={leads.data.items.length === 0} onRetry={leads.refresh}>
        <ProTable rowKey="id" dataSource={leads.data.items} columns={columns} pagination={{ pageSize: 20 }} options={false} columnsState={{ persistenceKey: "leadflow-lead-columns", persistenceType: "localStorage" }} />
      </ResourceState>
      <LeadDetailDrawer lead={selected} onClose={() => setSelected(null)} />
    </Page>
  );
}
