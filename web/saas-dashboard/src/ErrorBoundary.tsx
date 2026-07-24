import React from "react";
import { Alert, Button } from "antd";
import i18n from "./i18n";

export class ErrorBoundary extends React.Component<React.PropsWithChildren, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) {
      return <Alert type="error" showIcon message={i18n.t("common.loadFailed")} action={<Button onClick={() => window.location.reload()}>{i18n.t("common.retry")}</Button>} />;
    }
    return this.props.children;
  }
}
