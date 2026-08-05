import { readFile } from "node:fs/promises"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

const appSourcePath = resolve(process.cwd(), "src/App.tsx")

async function readAppSource() {
  return readFile(appSourcePath, "utf8")
}

describe("App dashboard routes", () => {
  it("loads dashboard page modules lazily behind a shared Suspense boundary", async () => {
    const source = await readAppSource()
    const dashboardPages = [
      "Dashboard",
      "Campaigns",
      "CampaignSettings",
      "ReplyTemplates",
      "MatchingRules",
      "ReplyTasks",
      "ReplyRecords",
      "LeadsInbox",
      "PlatformAccounts",
      "ExecutionRecords",
      "Settings",
      "Keywords",
      "TokenUsage",
      "Members",
      "AuditLog",
      "NotificationCenter",
      "SystemAdmin",
    ]

    for (const page of dashboardPages) {
      expect(source).toMatch(
        new RegExp(
          `const\\s+${page}\\s*=\\s*lazy\\(\\(\\)\\s*=>\\s*import\\("\\./pages/${page}"\\)\\)`,
        ),
      )
      expect(source).not.toMatch(
        new RegExp(`import\\s+${page}\\s+from\\s+"\\./pages/${page}"`),
      )
    }

    expect(source).toContain("<RouteSuspense>")
    expect(source).toContain("<Suspense fallback={<RouteLoadingFallback />}>")
  })

  it("keeps auth pages eager and preserves redirect and guarded admin routes", async () => {
    const source = await readAppSource()

    expect(source).toMatch(/import\s+LoginPage\s+from\s+"\.\/pages\/LoginPage"/)
    expect(source).toContain('<Route path="/login" element={<LoginPage />} />')
    expect(source).toMatch(
      /path="\/"[\s\S]*?element=\{<Navigate to="\/dashboard" replace \/>\}/,
    )
    expect(source).toMatch(
      /path="\*"[\s\S]*?element=\{<Navigate to="\/dashboard" replace \/>\}/,
    )
    expect(source).toMatch(
      /path="\/system-admin"[\s\S]*?<RequireSystemAdmin>[\s\S]*?<SystemAdmin \/>[\s\S]*?<\/RequireSystemAdmin>/,
    )
  })

  it("announces the route loading state to assistive technology", async () => {
    const source = await readAppSource()

    expect(source).toContain('role="status"')
    expect(source).toContain('aria-live="polite"')
    expect(source).toContain('aria-label="页面加载中"')
    expect(source).toContain('<span className="sr-only">页面加载中</span>')
  })
})
