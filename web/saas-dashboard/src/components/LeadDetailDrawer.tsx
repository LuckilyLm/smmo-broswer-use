import { Button, Descriptions, Drawer, Space } from "antd";
import type { ApiRecord } from "../api";
import { useTranslation } from "react-i18next";
import { formatIntentLevel, formatOwnershipStatus } from "../utils/formatters";

export function LeadDetailDrawer({ lead, onClose }: { lead: ApiRecord | null; onClose: () => void }) {
  const { t } = useTranslation();
  return (
    <Drawer open={Boolean(lead)} width={620} title={t("detail.lead")} onClose={onClose}>
      {lead && <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <Descriptions column={1} bordered size="small" items={[
          { key: "author", label: t("lead.author"), children: lead.author_name || "-" },
          { key: "comment", label: t("lead.comment"), children: lead.comment_text || "-" },
          { key: "intent", label: t("detail.finalIntent"), children: formatIntentLevel(lead.final_intent_level, t) },
          { key: "confidence", label: t("detail.aiConfidence"), children: lead.llm_confidence || "-" },
          { key: "reason", label: t("detail.aiReason"), children: lead.llm_reason || "-" },
          { key: "ownership", label: t("detail.ownership"), children: formatOwnershipStatus(lead.ownership_status, t) },
          { key: "allowed", label: t("lead.allowed"), children: Boolean(lead.reply_allowed) ? t("common.yes") : t("common.no") },
          { key: "reply", label: t("detail.suggestedReply"), children: lead.suggested_reply || "-" }
        ]} />
        <Space>
          {lead.source_content_url && <Button href={lead.source_content_url} target="_blank">{t("detail.openPost")}</Button>}
          {lead.direct_comment_url && <Button href={lead.direct_comment_url} target="_blank">{t("detail.openComment")}</Button>}
        </Space>
      </Space>}
    </Drawer>
  );
}
