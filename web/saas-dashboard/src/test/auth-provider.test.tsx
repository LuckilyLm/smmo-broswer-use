import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "../auth/AuthProvider";

const session = {
  user: { id: "user-1", email: "admin@example.com", is_system_admin: true },
  tenant: { id: "tenant-1", name: "Tenant", slug: "tenant", status: "active" },
  role: "owner",
  permissions: ["campaigns.read"],
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function AuthProbe() {
  const auth = useAuth();
  return (
    <>
      <output data-testid="auth-state">
        {JSON.stringify({
          status: auth.status,
          user: auth.user,
          tenant: auth.tenant,
          role: auth.role,
          permissions: auth.permissions,
          isSystemAdmin: auth.isSystemAdmin,
        })}
      </output>
      <button onClick={() => void auth.refreshSession()}>refresh</button>
      <button onClick={() => void auth.logout()}>logout</button>
    </>
  );
}

function renderProvider() {
  return render(
    <AuthProvider>
      <AuthProbe />
    </AuthProvider>,
  );
}

async function expectAuthenticated() {
  await waitFor(() => {
    expect(JSON.parse(screen.getByTestId("auth-state").textContent || "{}")).toEqual({
      status: "authenticated",
      user: session.user,
      tenant: session.tenant,
      role: session.role,
      permissions: session.permissions,
      isSystemAdmin: true,
    });
  });
}

function expectCleared() {
  expect(JSON.parse(screen.getByTestId("auth-state").textContent || "{}")).toEqual({
    status: "unauthenticated",
    user: null,
    tenant: null,
    role: null,
    permissions: [],
    isSystemAdmin: false,
  });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("AuthProvider session clearing", () => {
  it("clears the complete prior session when refresh fails", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(session))
      .mockRejectedValueOnce(new Error("network unavailable"));

    renderProvider();
    await expectAuthenticated();
    fireEvent.click(screen.getByRole("button", { name: "refresh" }));

    await waitFor(expectCleared);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("clears the complete prior session when refresh returns an empty session", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(session))
      .mockResolvedValueOnce(jsonResponse({}));

    renderProvider();
    await expectAuthenticated();
    fireEvent.click(screen.getByRole("button", { name: "refresh" }));

    await waitFor(expectCleared);
  });

  it("clears the complete session when session expiry is announced", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse(session));

    renderProvider();
    await expectAuthenticated();
    act(() => window.dispatchEvent(new Event("saas:session-expired")));

    expectCleared();
  });

  it("clears the complete session even when logout fails", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(session))
      .mockResolvedValueOnce(jsonResponse({ error: { message: "failed" } }, 500));

    renderProvider();
    await expectAuthenticated();
    fireEvent.click(screen.getByRole("button", { name: "logout" }));

    await waitFor(expectCleared);
    expect(fetchMock).toHaveBeenLastCalledWith(
      "/api/auth/logout",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
