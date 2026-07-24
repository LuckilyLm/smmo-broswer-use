import { render, screen } from "@testing-library/react";
import { Button } from "antd";
import { describe, expect, it } from "vitest";
import { AppEmpty, Page } from "./Page";

describe("page primitives", () => {
  it("renders the page title and refresh action exactly once", () => {
    render(<Page title="Executions" action={<Button>Refresh</Button>}><div>content</div></Page>);
    expect(screen.getAllByText("Executions")).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Refresh" })).toHaveLength(1);
  });

  it("renders the localized compact empty state", () => {
    render(<AppEmpty />);
    expect(screen.getByText("No records match the current filters")).toBeInTheDocument();
  });
});
