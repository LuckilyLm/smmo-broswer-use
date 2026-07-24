import { ProCard, ProForm, ProFormDigit, ProFormSelect, ProFormText } from "@ant-design/pro-components";
import { Alert, Button, Descriptions, message } from "antd";
import { useTranslation } from "react-i18next";
import { apiPatch, type ApiRecord } from "../api";
import { Page, ResourceState } from "../components/Page";
import { useResource } from "../hooks/useResource";
import type { AppLocale } from "../i18n";
import {
  businessOptions,
  formatDateTime,
  formatTargetPolicy
} from "../utils/formatters";

const timezones = [
  "UTC",
  "Asia/Shanghai",
  "Asia/Tokyo",
  "Asia/Singapore",
  "Europe/London",
  "Europe/Paris",
  "America/New_York",
  "America/Chicago",
  "America/Los_Angeles"
];

const displayVersion = (value: unknown) => value && value !== "unknown" ? String(value) : "-";

export function SettingsPage() {
  const { t, i18n } = useTranslation();
  const locale = (i18n.resolvedLanguage === "zh-CN" ? "zh-CN" : "en-US") as AppLocale;
  const settings = useResource<ApiRecord>("/api/settings", {});
  const backend = useResource<ApiRecord>("/api/version", {});
  const frontendVersion = import.meta.env.VITE_APP_VERSION || "0.1.0";
  const frontendCommit = import.meta.env.VITE_GIT_COMMIT || "-";
  return (
    <Page title={t("nav.settings")} loading={settings.loading}>
      <ResourceState loading={false} error={settings.error} empty={false} onRetry={settings.refresh}>
        <div className="settings-content">
          <ProCard title={t("settings.workspace")}>
            <ProForm
              key={String(settings.data.tenant?.updated_at || "settings")}
              initialValues={settings.data.tenant}
              submitter={{ render: (_, dom) => <Button type="primary" htmlType="submit">{t("settings.save")}</Button> }}
              onFinish={async (values) => {
                await apiPatch("/api/settings", values);
                message.success(t("settings.saved"));
                settings.refresh();
              }}
            >
              <div className="settings-grid">
                <ProFormText name="name" label={t("settings.workspaceName")} rules={[{ required: true }]} />
                <ProFormSelect name="timezone" label={t("settings.timezone")} rules={[{ required: true }]} showSearch options={timezones} />
                <ProFormSelect name="default_target_policy" label={t("settings.targetPolicy")} options={businessOptions(["discovery_only", "owned_only", "allowlist"], formatTargetPolicy, t)} />
                <ProFormDigit name="default_min_confidence" label={t("settings.confidence")} min={0} max={1} fieldProps={{ step: 0.05, precision: 2 }} />
                <ProFormDigit name="default_daily_limit" label={t("settings.dailyLimit")} min={1} fieldProps={{ precision: 0 }} />
              </div>
            </ProForm>
          </ProCard>
          <ProCard title={t("settings.safety")}>
            <Alert type="success" showIcon message={t("app.safety")} description={t("settings.safetyMessage")} />
          </ProCard>
          <ProCard title={t("settings.version")}>
            <Descriptions column={1} size="small" items={[
              { key: "frontend", label: t("settings.frontend"), children: frontendVersion },
              { key: "backend", label: t("settings.backend"), children: displayVersion(backend.data.app_version) },
              { key: "commit", label: t("settings.gitCommit"), children: displayVersion(backend.data.git_commit || frontendCommit) },
              { key: "build", label: t("settings.buildTime"), children: formatDateTime(backend.data.build_time, locale) }
            ]} />
          </ProCard>
        </div>
      </ResourceState>
    </Page>
  );
}
