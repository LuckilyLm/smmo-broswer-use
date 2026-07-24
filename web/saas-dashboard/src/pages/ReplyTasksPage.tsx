import { CheckOutlined, CloseOutlined, PlayCircleOutlined, ReloadOutlined } from "@ant-design/icons";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Alert, Button, Space, Tag, message } from "antd";
import { useTranslation } from "react-i18next";
import { apiPost, type ApiRecord } from "../api";
import { Page, ResourceState } from "../components/Page";
import { useResource } from "../hooks/useResource";

export function ReplyTasksPage() {
  const { t } = useTranslation();
  const candidates = useResource<{ items: ApiRecord[] }>("/api/reply-candidates?limit=100&offset=0", { items: [] });
  const plans = useResource<{ items: ApiRecord[] }>("/api/reply-plans?limit=100&offset=0", { items: [] });
  const summary = useResource<ApiRecord>("/api/dashboard/summary", {});
  const columns: ProColumns<ApiRecord>[] = [
    { title: t("lead.author"), dataIndex: "author_name", width: 160 },
    { title: t("lead.comment"), dataIndex: "comment_text", ellipsis: true },
    { title: t("reply.replyText"), dataIndex: "rendered_reply_text", ellipsis: true },
    { title: t("reply.rule"), dataIndex: "matched_rule_name" },
    { title: t("common.status"), dataIndex: "status", render: (_, row) => <Tag color={row.status === "approved" ? "green" : row.status === "blocked" ? "red" : "blue"}>{String(row.status)}</Tag> },
    {
      title: t("common.actions"),
      valueType: "option",
      render: (_, row) => [
        <Button key="approve" type="link" icon={<CheckOutlined />} disabled={row.status === "approved"} onClick={() => apiPost(`/api/reply-candidates/${row.id}/approve`).then(candidates.refresh)}>{t("reply.approve")}</Button>,
        <Button key="reject" type="link" danger icon={<CloseOutlined />} onClick={() => apiPost(`/api/reply-candidates/${row.id}/reject`, { reason: "manual_reject" }).then(candidates.refresh)}>{t("reply.reject")}</Button>
      ]
    }
  ];
  return (
    <Page title={t("nav.replyTasks")} action={<Button icon={<ReloadOutlined />} onClick={() => { candidates.refresh(); plans.refresh(); }}>{t("common.refresh")}</Button>}>
      {!summary.data.system_send_enabled && <Alert type="warning" showIcon message={String(summary.data.reply_safety_message || t("reply.sendOff"))} />}
      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <ResourceState loading={plans.loading} error={plans.error} empty={false} onRetry={plans.refresh}>
          <ProTable
            rowKey="id"
            search={false}
            headerTitle={t("reply.plans")}
            dataSource={plans.data.items}
            columns={[
              { title: t("nav.campaigns"), dataIndex: "campaign_id", copyable: true },
              { title: t("common.status"), dataIndex: "status" },
              { title: t("reply.mode"), dataIndex: "reply_mode" },
              { title: t("reply.totalCandidates"), dataIndex: "total_candidates" },
              { title: t("reply.blockedReason"), dataIndex: "blocked_reason" },
              { title: t("common.actions"), valueType: "option", render: (_, row) => [
                <Button key="approve" type="link" icon={<CheckOutlined />} onClick={() => apiPost(`/api/reply-plans/${row.id}/approve`).then(plans.refresh)}>{t("reply.approve")}</Button>,
                <Button key="execute" type="link" icon={<PlayCircleOutlined />} onClick={async () => { await apiPost(`/api/reply-plans/${row.id}/execute`); message.info(t("reply.executeGuarded")); plans.refresh(); }}>{t("reply.execute")}</Button>
              ] }
            ]}
            pagination={{ pageSize: 10 }}
          />
        </ResourceState>
        <ResourceState loading={candidates.loading} error={candidates.error} empty={candidates.data.items.length === 0} onRetry={candidates.refresh}>
          <ProTable rowKey="id" search={false} headerTitle={t("reply.candidates")} dataSource={candidates.data.items} columns={columns} pagination={{ pageSize: 20 }} />
        </ResourceState>
      </Space>
    </Page>
  );
}
