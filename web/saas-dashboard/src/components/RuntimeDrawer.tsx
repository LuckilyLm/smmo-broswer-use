import { Descriptions, Drawer } from "antd";
import type { BrowserRuntime } from "../types";
import { useTranslation } from "react-i18next";
import type { AppLocale } from "../i18n";
import { formatDateTime, formatRuntimeStatus, formatRuntimeType } from "../utils/formatters";
import { StatusTag } from "./DataList";

export function RuntimeDrawer({ runtime, onClose }: { runtime: BrowserRuntime | null; onClose: () => void }) {
  const { t, i18n } = useTranslation();
  const locale = (i18n.resolvedLanguage === "zh-CN" ? "zh-CN" : "en-US") as AppLocale;
  return (
    <Drawer open={Boolean(runtime)} width={520} title={t("detail.runtime")} onClose={onClose}>
      {runtime && <Descriptions column={1} bordered size="small" items={[
        { key: "status", label: t("detail.runtimeStatus"), children: <StatusTag value={runtime.status} formatter={formatRuntimeStatus} /> },
        { key: "type", label: t("detail.runtimeType"), children: formatRuntimeType(runtime.runtime_type, t) },
        { key: "started", label: t("detail.startedAt"), children: formatDateTime(runtime.started_at, locale) },
        { key: "checked", label: t("detail.healthCheck"), children: formatDateTime(runtime.last_health_check_at, locale) }
      ]} />}
    </Drawer>
  );
}
