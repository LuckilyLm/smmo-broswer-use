import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SystemAdmin from "../pages/SystemAdmin";

const responses: Record<string, unknown> = {
  "/api/admin/system/usage": { tenants: 1, users: 1, executions: 3, tokens: 42, worker_health: 1 },
  "/api/admin/tenants?limit=200": { items: [{ id: "tenant-1", name: "真实租户", slug: "real", status: "active", plan: { name: "专业版" }, usage: { members: 2, campaigns: 4 }, created_at: "2026-07-01T00:00:00Z", updated_at: "2026-07-01T00:00:00Z" }], total: 1, limit: 200, offset: 0 },
  "/api/admin/users?limit=200": { items: [{ id: "user-1", email: "admin@example.com", display_name: "系统用户", status: "active", must_change_password: false, is_system_admin: true, created_at: "2026-07-01T00:00:00Z", updated_at: "2026-07-01T00:00:00Z" }], total: 1, limit: 200, offset: 0 },
  "/api/admin/system/health": { api: { status: "ok" }, postgres: { status: "ok" }, worker: { online: true, worker_count: 1 }, scheduler: { online: false, due_campaign_count: 0, queued_tasks: 1, running_tasks: 0 }, queue: { queued: 1 }, browser_runtimes: { count: 0 } },
  "/api/admin/system/runtimes?limit=200": { items: [], total: 0, limit: 200, offset: 0 },
  "/api/admin/system/queue?limit=200": { items: [], total: 0, limit: 200, offset: 0 },
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function renderPage() {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const path = new URL(String(input), "http://localhost").pathname + new URL(String(input), "http://localhost").search;
    return new Response(JSON.stringify(responses[path]), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><SystemAdmin /></QueryClientProvider>);
}

describe("SystemAdmin", () => {
  it("renders tenant and user data returned by admin APIs", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "租户" }));
    expect(await screen.findAllByText("真实租户")).not.toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "用户" }));
    expect(await screen.findByText("系统用户")).toBeInTheDocument();
    expect(screen.queryByText("科技有限公司")).not.toBeInTheDocument();
  });

  it("renders real empty runtime and queue states", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "运行时与队列" }));
    await waitFor(() => expect(screen.getByText("暂无运行时")).toBeInTheDocument());
    expect(screen.getByText("队列为空")).toBeInTheDocument();
  });

  it("shows health states from the backend", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "系统健康" }));
    expect(await screen.findByText("Scheduler")).toBeInTheDocument();
    expect(screen.getByText("1 排队 / 0 运行")).toBeInTheDocument();
    expect(screen.getByText("异常")).toBeInTheDocument();
  });
});
