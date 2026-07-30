import { Component, type ErrorInfo, type ReactNode } from "react";

import { Button } from "./components/ui/button";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Dashboard render failed", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <div className="flex min-h-screen items-center justify-center bg-muted/40 p-6">
        <div className="w-full max-w-lg rounded-2xl border bg-card p-6 text-center shadow-sm">
          <h1 className="text-xl font-semibold text-foreground">页面加载失败</h1>
          <p className="mt-2 text-sm text-muted-foreground">界面发生了意外错误，请刷新页面重试。</p>
          <p className="mt-3 break-words rounded-lg bg-muted p-3 text-left font-mono text-xs text-muted-foreground">
            {this.state.error.message}
          </p>
          <Button className="mt-5" onClick={() => window.location.reload()}>刷新页面</Button>
        </div>
      </div>
    );
  }
}
