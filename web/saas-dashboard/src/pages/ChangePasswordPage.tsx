import { KeyOutlined } from "@ant-design/icons";
import { Button, Card, Form, Input, Space, message } from "antd";
import { apiPost } from "../api";
import { useTranslation } from "react-i18next";

export function ChangePasswordPage({ onChanged }: { onChanged: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="login-page">
      <Card className="login-panel">
        <Space direction="vertical" size={20} style={{ width: "100%" }}>
          <div className="brand">{t("auth.changePassword")}</div>
          <Form layout="vertical" onFinish={async (values) => {
            try {
              await apiPost("/api/auth/change-password", {
                current_password: values.current_password,
                new_password: values.new_password
              });
              message.success(t("auth.changePassword"));
              onChanged();
            } catch {
              message.error(t("common.loadFailed"));
            }
          }}>
            <Form.Item name="current_password" label={t("auth.currentPassword")} rules={[{ required: true }]}>
              <Input.Password autoComplete="current-password" />
            </Form.Item>
            <Form.Item name="new_password" label={t("auth.newPassword")} rules={[{ required: true, min: 8 }]}>
              <Input.Password autoComplete="new-password" />
            </Form.Item>
            <Form.Item
              name="confirm_password"
              label={t("auth.confirmPassword")}
              dependencies={["new_password"]}
              rules={[
                { required: true },
                ({ getFieldValue }) => ({
                  validator(_, value) {
                    return !value || getFieldValue("new_password") === value
                      ? Promise.resolve()
                      : Promise.reject(new Error(t("auth.passwordMismatch")));
                  }
                })
              ]}
            >
              <Input.Password autoComplete="new-password" />
            </Form.Item>
            <Button type="primary" htmlType="submit" block icon={<KeyOutlined />}>{t("auth.changePassword")}</Button>
          </Form>
        </Space>
      </Card>
    </div>
  );
}
