import { describe, expect, it } from "vitest";
import i18n from "../i18n";
import { appRoutes, buildMenuRoutes, canAccessRoute, findRoute } from "./routes";

describe("route configuration", () => {
  it("groups tenant navigation into the requested sections", () => {
    const groups = buildMenuRoutes(i18n.t, "owner", false);
    expect(groups.map((group) => group.name)).toEqual(["Overview", "Lead Generation", "Operations", "Workspace"]);
    expect(groups.flatMap((group) => group.children || []).map((route) => route.path)).toContain("/settings");
  });

  it("keeps manager routes out of viewer menus", () => {
    const paths = buildMenuRoutes(i18n.t, "viewer", false).flatMap((group) => group.children || []).map((route) => route.path);
    expect(paths).not.toContain("/members");
    expect(paths).not.toContain("/audit-logs");
  });

  it("loads system routes only for system administrators", () => {
    const adminRoute = findRoute("/admin")!;
    expect(canAccessRoute(adminRoute, "owner", false)).toBe(false);
    expect(canAccessRoute(adminRoute, "viewer", true)).toBe(true);
    expect(appRoutes.filter((route) => route.systemAdminOnly)).toHaveLength(3);
  });

  it("provides route names for global breadcrumbs", () => {
    expect(findRoute("/executions")?.nameKey).toBe("nav.executions");
    expect(findRoute("/settings")?.group).toBe("workspace");
  });
});
