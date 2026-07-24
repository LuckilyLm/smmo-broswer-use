import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Switch } from "antd";
import { useTranslation } from "react-i18next";
import { apiPatch, type ApiRecord } from "../api";
import { Page, ResourceState } from "../components/Page";
import { useResource } from "../hooks/useResource";
import { businessValueEnum, formatApprovalMode, formatIntentLevel } from "../utils/formatters";

export function ReplyRulesPage() {
  const { t } = useTranslation();
  const rules = useResource<ApiRecord[]>("/api/reply-rules", []);
  const columns: ProColumns<ApiRecord>[] = [
    { title: t("common.name"), dataIndex: "name", copyable: true },
    { title: t("common.intent"), dataIndex: "intent_type", valueType: "select", valueEnum: businessValueEnum(["high", "medium", "low", "unknown"], formatIntentLevel, t) },
    { title: t("campaign.confidence"), dataIndex: "min_confidence", valueType: "digit", hideInSearch: true },
    { title: t("common.approval"), dataIndex: "approval_mode", valueType: "select", valueEnum: businessValueEnum(["manual", "required", "auto"], formatApprovalMode, t) },
    { title: t("common.enabled"), dataIndex: "enabled", valueType: "switch", render: (_, row) => <Switch checked={Boolean(row.enabled)} onChange={(enabled) => apiPatch(`/api/reply-rules/${row.id}`, { enabled }).then(rules.refresh)} /> }
  ];
  return (
    <Page title={t("nav.replyRules")}>
      <ResourceState loading={rules.loading} error={rules.error} empty={rules.data.length === 0} onRetry={rules.refresh}>
        <ProTable rowKey="id" dataSource={rules.data} columns={columns} options={{ reload: rules.refresh }} pagination={{ pageSize: 20 }} />
      </ResourceState>
    </Page>
  );
}
