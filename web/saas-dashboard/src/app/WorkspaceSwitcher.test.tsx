import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { WorkspaceSwitcher } from "../App";

describe("workspace switcher", () => {
  it("switches to another tenant", async () => {
    const onSwitch = vi.fn().mockResolvedValue(undefined);
    render(<WorkspaceSwitcher currentId="one" tenants={[
      { id: "one", name: "Workspace One", slug: "one", status: "active" },
      { id: "two", name: "Workspace Two", slug: "two", status: "active" }
    ]} onSwitch={onSwitch} />);
    fireEvent.mouseDown(screen.getByRole("combobox"));
    fireEvent.click(await screen.findByText("Workspace Two"));
    await waitFor(() => expect(onSwitch).toHaveBeenCalledWith("two"));
  });
});
