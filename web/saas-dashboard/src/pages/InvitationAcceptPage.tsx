import { Button, Card, Form, Input, Space, Typography, message } from "antd";
import { apiPost } from "../api";
import { useTranslation } from "react-i18next";

export function InvitationAcceptPage({ token, authenticated, onAccepted }: { token: string; authenticated: boolean; onAccepted: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="login-page">
      <Card className="login-panel">
        <Space direction="vertical" size={18} style={{ width: "100%" }}>
          <div>
            <div className="brand">{t("invite.join")}</div>
            <Typography.Text className="muted">{authenticated ? t("invite.signedInHint") : t("invite.anonymousHint")}</Typography.Text>
          </div>
          <Form layout="vertical" onFinish={async (values) => {
            await apiPost(`/api/invitations/${token}/accept`, authenticated ? {} : values);
            message.success(t("invite.accepted"));
            onAccepted();
          }}>
            {!authenticated && <>
              <Form.Item name="email" label={t("common.email")} rules={[{ required: true, type: "email" }]}><Input autoComplete="email" /></Form.Item>
              <Form.Item name="display_name" label={t("invite.displayName")} rules={[{ required: true }]}><Input /></Form.Item>
              <Form.Item name="password" label={t("auth.password")} rules={[{ required: true, min: 8 }]}><Input.Password autoComplete="new-password" /></Form.Item>
            </>}
            <Button type="primary" htmlType="submit" block>{t("invite.accept")}</Button>
          </Form>
        </Space>
      </Card>
    </div>
  );
}
