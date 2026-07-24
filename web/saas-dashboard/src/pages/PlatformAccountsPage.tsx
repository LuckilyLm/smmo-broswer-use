import { EyeOutlined, MoreOutlined, PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { ModalForm, ProFormSelect, ProFormText, ProList } from "@ant-design/pro-components";
import { Alert, Button, Dropdown, Modal, Space, Tag, Tooltip, message, type MenuProps } from "antd";
import type { ReactNode } from "react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { apiGet, apiPost, type ApiRecord } from "../api";
import { StatusTag } from "../components/DataList";
import { Page, ResourceState } from "../components/Page";
import { RuntimeDrawer } from "../components/RuntimeDrawer";
import { useResource } from "../hooks/useResource";
import type { BrowserRuntime, RuntimeCapabilities } from "../types";
import type { AppLocale } from "../i18n";
import {
  formatConnectionStatus,
  formatDateTime,
  formatEmpty,
  formatLoginStatus,
  formatRuntimeStatus
} from "../utils/formatters";

export function PlatformAccountsPage() {
  const { t, i18n } = useTranslation();
  const locale = (i18n.resolvedLanguage === "zh-CN" ? "zh-CN" : "en-US") as AppLocale;
  const accounts = useResource<ApiRecord[]>("/api/platform-accounts", []);
  const capabilities = useResource<RuntimeCapabilities>("/api/system/runtime-capabilities", {
    runtime_host: "local",
    runtime_available: false,
    browser_platform: "unknown",
    local_browser_supported: false
  });
  const [selectedRuntime, setSelectedRuntime] = useState<BrowserRuntime | null>(null);
  const [busy, setBusy] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const runAction = async (account: ApiRecord, action: string, body?: ApiRecord) => {
    setBusy(`${account.id}:${action}`);
    try {
      const result = await apiPost<ApiRecord>(`/api/platform-accounts/${account.id}/${action}`, body);
      if (action === "connect") Modal.info({ title: t("platform.completeSignIn"), content: t("platform.completeSignInDescription") });
      if (result.runtime) setSelectedRuntime(result.runtime);
      message.success(t("platform.actionCompleted"));
      accounts.refresh();
    } catch {
      message.error(t("platform.actionFailed"));
    } finally {
      setBusy("");
    }
  };
  const runtimeAvailable = capabilities.data.runtime_available;
  const runtimeUnavailableReason = t("platform.runtimeUnavailableActionTip");
  const renderBrowserActions = (row: ApiRecord) => {
    const browserItems: MenuProps["items"] = [
      { key: "connect", label: t("platform.connect"), disabled: !runtimeAvailable },
      { key: "check-login", label: t("platform.check"), disabled: !runtimeAvailable },
      { key: "restart-runtime", label: t("platform.restart"), disabled: !runtimeAvailable },
      { key: "stop-runtime", label: t("platform.stop"), disabled: !runtimeAvailable },
      { key: "reset-profile", label: t("platform.reset"), disabled: !runtimeAvailable, danger: true }
    ];

    const browserAction = runtimeAvailable ? (
      <Dropdown
        key="browser-actions"
        menu={{
          items: browserItems,
          onClick: ({ key }) => {
            if (key === "reset-profile") {
              Modal.confirm({
                title: t("platform.resetConfirmTitle"),
                content: t("platform.resetConfirmDescription"),
                okButtonProps: { danger: true },
                onOk: () => runAction(row, "reset-profile", { confirm: "RESET PROFILE" })
              });
            } else {
              runAction(row, key);
            }
          }
        }}
      >
        <Button icon={<MoreOutlined />} loading={busy.startsWith(`${row.id}:`)}>{t("platform.browserActions")}</Button>
      </Dropdown>
    ) : (
      <Tooltip key="browser-actions" title={runtimeUnavailableReason}>
        <span>
          <Dropdown menu={{ items: browserItems }} disabled>
            <Button icon={<MoreOutlined />} disabled>{t("platform.browserActions")}</Button>
          </Dropdown>
        </span>
      </Tooltip>
    );

    return (
      <div className="platform-card-actions">
        {browserAction}
        <Button icon={<EyeOutlined />} onClick={() => apiGet<BrowserRuntime>(`/api/platform-accounts/${row.id}/runtime`).then(setSelectedRuntime)}>{t("common.details")}</Button>
      </div>
    );
  };

  return (
    <Page title={t("nav.platforms")} loading={accounts.loading} action={
      <Space>
        <Button aria-label={t("common.refresh")} icon={<ReloadOutlined />} loading={accounts.loading} onClick={accounts.refresh}>{t("common.refresh")}</Button>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>{t("common.create")}</Button>
      </Space>
    }>
      {!runtimeAvailable && <Alert className="quota-alert" type="warning" showIcon message={t("platform.unavailable")} description={t("platform.unavailableDescription")} />}
      <ResourceState loading={false} error={accounts.error} empty={accounts.data.length === 0} onRetry={accounts.refresh}>
        <ProList<ApiRecord>
          className="platform-account-list"
          rowKey="id"
          grid={accounts.data.length <= 1
            ? { gutter: 16, xs: 1, sm: 1, md: 1, lg: 1, xl: 1, xxl: 1 }
            : { gutter: 16, xs: 1, sm: 1, md: 2, lg: 2, xl: 2, xxl: 3 }}
          dataSource={accounts.data}
          metas={{
            title: { render: (_, row) => String(row.display_name || formatEmpty(locale, "unknown")) },
            subTitle: { render: (_, row) => <Tag>{String(row.platform || formatEmpty(locale, "unknown"))}</Tag> },
            content: { render: (_, row) => (
              <div className="platform-meta">
                <div className="platform-meta-grid">
                  <MetaItem label={t("platform.platform")} value={String(row.platform || formatEmpty(locale, "unknown"))} />
                  <MetaItem label={t("platform.displayName")} value={String(row.display_name || formatEmpty(locale, "unknown"))} />
                  <MetaItem label={t("platform.connectionStatus")} value={<StatusTag value={row.connection_status || "unknown"} formatter={formatConnectionStatus} />} />
                  <MetaItem label={t("platform.loginStatus")} value={<StatusTag value={row.login_status || "unknown"} formatter={formatLoginStatus} />} />
                  <MetaItem label={t("platform.browserAvailability")} value={<Tag color={runtimeAvailable ? "green" : "gold"}>{runtimeAvailable ? t("platform.available") : t("platform.unavailableShort")}</Tag>} />
                  <MetaItem label={t("platform.runtimeStatus")} value={<StatusTag value={row.runtime?.status || "stopped"} formatter={formatRuntimeStatus} />} />
                  <MetaItem label={t("platform.lastCheck")} value={formatDateTime(row.last_login_check_at, locale, "notChecked")} />
                </div>
                {row.last_connection_error ? <span className="muted">{t("platform.connectionIssue")}</span> : null}
                {renderBrowserActions(row)}
              </div>
            ) }
          }}
        />
      </ResourceState>
      <PlatformAccountForm open={createOpen} onOpenChange={setCreateOpen} onSaved={accounts.refresh} />
      <RuntimeDrawer runtime={selectedRuntime} onClose={() => setSelectedRuntime(null)} />
    </Page>
  );
}

function MetaItem({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="platform-meta-item">
      <span className="muted">{label}</span>
      <span>{value}</span>
    </div>
  );
}

function PlatformAccountForm({
  open,
  onOpenChange,
  onSaved
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  return (
    <ModalForm
      title={t("platform.createAccount")}
      open={open}
      onOpenChange={onOpenChange}
      initialValues={{ platform: "facebook" }}
      modalProps={{ destroyOnClose: true }}
      onFinish={async (values) => {
        await apiPost("/api/platform-accounts", values);
        message.success(t("platform.created"));
        onSaved();
        return true;
      }}
    >
      <ProFormSelect name="platform" label={t("platform.platform")} rules={[{ required: true }]} options={[{ value: "facebook", label: "Facebook" }]} />
      <ProFormText name="display_name" label={t("platform.displayName")} rules={[{ required: true }]} />
      <ProFormText name="external_account_name" label={t("platform.externalAccountName")} />
      <ProFormText name="external_account_id" label={t("platform.externalAccountId")} />
    </ModalForm>
  );
}
