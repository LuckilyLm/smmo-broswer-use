import { lazy, Suspense, useState } from "react"

import { QueryClientProvider } from "@tanstack/react-query"

import { Toaster } from "sonner"

import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  useLocation,
} from "react-router-dom"

import { queryClient } from "./lib/query-client"

import { AuthProvider } from "./auth/AuthProvider"

import { WorkspaceProvider } from "./workspace/WorkspaceProvider"

import { RequireAuth } from "./auth/RequireAuth"

import { RequireSystemAdmin } from "./auth/RequireSystemAdmin"

import Sidebar from "./components/layout/Sidebar"

import TopBar from "./components/layout/TopBar"

import LoginPage from "./pages/LoginPage"

import InvitationPage from "./pages/InvitationPage"

import ChangePasswordPage from "./pages/ChangePasswordPage"

const Dashboard = lazy(() => import("./pages/Dashboard"))

const Campaigns = lazy(() => import("./pages/Campaigns"))

const CampaignSettings = lazy(() => import("./pages/CampaignSettings"))

const ReplyTemplates = lazy(() => import("./pages/ReplyTemplates"))

const MatchingRules = lazy(() => import("./pages/MatchingRules"))

const ReplyTasks = lazy(() => import("./pages/ReplyTasks"))

const ReplyRecords = lazy(() => import("./pages/ReplyRecords"))

const LeadsInbox = lazy(() => import("./pages/LeadsInbox"))

const PlatformAccounts = lazy(() => import("./pages/PlatformAccounts"))

const ExecutionRecords = lazy(() => import("./pages/ExecutionRecords"))

const Settings = lazy(() => import("./pages/Settings"))

const Keywords = lazy(() => import("./pages/Keywords"))

const TokenUsage = lazy(() => import("./pages/TokenUsage"))

const Members = lazy(() => import("./pages/Members"))

const AuditLog = lazy(() => import("./pages/AuditLog"))

const NotificationCenter = lazy(() => import("./pages/NotificationCenter"))

const SystemAdmin = lazy(() => import("./pages/SystemAdmin"))

function RouteLoadingFallback() {
  return (
    <div
      className="flex min-h-48 items-center justify-center"
      role="status"
      aria-live="polite"
      aria-label="页面加载中"
    >
      <span
        className="h-8 w-8 animate-spin rounded-full border-2 border-muted border-b-primary"
        aria-hidden="true"
      />
      <span className="sr-only">页面加载中</span>
    </div>
  )
}

function RouteSuspense({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<RouteLoadingFallback />}>{children}</Suspense>
}

function AppContent() {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false)

  const location = useLocation()

  const isAuthPage =
    location.pathname === "/login" ||
    location.pathname.startsWith("/invitations/") ||
    location.pathname === "/change-password"

  if (isAuthPage) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/change-password" element={<ChangePasswordPage />} />
        <Route path="/invitations/:token" element={<InvitationPage />} />
      </Routes>
    )
  }

  return (
    <RequireAuth>
      <div className="flex h-dvh min-h-0 flex-col overflow-hidden bg-background">
        <TopBar onMenuOpen={() => setMobileSidebarOpen(true)} />
        <div className="flex min-h-0 flex-1 overflow-hidden">
          <Sidebar
            mobileOpen={mobileSidebarOpen}
            onMobileClose={() => setMobileSidebarOpen(false)}
          />
          <main
            data-testid="app-main-scroll"
            className="min-h-0 min-w-0 flex-1 overflow-y-auto overscroll-contain"
          >
            <RouteSuspense>
              <Routes>
                <Route
                  path="/"
                  element={<Navigate to="/dashboard" replace />}
                />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/campaigns" element={<Campaigns />} />
                <Route path="/campaigns/new" element={<CampaignSettings />} />
                <Route
                  path="/campaigns/:campaignId"
                  element={<CampaignSettings />}
                />
                <Route
                  path="/platform-accounts"
                  element={<PlatformAccounts />}
                />
                <Route path="/keywords" element={<Keywords />} />
                <Route path="/leads" element={<LeadsInbox />} />
                <Route path="/leads-inbox" element={<LeadsInbox />} />
                <Route path="/reply-templates" element={<ReplyTemplates />} />
                <Route path="/reply-rules" element={<MatchingRules />} />
                <Route path="/matching-rules" element={<MatchingRules />} />
                <Route path="/reply-tasks" element={<ReplyTasks />} />
                <Route path="/reply-records" element={<ReplyRecords />} />
                <Route path="/executions" element={<ExecutionRecords />} />
                <Route
                  path="/execution-records"
                  element={<ExecutionRecords />}
                />
                <Route path="/token-usage" element={<TokenUsage />} />
                <Route path="/members" element={<Members />} />
                <Route path="/audit-logs" element={<AuditLog />} />
                <Route path="/notifications" element={<NotificationCenter />} />
                <Route path="/settings" element={<Settings />} />
                <Route
                  path="/system-admin"
                  element={
                    <RequireSystemAdmin>
                      <SystemAdmin />
                    </RequireSystemAdmin>
                  }
                />
                <Route
                  path="*"
                  element={<Navigate to="/dashboard" replace />}
                />
              </Routes>
            </RouteSuspense>
          </main>
        </div>
      </div>
    </RequireAuth>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <WorkspaceProvider>
            <AppContent />
            <Toaster position="top-right" richColors />
          </WorkspaceProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
