import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import i18n from "../i18n";
import { DataList } from "./DataList";

describe("localized table columns", () => {
  afterEach(async () => {
    cleanup();
    await i18n.changeLanguage("en-US");
  });

  it("renders business column labels and values in the selected locale", async () => {
    await i18n.changeLanguage("zh-CN");
    render(<DataList rows={[{ run_id: "run-1", status: "retry_waiting", selected_count: 1200 }]} fields={["run_id", "status", "selected_count"]} />);
    expect(screen.getByRole("columnheader", { name: "执行 ID" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "已选线索" })).toBeInTheDocument();
    expect(screen.getByText("等待重试")).toBeInTheDocument();
    expect(screen.getByText("1,200")).toBeInTheDocument();

    cleanup();
    await i18n.changeLanguage("en-US");
    render(<DataList rows={[{ id: "lead-1", author_name: "Alice", final_intent_level: "high", status: "qualified" }]} fields={["author_name", "final_intent_level", "status"]} />);
    expect(screen.getByRole("columnheader", { name: "User" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Final intent" })).toBeInTheDocument();
    expect(screen.getByText("High intent")).toBeInTheDocument();
    expect(screen.getByText("Qualified")).toBeInTheDocument();
  });
});
