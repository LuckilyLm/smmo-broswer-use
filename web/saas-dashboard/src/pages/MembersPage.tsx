import { CopyOutlined, DeleteOutlined, PlusOutlined, SwapOutlined } from "@ant-design/icons";
import { ModalForm, ProFormSelect, ProFormText, ProTable, type ProColumns } from "@ant-design/pro-components";
import { Button, Input, Result, Select, Space, message } from "antd";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { apiDelete, apiPatch, apiPost } from "../api";
import { Page, ResourceState } from "../components/Page";
import { useResource } from "../hooks/useResource";
import type { Invitation, PaginatedResponse, TenantMember } from "../types";
import type { AppLocale } from "../i18n";
import {
  businessOptions,
  formatDateTime,
  formatInvitationStatus,
  formatMemberRole,
  formatStatus
} from "../utils/formatters";
import { StatusTag } from "../components/DataList";

export function MembersPage({ currentUserId, role }: { currentUserId: string; role: string }) {
  const { t, i18n } = useTranslation();
  const locale = (i18n.resolvedLanguage === "zh-CN" ? "zh-CN" : "en-US") as AppLocale;
  const members = useResource<PaginatedResponse<TenantMember>>("/api/tenant/members?limit=200&offset=0", { items: [], limit: 200, offset: 0, total: 0 });
  const invitations = useResource<PaginatedResponse<Invitation>>("/api/tenant/invitations?limit=200&offset=0", { items: [], limit: 200, offset: 0, total: 0 });
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteLink, setInviteLink] = useState("");
  const memberColumns: ProColumns<TenantMember>[] = [
    { title: t("common.name"), dataIndex: "display_name" },
    { title: t("common.email"), dataIndex: "email", copyable: true },
    { title: t("members.role"), dataIndex: "role", valueType: "select", render: (_, row) => <Select value={row.role} disabled={row.role === "owner" || (role === "admin" && row.role === "admin")} className="role-select" options={businessOptions(["admin", "member", "viewer"], formatMemberRole, t)} onChange={(next) => apiPatch(`/api/tenant/members/${row.id}`, { role: next }).then(members.refresh)} /> },
    { title: t("common.status"), dataIndex: "status", valueType: "select", render: (_, row) => <StatusTag value={row.status} formatter={formatStatus} /> },
    { title: t("common.actions"), valueType: "option", render: (_, row) => [
      ...(role === "owner" && row.user_id !== currentUserId ? [<Button key="transfer" type="link" icon={<SwapOutlined />} onClick={() => apiPost("/api/tenant/transfer-ownership", { target_user_id: row.user_id }).then(members.refresh)}>{t("members.transfer")}</Button>] : []),
      <Button key="remove" type="link" danger icon={<DeleteOutlined />} disabled={row.user_id === currentUserId || row.role === "owner"} onClick={() => apiDelete(`/api/tenant/members/${row.id}`).then(members.refresh)}>{t("common.remove")}</Button>
    ] }
  ];
  const invitationColumns: ProColumns<Invitation>[] = [
    { title: t("common.email"), dataIndex: "email", copyable: true },
    { title: t("members.role"), dataIndex: "role", renderText: (value) => formatMemberRole(value, t) },
    { title: t("common.status"), dataIndex: "status", valueType: "select", render: (_, row) => <StatusTag value={row.status} formatter={formatInvitationStatus} /> },
    { title: t("members.expires"), dataIndex: "expires_at", renderText: (value) => formatDateTime(value, locale) },
    { title: t("common.actions"), valueType: "option", render: (_, row) => <Button type="link" danger icon={<DeleteOutlined />} disabled={row.status !== "pending"} onClick={() => apiDelete(`/api/tenant/invitations/${row.id}`).then(invitations.refresh)}>{t("members.revoke")}</Button> }
  ];
  return (
    <Page title={t("nav.members")} loading={members.loading} action={<Button type="primary" icon={<PlusOutlined />} onClick={() => { setInviteLink(""); setInviteOpen(true); }}>{t("members.invite")}</Button>}>
      <ResourceState loading={false} error={members.error} empty={false} onRetry={members.refresh}>
        <ProTable rowKey="id" headerTitle={t("nav.members")} search={false} options={{ reload: members.refresh }} dataSource={members.data.items} columns={memberColumns} pagination={false} />
        <ProTable rowKey="id" headerTitle={t("members.pending")} search={false} options={{ reload: invitations.refresh }} dataSource={invitations.data.items} columns={invitationColumns} pagination={false} />
      </ResourceState>
      <ModalForm
        title={t("members.invite")}
        open={inviteOpen}
        onOpenChange={setInviteOpen}
        submitter={inviteLink ? false : undefined}
        initialValues={{ role: "member" }}
        onFinish={async (values) => {
          const created = await apiPost<Invitation>("/api/tenant/invitations", values);
          setInviteLink(`${window.location.origin}/invite/${created.token}`);
          invitations.refresh();
          return false;
        }}
      >
        {inviteLink ? <Result status="success" title={t("members.inviteReady")} extra={<Space.Compact block><Input value={inviteLink} readOnly /><Button icon={<CopyOutlined />} onClick={async () => { await navigator.clipboard.writeText(inviteLink); message.success(t("common.copied")); }}>{t("members.copyLink")}</Button></Space.Compact>} /> : <>
          <ProFormText name="email" label={t("common.email")} rules={[{ required: true, type: "email" }]} />
          <ProFormSelect name="role" label={t("members.role")} options={businessOptions(role === "owner" ? ["admin", "member", "viewer"] : ["member", "viewer"], formatMemberRole, t)} />
        </>}
      </ModalForm>
    </Page>
  );
}
