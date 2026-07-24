import { BellOutlined, CheckOutlined, ExclamationCircleOutlined, InfoCircleOutlined, WarningOutlined } from "@ant-design/icons";
import { Badge, Button, Drawer, List, Segmented, Space, Tag, Tooltip, Typography } from "antd";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { apiPost } from "../api";
import { useResource } from "../hooks/useResource";
import type { Notification, PaginatedResponse } from "../types";
import type { AppLocale } from "../i18n";
import {
  formatDateTime,
  formatNotificationMessage,
  formatNotificationSeverity,
  formatNotificationTitle
} from "../utils/formatters";

type NotificationPage = PaginatedResponse<Notification> & { unread_count: number };

const severityIcons = {
  error: <ExclamationCircleOutlined className="error-icon" />,
  warning: <WarningOutlined className="warning-icon" />,
  info: <InfoCircleOutlined className="info-icon" />
};

export function NotificationDrawer() {
  const { t, i18n } = useTranslation();
  const locale = (i18n.resolvedLanguage === "zh-CN" ? "zh-CN" : "en-US") as AppLocale;
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<"unread" | "all">("unread");
  const notifications = useResource<NotificationPage>("/api/notifications?limit=50&offset=0", { items: [], limit: 50, offset: 0, total: 0, unread_count: 0 });
  const rows = view === "unread" ? notifications.data.items.filter((item) => !item.read_at) : notifications.data.items;
  return (
    <>
      <Badge count={notifications.data.unread_count} size="small">
        <Tooltip title={t("notification.title")}><Button type="text" aria-label={t("notification.title")} icon={<BellOutlined />} onClick={() => setOpen(true)} /></Tooltip>
      </Badge>
      <Drawer title={t("notification.title")} open={open} onClose={() => setOpen(false)} width={440} extra={<Button icon={<CheckOutlined />} onClick={() => apiPost("/api/notifications/read-all").then(notifications.refresh)}>{t("notification.readAll")}</Button>}>
        <Segmented block value={view} onChange={(value) => setView(value as "unread" | "all")} options={[{ value: "unread", label: `${t("notification.unread")} (${notifications.data.unread_count})` }, { value: "all", label: t("notification.all") }]} />
        <List className="notification-list" dataSource={rows} locale={{ emptyText: t("notification.empty") }} renderItem={(item) => (
          <List.Item actions={!item.read_at ? [<Button key="read" type="link" onClick={() => apiPost(`/api/notifications/${item.id}/read`).then(notifications.refresh)}>{t("notification.markRead")}</Button>] : []}>
            <List.Item.Meta
              avatar={severityIcons[item.severity as keyof typeof severityIcons] || severityIcons.info}
              title={<Space><Typography.Text strong={!item.read_at}>{formatNotificationTitle(item.type, t)}</Typography.Text><Tag>{formatNotificationSeverity(item.severity, t)}</Tag></Space>}
              description={<><div>{formatNotificationMessage(item.type, t)}</div><Typography.Text type="secondary">{formatDateTime(item.created_at, locale)}</Typography.Text></>}
            />
          </List.Item>
        )} />
      </Drawer>
    </>
  );
}
