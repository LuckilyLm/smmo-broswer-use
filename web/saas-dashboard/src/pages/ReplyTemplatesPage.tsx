import { CopyOutlined, DeleteOutlined, EditOutlined, EyeOutlined, PlusOutlined } from "@ant-design/icons";
import { ModalForm, ProFormDigit, ProFormSelect, ProFormSwitch, ProFormText, ProFormTextArea, ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Modal, Space, Tag, message } from "antd";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { apiDelete, apiPatch, apiPost, type ApiRecord } from "../api";
import { Page, ResourceState } from "../components/Page";
import { useResource } from "../hooks/useResource";

export function ReplyTemplatesPage() {
  const { t } = useTranslation();
  const templates = useResource<ApiRecord[]>("/api/reply-templates", []);
  const [editing, setEditing] = useState<ApiRecord | null>(null);
  const [open, setOpen] = useState(false);
  const columns: ProColumns<ApiRecord>[] = [
    { title: t("common.name"), dataIndex: "name", copyable: true },
    { title: t("reply.platform"), dataIndex: "platform" },
    { title: t("reply.language"), dataIndex: "language" },
    { title: t("common.priority"), dataIndex: "priority", valueType: "digit" },
    { title: t("reply.default"), dataIndex: "is_default", render: (_, row) => row.is_default ? <Tag color="green">{t("common.yes")}</Tag> : <Tag>{t("common.no")}</Tag> },
    { title: t("common.enabled"), dataIndex: "enabled", render: (_, row) => row.enabled ? <Tag color="blue">{t("common.enabled")}</Tag> : <Tag>{t("common.disabled")}</Tag> },
    {
      title: t("common.actions"),
      valueType: "option",
      render: (_, row) => [
        <Button key="preview" type="link" icon={<EyeOutlined />} onClick={async () => {
          const result = await apiPost<ApiRecord>("/api/reply-templates/preview", { template_id: row.id, comment: { author_name: "Preview", keyword: "preview" } });
          Modal.info({ title: t("reply.preview"), content: <pre>{String(result.rendered || "")}</pre> });
        }}>{t("reply.preview")}</Button>,
        <Button key="edit" type="link" icon={<EditOutlined />} onClick={() => setEditing(row)}>{t("common.edit")}</Button>,
        <Button key="copy" type="link" icon={<CopyOutlined />} onClick={() => apiPost(`/api/reply-templates/${row.id}/copy`).then(templates.refresh)}>{t("reply.copy")}</Button>,
        <Button key="delete" type="link" danger icon={<DeleteOutlined />} onClick={() => apiDelete(`/api/reply-templates/${row.id}`).then(templates.refresh)}>{t("common.delete")}</Button>
      ]
    }
  ];
  return (
    <Page title={t("nav.replyTemplates")} action={<Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>{t("common.create")}</Button>}>
      <ResourceState loading={templates.loading} error={templates.error} empty={templates.data.length === 0} onRetry={templates.refresh}>
        <ProTable rowKey="id" dataSource={templates.data} columns={columns} options={{ reload: templates.refresh }} search={false} pagination={{ pageSize: 20 }} />
      </ResourceState>
      <TemplateForm open={open} onOpenChange={setOpen} onSaved={templates.refresh} />
      <TemplateForm open={Boolean(editing)} template={editing} onOpenChange={(value) => !value && setEditing(null)} onSaved={templates.refresh} />
    </Page>
  );
}

function TemplateForm({ open, template, onOpenChange, onSaved }: { open: boolean; template?: ApiRecord | null; onOpenChange: (open: boolean) => void; onSaved: () => void }) {
  const { t } = useTranslation();
  return (
    <ModalForm
      key={String(template?.id || "create")}
      title={template ? t("common.edit") : t("common.create")}
      open={open}
      onOpenChange={onOpenChange}
      initialValues={template || { platform: "facebook", language: "zh-CN", enabled: true, priority: 100, is_default: false }}
      modalProps={{ destroyOnClose: true }}
      onFinish={async (values) => {
        if (template) await apiPatch(`/api/reply-templates/${template.id}`, values);
        else await apiPost("/api/reply-templates", values);
        message.success(t("reply.saved"));
        onSaved();
        return true;
      }}
    >
      <ProFormText name="name" label={t("common.name")} rules={[{ required: true }]} />
      <ProFormTextArea name="description" label={t("reply.description")} />
      <ProFormTextArea name="content" label={t("reply.content")} rules={[{ required: true }]} fieldProps={{ rows: 5 }} />
      <Space wrap>
        <ProFormSelect name="platform" label={t("reply.platform")} options={[{ value: "facebook", label: "Facebook" }]} />
        <ProFormSelect name="language" label={t("reply.language")} options={[{ value: "zh-CN", label: "zh-CN" }, { value: "en-US", label: "en-US" }]} />
        <ProFormDigit name="priority" label={t("common.priority")} min={1} max={1000} />
        <ProFormSwitch name="enabled" label={t("common.enabled")} />
        <ProFormSwitch name="is_default" label={t("reply.default")} />
      </Space>
    </ModalForm>
  );
}
