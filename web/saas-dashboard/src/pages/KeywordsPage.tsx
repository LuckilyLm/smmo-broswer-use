import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import { ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Input, Select, Space, Switch } from "antd";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { apiDelete, apiPatch, apiPost, type ApiRecord } from "../api";
import { Page, ResourceState } from "../components/Page";
import { useResource } from "../hooks/useResource";
import type { PaginatedResponse } from "../types";

export function KeywordsPage() {
  const { t } = useTranslation();
  const campaignPage = useResource<PaginatedResponse<ApiRecord>>("/api/campaigns?limit=100&offset=0", { items: [], limit: 100, offset: 0, total: 0 });
  const [campaignId, setCampaignId] = useState("");
  const [keyword, setKeyword] = useState("");
  const rows = useResource<ApiRecord[]>(campaignId ? `/api/campaigns/${campaignId}/keywords` : "", []);
  useEffect(() => { if (!campaignId && campaignPage.data.items[0]) setCampaignId(String(campaignPage.data.items[0].id)); }, [campaignId, campaignPage.data.items]);
  const columns: ProColumns<ApiRecord>[] = [
    { title: t("nav.keywords"), dataIndex: "keyword", copyable: true },
    { title: t("common.enabled"), dataIndex: "enabled", render: (_, row) => <Switch checked={Boolean(row.enabled)} onChange={(enabled) => apiPatch(`/api/keywords/${row.id}`, { enabled }).then(rows.refresh)} /> },
    { title: t("common.priority"), dataIndex: "priority", valueType: "digit" },
    { title: t("common.actions"), valueType: "option", render: (_, row) => <Button type="link" danger icon={<DeleteOutlined />} onClick={() => apiDelete(`/api/keywords/${row.id}`).then(rows.refresh)}>{t("common.delete")}</Button> }
  ];
  return (
    <Page title={t("nav.keywords")} action={
      <Space wrap>
        <Select value={campaignId} className="campaign-select" onChange={setCampaignId} options={campaignPage.data.items.map((item) => ({ value: String(item.id), label: String(item.name) }))} />
        <Input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder={t("nav.keywords")} />
        <Button type="primary" icon={<PlusOutlined />} disabled={!campaignId || !keyword.trim()} onClick={async () => {
          await apiPost(`/api/campaigns/${campaignId}/keywords`, { keyword: keyword.trim() });
          setKeyword("");
          rows.refresh();
        }}>{t("common.create")}</Button>
      </Space>
    }>
      <ResourceState loading={rows.loading} error={rows.error} empty={rows.data.length === 0} onRetry={rows.refresh}>
        <ProTable rowKey="id" search={false} options={{ reload: rows.refresh }} dataSource={rows.data} columns={columns} pagination={{ pageSize: 20 }} />
      </ResourceState>
    </Page>
  );
}
