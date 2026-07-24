import { Button, Descriptions, Drawer, Form, Input, Select, Space, Switch, message } from "antd";
import { useEffect } from "react";
import { apiPost, apiPut, type ApiRecord } from "../api";
import { useResource } from "../hooks/useResource";
import { useTranslation } from "react-i18next";
import type { AppLocale } from "../i18n";
import { formatDateTime } from "../utils/formatters";

export function ScheduleDrawer({ campaign, onClose, onSaved }: { campaign: ApiRecord | null; onClose: () => void; onSaved: () => void }) {
  const { t, i18n } = useTranslation();
  const locale = (i18n.resolvedLanguage === "zh-CN" ? "zh-CN" : "en-US") as AppLocale;
  const [form] = Form.useForm();
  const { data: schedule, refresh } = useResource<ApiRecord>(campaign ? `/api/campaigns/${campaign.id}/schedule` : "", {});
  useEffect(() => {
    if (campaign) {
      form.setFieldsValue({ schedule_type: "manual", enabled: false, interval_minutes: 360, daily_time: "09:00", timezone: "Asia/Shanghai", ...schedule });
    }
  }, [campaign, schedule, form]);
  return (
    <Drawer open={Boolean(campaign)} width={520} title={t("schedule.title")} onClose={onClose}>
      {campaign && <Form form={form} layout="vertical" onFinish={async (values) => {
        await apiPut(`/api/campaigns/${campaign.id}/schedule`, values);
        message.success(t("schedule.saved"));
        refresh();
        onSaved();
      }}>
        <Form.Item name="schedule_type" label={t("schedule.runPlan")}>
          <Select options={[{ value: "manual", label: t("schedule.manualOnly") }, { value: "interval", label: t("schedule.everyHours") }, { value: "daily", label: t("schedule.dailyFixed") }]} />
        </Form.Item>
        <Form.Item name="enabled" label={t("common.enabled")} valuePropName="checked"><Switch /></Form.Item>
        <Form.Item noStyle shouldUpdate>
          {() => form.getFieldValue("schedule_type") === "interval" && <Form.Item name="interval_minutes" label={t("schedule.interval")}><Select options={[{ value: 180, label: t("schedule.every3") }, { value: 360, label: t("schedule.every6") }, { value: 720, label: t("schedule.every12") }]} /></Form.Item>}
        </Form.Item>
        <Form.Item noStyle shouldUpdate>
          {() => form.getFieldValue("schedule_type") === "daily" && <Form.Item name="daily_time" label={t("schedule.dailyTime")}><Input placeholder="09:00" /></Form.Item>}
        </Form.Item>
        <Form.Item name="timezone" label={t("settings.timezone")}><Select options={[{ value: "Asia/Shanghai" }, { value: "Asia/Singapore" }, { value: "UTC" }]} /></Form.Item>
        <Descriptions column={1} size="small" bordered items={[
          { key: "next", label: t("schedule.nextRun"), children: formatDateTime(schedule.next_run_at, locale) },
          { key: "last", label: t("schedule.lastRun"), children: formatDateTime(schedule.last_run_at, locale) }
        ]} />
        <Space style={{ marginTop: 16 }}>
          <Button type="primary" htmlType="submit">{t("common.save")}</Button>
          <Button onClick={async () => { await apiPost(`/api/campaigns/${campaign.id}/schedule/disable`); message.success(t("schedule.disabled")); refresh(); onSaved(); }}>{t("schedule.disable")}</Button>
        </Space>
      </Form>}
    </Drawer>
  );
}
