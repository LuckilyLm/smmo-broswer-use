import {
  DeleteOutlined,
  EditOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  SettingOutlined,
  ThunderboltOutlined
} from "@ant-design/icons";
import {
  ModalForm,
  ProFormDigit,
  ProFormSelect,
  ProFormText,
  ProFormTextArea,
  ProTable,
  type ProColumns
} from "@ant-design/pro-components";
import { Alert, Button, Modal, Space, Tag, message } from "antd";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { apiDelete, apiPatch, apiPost, type ApiRecord } from "../api";
import { Page, ResourceState } from "../components/Page";
import { ScheduleDrawer } from "../components/ScheduleDrawer";
import { useResource } from "../hooks/useResource";
import type { AppLocale } from "../i18n";
import type { PaginatedResponse, UsageSummary } from "../types";
import {
  businessValueEnum,
  businessOptions,
  formatCampaignStatus,
  formatNumber,
  formatScheduleType,
  formatTargetPolicy
} from "../utils/formatters";

const emptyUsage: UsageSummary = {
  plan: { id: "", code: "", name: "", allow_scheduler: false, allow_multi_keyword: false, allow_advanced_reports: false },
  subscription: {},
  usage: {},
  limits: {},
  remaining: {}
};

export function CampaignsPage() {
  const { t, i18n } = useTranslation();
  const locale = (i18n.resolvedLanguage === "zh-CN" ? "zh-CN" : "en-US") as AppLocale;
  const campaigns = useResource<PaginatedResponse<ApiRecord>>("/api/campaigns?limit=100&offset=0", { items: [], limit: 100, offset: 0, total: 0 });
  const accounts = useResource<ApiRecord[]>("/api/platform-accounts", []);
  const usage = useResource<UsageSummary>("/api/usage/summary", emptyUsage);
  const [editing, setEditing] = useState<ApiRecord | null>(null);
  const [scheduleCampaign, setScheduleCampaign] = useState<ApiRecord | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [runningId, setRunningId] = useState("");
  const quotaReached = usage.data.remaining.monthly_executions === 0 || usage.data.remaining.monthly_tokens === 0;

  const columns: ProColumns<ApiRecord>[] = [
    { title: t("common.name"), dataIndex: "name", copyable: true },
    { title: t("common.status"), dataIndex: "status", valueType: "select", valueEnum: businessValueEnum(["active", "draft", "paused", "archived"], formatCampaignStatus, t) },
    { title: t("campaign.policy"), dataIndex: "target_policy", valueType: "select", valueEnum: businessValueEnum(["discovery_only", "owned_only", "allowlist"], formatTargetPolicy, t) },
    { title: t("campaign.comments"), dataIndex: "max_comments", hideInSearch: true, renderText: (value) => formatNumber(value, locale) },
    { title: t("campaign.confidence"), dataIndex: "min_confidence", hideInSearch: true, renderText: (value) => `${Math.round(Number(value || 0) * 100)}%` },
    {
      title: t("campaign.schedule"),
      hideInSearch: true,
      render: (_, row) => <Tag color={row.schedule?.enabled ? "blue" : "default"}>{formatScheduleType(row.schedule?.enabled ? row.schedule.schedule_type : "manual", t)}</Tag>
    },
    {
      title: t("common.actions"),
      valueType: "option",
      render: (_, row) => [
        <Button key="run" type="link" icon={<PlayCircleOutlined />} disabled={quotaReached} loading={runningId === row.id} onClick={async () => {
          setRunningId(String(row.id));
          try {
            await apiPost(`/api/campaigns/${row.id}/run`);
            message.success(t("campaign.runQueued"));
            campaigns.refresh();
          } finally {
            setRunningId("");
          }
        }}>{t("campaign.runOnce")}</Button>,
        <Button key="edit" type="link" icon={<EditOutlined />} onClick={() => setEditing(row)}>{t("common.edit")}</Button>,
        <Button key="schedule" type="link" icon={<SettingOutlined />} onClick={() => setScheduleCampaign(row)}>{t("campaign.schedule")}</Button>,
        <Button key="toggle" type="link" icon={row.status === "active" ? <PauseCircleOutlined /> : <ThunderboltOutlined />} onClick={() => apiPatch(`/api/campaigns/${row.id}`, { status: row.status === "active" ? "paused" : "active" }).then(campaigns.refresh)}>
          {row.status === "active" ? t("campaign.pause") : t("campaign.enable")}
        </Button>,
        <Button key="delete" type="link" danger icon={<DeleteOutlined />} onClick={() => Modal.confirm({
          title: `${t("common.delete")} ${row.name}?`,
          onOk: () => apiDelete(`/api/campaigns/${row.id}`).then(campaigns.refresh)
        })}>{t("common.delete")}</Button>
      ]
    }
  ];

  return (
    <Page
      title={t("nav.campaigns")}
      action={<Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>{t("common.create")}</Button>}
    >
      {quotaReached && <Alert className="quota-alert" type="warning" showIcon message={t("campaign.quotaReached")} />}
      <ResourceState loading={campaigns.loading} error={campaigns.error} empty={campaigns.data.items.length === 0} onRetry={campaigns.refresh}>
        <ProTable<ApiRecord>
          rowKey="id"
          search={{ labelWidth: "auto" }}
          pagination={{ pageSize: 10 }}
          dataSource={campaigns.data.items}
          columns={columns}
          options={{ reload: campaigns.refresh }}
          columnsState={{ persistenceKey: "leadflow-campaign-columns", persistenceType: "localStorage" }}
        />
      </ResourceState>
      <CampaignForm open={createOpen} accounts={accounts.data} onOpenChange={setCreateOpen} onSaved={campaigns.refresh} />
      <CampaignForm open={Boolean(editing)} campaign={editing} accounts={accounts.data} onOpenChange={(open) => !open && setEditing(null)} onSaved={campaigns.refresh} />
      <ScheduleDrawer campaign={scheduleCampaign} onClose={() => setScheduleCampaign(null)} onSaved={campaigns.refresh} />
    </Page>
  );
}

function CampaignForm({
  open,
  campaign,
  accounts,
  onOpenChange,
  onSaved
}: {
  open: boolean;
  campaign?: ApiRecord | null;
  accounts: ApiRecord[];
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  return (
    <ModalForm
      key={String(campaign?.id || "create")}
      title={campaign ? t("common.edit") : t("common.create")}
      open={open}
      onOpenChange={onOpenChange}
      initialValues={campaign || { status: "active", target_policy: "discovery_only", max_contents: 5, max_comments: 80, min_confidence: 0.9, max_leads: 5, daily_limit: 10 }}
      modalProps={{ destroyOnClose: true }}
      onFinish={async (values) => {
        if (campaign) {
          await apiPatch(`/api/campaigns/${campaign.id}`, values);
        } else {
          const created = await apiPost<ApiRecord>("/api/campaigns", values);
          const keywords = String(values.keywords || "").split("\n").map((item) => item.trim()).filter(Boolean);
          await Promise.all(keywords.map((keyword) => apiPost(`/api/campaigns/${created.id}/keywords`, { keyword, enabled: true, priority: 100 })));
        }
        message.success(campaign ? t("campaign.updated") : t("campaign.created"));
        onSaved();
        return true;
      }}
    >
      <ProFormText name="name" label={t("common.name")} rules={[{ required: true }]} />
      <ProFormSelect name="platform_account_id" label={t("nav.platforms")} disabled={Boolean(campaign)} rules={[{ required: !campaign }]} options={accounts.map((account) => ({ value: String(account.id), label: `${account.platform} - ${account.display_name}` }))} />
      <ProFormSelect name="status" label={t("common.status")} options={businessOptions(["active", "paused", "draft"], formatCampaignStatus, t)} />
      <ProFormSelect name="target_policy" label={t("campaign.targetPolicy")} options={businessOptions(["discovery_only", "owned_only", "allowlist"], formatTargetPolicy, t)} />
      <Space wrap>
        <ProFormDigit name="max_contents" label={t("campaign.contents")} min={1} max={20} />
        <ProFormDigit name="max_comments" label={t("campaign.comments")} min={1} max={300} />
        <ProFormDigit name="min_confidence" label={t("campaign.confidence")} min={0.1} max={1} fieldProps={{ step: 0.05 }} />
        <ProFormDigit name="max_leads" label={t("campaign.leadCap")} min={1} max={50} />
        <ProFormDigit name="daily_limit" label={t("campaign.dailyLimit")} min={1} max={100} />
      </Space>
      {!campaign && <ProFormTextArea name="keywords" label={t("nav.keywords")} rules={[{ required: true }]} fieldProps={{ rows: 4 }} />}
    </ModalForm>
  );
}
