import { DeleteOutlined, EditOutlined, PlusOutlined, ExperimentOutlined } from "@ant-design/icons";
import { ModalForm, ProFormDigit, ProFormSelect, ProFormSwitch, ProFormText, ProFormTextArea, ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Modal, Space, Tag, message } from "antd";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { apiDelete, apiPatch, apiPost, type ApiRecord } from "../api";
import { Page, ResourceState } from "../components/Page";
import { useResource } from "../hooks/useResource";

export function ReplyMatchRulesPage() {
  const { t } = useTranslation();
  const rules = useResource<ApiRecord[]>("/api/reply-match-rules", []);
  const campaigns = useResource<{ items: ApiRecord[] }>("/api/campaigns?limit=100&offset=0", { items: [] });
  const templates = useResource<ApiRecord[]>("/api/reply-templates", []);
  const [editing, setEditing] = useState<ApiRecord | null>(null);
  const [open, setOpen] = useState(false);
  const columns: ProColumns<ApiRecord>[] = [
    { title: t("common.name"), dataIndex: "name", copyable: true },
    { title: t("nav.campaigns"), dataIndex: "campaign_id", renderText: (value) => campaigns.data.items.find((item) => item.id === value)?.name || "-" },
    { title: t("nav.replyTemplates"), dataIndex: "reply_template_id", renderText: (value) => templates.data.find((item) => item.id === value)?.name || "-" },
    { title: t("common.priority"), dataIndex: "priority", valueType: "digit" },
    { title: t("reply.containsAny"), dataIndex: "contains_any_json", render: (_, row) => <Tag>{Array.isArray(row.contains_any_json) ? row.contains_any_json.join(", ") : "-"}</Tag> },
    { title: t("common.enabled"), dataIndex: "enabled", render: (_, row) => row.enabled ? <Tag color="blue">{t("common.enabled")}</Tag> : <Tag>{t("common.disabled")}</Tag> },
    {
      title: t("common.actions"),
      valueType: "option",
      render: (_, row) => [
        <Button key="test" type="link" icon={<ExperimentOutlined />} onClick={() => testRule(row, t)}>{t("reply.test")}</Button>,
        <Button key="edit" type="link" icon={<EditOutlined />} onClick={() => setEditing(row)}>{t("common.edit")}</Button>,
        <Button key="delete" type="link" danger icon={<DeleteOutlined />} onClick={() => apiDelete(`/api/reply-match-rules/${row.id}`).then(rules.refresh)}>{t("common.delete")}</Button>
      ]
    }
  ];
  return (
    <Page title={t("nav.replyMatchRules")} action={<Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>{t("common.create")}</Button>}>
      <ResourceState loading={rules.loading} error={rules.error} empty={rules.data.length === 0} onRetry={rules.refresh}>
        <ProTable rowKey="id" search={false} dataSource={rules.data} columns={columns} options={{ reload: rules.refresh }} pagination={{ pageSize: 20 }} />
      </ResourceState>
      <RuleForm open={open} campaigns={campaigns.data.items} templates={templates.data} onOpenChange={setOpen} onSaved={rules.refresh} />
      <RuleForm open={Boolean(editing)} rule={editing} campaigns={campaigns.data.items} templates={templates.data} onOpenChange={(value) => !value && setEditing(null)} onSaved={rules.refresh} />
    </Page>
  );
}

async function testRule(row: ApiRecord, t: (key: string) => string) {
  const result = await apiPost<ApiRecord>("/api/reply-match-rules/test", { ...row, comment_text: "How much? Interested", author_name: "Preview" });
  Modal.info({ title: t("reply.test"), content: <pre>{JSON.stringify(result, null, 2)}</pre> });
}

function csv(value: unknown) {
  return Array.isArray(value) ? value.join(", ") : "";
}

function parseCsv(value: unknown) {
  return String(value || "").split(",").map((item) => item.trim()).filter(Boolean);
}

function RuleForm({ open, rule, campaigns, templates, onOpenChange, onSaved }: { open: boolean; rule?: ApiRecord | null; campaigns: ApiRecord[]; templates: ApiRecord[]; onOpenChange: (open: boolean) => void; onSaved: () => void }) {
  const { t } = useTranslation();
  return (
    <ModalForm
      key={String(rule?.id || "create")}
      title={rule ? t("common.edit") : t("common.create")}
      open={open}
      onOpenChange={onOpenChange}
      initialValues={rule ? { ...rule, contains_any_csv: csv(rule.contains_any_json), contains_all_csv: csv(rule.contains_all_json), author_exclude_csv: csv(rule.author_exclude_json) } : { enabled: true, priority: 100, comment_language: "any" }}
      modalProps={{ destroyOnClose: true }}
      onFinish={async (values) => {
        const raw = values as ApiRecord;
        const payload: ApiRecord = { ...raw, contains_any_json: parseCsv(raw.contains_any_csv), contains_all_json: parseCsv(raw.contains_all_csv), author_exclude_json: parseCsv(raw.author_exclude_csv) };
        delete payload.contains_any_csv; delete payload.contains_all_csv; delete payload.author_exclude_csv;
        if (rule) await apiPatch(`/api/reply-match-rules/${rule.id}`, payload);
        else await apiPost("/api/reply-match-rules", payload);
        message.success(t("reply.saved"));
        onSaved();
        return true;
      }}
    >
      <ProFormText name="name" label={t("common.name")} rules={[{ required: true }]} />
      <ProFormSelect name="campaign_id" label={t("nav.campaigns")} options={campaigns.map((item) => ({ value: String(item.id), label: String(item.name) }))} />
      <ProFormSelect name="reply_template_id" label={t("nav.replyTemplates")} options={templates.map((item) => ({ value: String(item.id), label: String(item.name) }))} />
      <Space wrap>
        <ProFormDigit name="priority" label={t("common.priority")} min={1} max={1000} />
        <ProFormSwitch name="enabled" label={t("common.enabled")} />
        <ProFormSelect name="comment_language" label={t("reply.language")} options={[{ value: "any", label: "Any" }, { value: "zh-CN", label: "zh-CN" }, { value: "en-US", label: "en-US" }]} />
      </Space>
      <ProFormText name="contains_any_csv" label={t("reply.containsAny")} />
      <ProFormText name="contains_all_csv" label={t("reply.containsAll")} />
      <ProFormText name="exact_text" label={t("reply.exact")} />
      <ProFormText name="regex_pattern" label={t("reply.regex")} />
      <ProFormText name="author_exclude_csv" label={t("reply.authorExclude")} />
      <ProFormTextArea name="description" label={t("reply.description")} />
    </ModalForm>
  );
}
