import { ReloadOutlined } from "@ant-design/icons";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Tag } from "antd";
import { useTranslation } from "react-i18next";
import type { ApiRecord } from "../api";
import { Page, ResourceState } from "../components/Page";
import { useResource } from "../hooks/useResource";

export function ReplyRecordsPage() {
  const { t } = useTranslation();
  const records = useResource<{ items: ApiRecord[] }>("/api/reply-records?limit=100&offset=0", { items: [] });
  const columns: ProColumns<ApiRecord>[] = [
    { title: t("nav.campaigns"), dataIndex: "campaign_id", copyable: true },
    { title: t("reply.commentId"), dataIndex: "comment_id", copyable: true },
    { title: t("reply.replyText"), dataIndex: "reply_text", ellipsis: true },
    { title: t("common.status"), dataIndex: "status", render: (_, row) => <Tag color={row.status === "sent" ? "green" : row.status === "blocked" ? "orange" : "red"}>{String(row.status)}</Tag> },
    { title: t("reply.blockedReason"), dataIndex: "error_type" },
    { title: t("audit.time"), dataIndex: "created_at", valueType: "dateTime" }
  ];
  return (
    <Page title={t("nav.replyRecords")} action={<Button icon={<ReloadOutlined />} onClick={records.refresh}>{t("common.refresh")}</Button>}>
      <ResourceState loading={records.loading} error={records.error} empty={records.data.items.length === 0} onRetry={records.refresh}>
        <ProTable rowKey="id" search={false} dataSource={records.data.items} columns={columns} pagination={{ pageSize: 20 }} options={{ reload: records.refresh }} />
      </ResourceState>
    </Page>
  );
}
