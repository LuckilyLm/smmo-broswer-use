import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import i18n from "../i18n";
import { ScheduleDrawer } from "./ScheduleDrawer";

vi.mock("../hooks/useResource", () => ({
  useResource: () => ({
    data: {
      schedule_type: "manual",
      enabled: false,
      timezone: "Asia/Shanghai",
      next_run_at: "2026-07-01T14:30:00",
      last_run_at: "2026-06-30T09:00:00"
    },
    refresh: vi.fn()
  })
}));

describe("localized campaign schedule drawer", () => {
  afterEach(async () => {
    cleanup();
    await i18n.changeLanguage("en-US");
  });

  it("renders drawer copy and dates entirely in the selected locale", async () => {
    await i18n.changeLanguage("zh-CN");
    render(<ScheduleDrawer campaign={{ id: "campaign-1" }} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByText("活动执行计划")).toBeInTheDocument();
    expect(screen.getByText("执行方式")).toBeInTheDocument();
    expect(screen.getByText("仅手动执行")).toBeInTheDocument();
    expect(screen.getByText("2026-07-01 14:30")).toBeInTheDocument();

    cleanup();
    await i18n.changeLanguage("en-US");
    render(<ScheduleDrawer campaign={{ id: "campaign-1" }} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByText("Campaign schedule")).toBeInTheDocument();
    expect(screen.getByText("Run plan")).toBeInTheDocument();
    expect(screen.getByText("Manual only")).toBeInTheDocument();
    expect(screen.getByText("Jul 1, 2026, 2:30 PM")).toBeInTheDocument();
  });
});
