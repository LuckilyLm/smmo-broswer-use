import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import { afterEach, describe, expect, it, vi } from "vitest";
import i18n from "../i18n";
import { PlatformAccountsPage } from "./PlatformAccountsPage";

const runtimeAvailable = vi.hoisted(() => ({ value: false }));

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    apiGet: vi.fn(),
    apiPost: vi.fn()
  };
});

vi.mock("../hooks/useResource", () => ({
  useResource: (url: string, initial: unknown) => {
    let data = initial;
    if (url === "/api/platform-accounts") {
      data = [{
        id: "account-1",
        platform: "Facebook",
        display_name: "Sales Account",
        connection_status: "unknown",
        login_status: "unknown",
        last_login_check_at: null,
        runtime: null
      }];
    } else if (url === "/api/system/runtime-capabilities") {
      data = {
        runtime_host: "local",
        runtime_available: runtimeAvailable.value,
        browser_platform: "linux",
        local_browser_supported: false
      };
    }
    return { data, loading: false, error: "", refresh: vi.fn() };
  }
}));

describe("PlatformAccountsPage", () => {
  afterEach(async () => {
    cleanup();
    await i18n.changeLanguage("en-US");
  });

  it("keeps database account creation available when browser actions are unavailable", async () => {
    runtimeAvailable.value = false;
    await i18n.changeLanguage("zh-CN");
    const { container } = render(<ConfigProvider locale={zhCN}><PlatformAccountsPage /></ConfigProvider>);

    expect(screen.getByRole("button", { name: /创建/ })).toBeEnabled();
    expect(screen.getByText("平台")).toBeInTheDocument();
    expect(screen.getByText("账号显示名称")).toBeInTheDocument();
    expect(screen.getByText("连接状态")).toBeInTheDocument();
    expect(screen.getByText("登录状态")).toBeInTheDocument();
    expect(screen.getByText("浏览器运行节点")).toBeInTheDocument();
    expect(screen.getByText("最近检查")).toBeInTheDocument();
    expect(screen.getByText("未检查")).toBeInTheDocument();

    expect(screen.getByText("此服务节点不支持本地浏览器运行，请使用 Windows 浏览器运行节点。")).toBeInTheDocument();

    const browserActions = screen.getByRole("button", { name: /浏览器操作/ });
    expect(browserActions).toBeDisabled();
    expect(screen.queryByRole("button", { name: "连接" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "检查登录" })).not.toBeInTheDocument();
    expect(container.textContent).not.toMatch(/Runtime Host|Browser Runtime|Worker|Scheduler|CDP|PID|send_disabled|discovery_only/);
  });

  it("enables every browser action when the runtime capability API reports availability", async () => {
    runtimeAvailable.value = true;
    const user = userEvent.setup();
    render(<PlatformAccountsPage />);

    const browserActions = screen.getByRole("button", { name: /browser actions/i });
    expect(browserActions).toBeEnabled();
    await user.click(browserActions);

    for (const label of ["Connect", "Check login", "Restart", "Stop", "Reset"]) {
      expect(await screen.findByRole("menuitem", { name: label })).toHaveAttribute("aria-disabled", "false");
    }
  });
});
