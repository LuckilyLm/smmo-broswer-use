import React from "react";
import { Alert, Button } from "antd";

export class ErrorBoundary extends React.Component<React.PropsWithChildren, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) {
      return <Alert type="error" showIcon message="Application unavailable" action={<Button onClick={() => window.location.reload()}>Reload</Button>} />;
    }
    return this.props.children;
  }
}
