import {
  GlobalOutlined,
  KeyOutlined,
  LogoutOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  TeamOutlined,
  UserOutlined
} from "@ant-design/icons";
import { ProLayout } from "@ant-design/pro-components";
import {
  Button,
  Card,
  ConfigProvider,
  Dropdown,
  Form,
  Input,
  Result,
  Select,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
  message,
  theme as antdTheme
} from "antd";
import enUS from "antd/locale/en_US";
import zhCN from "antd/locale/zh_CN";
import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { apiGet, apiPost, type ApiRecord } from "./api";
import { buildMenuRoutes, canAccessRoute, findRoute } from "./app/routes";
import { NotificationDrawer } from "./components/NotificationDrawer";
import { PageLoading } from "./components/Page";
import { type AppLocale, setAppLocale } from "./i18n";
import type { Tenant } from "./types";

const DashboardPage = lazy(() => import("./pages/DashboardPage").then((module) => ({ default: module.DashboardPage })));
const PlatformAccountsPage = lazy(() => import("./pages/PlatformAccountsPage").then((module) => ({ default: module.PlatformAccountsPage })));
const CampaignsPage = lazy(() => import("./pages/CampaignsPage").then((module) => ({ default: module.CampaignsPage })));
const KeywordsPage = lazy(() => import("./pages/KeywordsPage").then((module) => ({ default: module.KeywordsPage })));
const LeadsPage = lazy(() => import("./pages/LeadsPage").then((module) => ({ default: module.LeadsPage })));
const ReplyRulesPage = lazy(() => import("./pages/ReplyRulesPage").then((module) => ({ default: module.ReplyRulesPage })));
const ReplyTemplatesPage = lazy(() => import("./pages/ReplyTemplatesPage").then((module) => ({ default: module.ReplyTemplatesPage })));
const ReplyMatchRulesPage = lazy(() => import("./pages/ReplyMatchRulesPage").then((module) => ({ default: module.ReplyMatchRulesPage })));
const ReplyTasksPage = lazy(() => import("./pages/ReplyTasksPage").then((module) => ({ default: module.ReplyTasksPage })));
const ReplyRecordsPage = lazy(() => import("./pages/ReplyRecordsPage").then((module) => ({ default: module.ReplyRecordsPage })));
const ExecutionsPage = lazy(() => import("./pages/ExecutionsPage").then((module) => ({ default: module.ExecutionsPage })));
const TokenUsagePage = lazy(() => import("./pages/TokenUsagePage").then((module) => ({ default: module.TokenUsagePage })));
const UsagePage = lazy(() => import("./pages/UsagePage").then((module) => ({ default: module.UsagePage })));
const MembersPage = lazy(() => import("./pages/MembersPage").then((module) => ({ default: module.MembersPage })));
const AuditLogsPage = lazy(() => import("./pages/AuditLogsPage").then((module) => ({ default: module.AuditLogsPage })));
const SettingsPage = lazy(() => import("./pages/SettingsPage").then((module) => ({ default: module.SettingsPage })));
const AdminPage = lazy(() => import("./pages/AdminPage").then((module) => ({ default: module.AdminPage })));
const ChangePasswordPage = lazy(() => import("./pages/ChangePasswordPage").then((module) => ({ default: module.ChangePasswordPage })));
const InvitationAcceptPage = lazy(() => import("./pages/InvitationAcceptPage").then((module) => ({ default: module.InvitationAcceptPage })));

const pageComponents: Record<string, React.LazyExoticComponent<React.ComponentType>> = {
  "/dashboard": DashboardPage,
  "/platform-accounts": PlatformAccountsPage,
  "/campaigns": CampaignsPage,
  "/keywords": KeywordsPage,
  "/leads": LeadsPage,
  "/reply-rules": ReplyRulesPage,
  "/reply-templates": ReplyTemplatesPage,
  "/reply-match-rules": ReplyMatchRulesPage,
  "/reply-tasks": ReplyTasksPage,
  "/reply-records": ReplyRecordsPage,
  "/executions": ExecutionsPage,
  "/token-usage": TokenUsagePage,
  "/usage": UsagePage,
  "/audit-logs": AuditLogsPage,
  "/settings": SettingsPage,
  "/admin": AdminPage,
  "/admin/tenants": AdminPage,
  "/admin/plans": AdminPage
};

function currentPath() {
  return window.location.pathname === "/" ? "/dashboard" : window.location.pathname;
}

export default function App() {
  const { i18n } = useTranslation();
  const locale = (i18n.resolvedLanguage === "zh-CN" ? "zh-CN" : "en-US") as AppLocale;
  return (
    <ConfigProvider
      locale={locale === "zh-CN" ? zhCN : enUS}
      theme={{ token: { borderRadius: 6, colorPrimary: "#14635c", fontFamily: "Inter, Segoe UI, Arial, sans-serif" } }}
    >
      <AppSession locale={locale} />
    </ConfigProvider>
  );
}

function AppSession({ locale }: { locale: AppLocale }) {
  const { t } = useTranslation();
  const [authState, setAuthState] = useState<"checking" | "authenticated" | "anonymous">("checking");
  const [path, setPath] = useState(currentPath);
  const [me, setMe] = useState<ApiRecord | null>(null);

  const navigate = (next: string, replace = false) => {
    window.history[replace ? "replaceState" : "pushState"]({}, "", next);
    setPath(next);
  };

  const refreshMe = async () => {
    const current = await apiGet<ApiRecord>("/api/auth/me");
    setMe(current);
    setAuthState("authenticated");
    return current;
  };

  useEffect(() => {
    let cancelled = false;
    apiGet<ApiRecord>("/api/auth/me")
      .then((value) => {
        if (cancelled) return;
        setMe(value);
        setAuthState("authenticated");
        if (value.user?.must_change_password) navigate("/change-password", true);
      })
      .catch(() => { if (!cancelled) setAuthState("anonymous"); });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const pop = () => setPath(currentPath());
    const expired = () => {
      setMe(null);
      setAuthState("anonymous");
      navigate("/login", true);
    };
    window.addEventListener("popstate", pop);
    window.addEventListener("saas:session-expired", expired);
    return () => {
      window.removeEventListener("popstate", pop);
      window.removeEventListener("saas:session-expired", expired);
    };
  }, []);

  if (authState === "checking") return <div className="login-page"><Spin size="large" /></div>;

  if (authState === "anonymous") {
    if (path.startsWith("/invite/")) {
      return <Suspense fallback={<PageLoading />}><InvitationAcceptPage token={path.slice(8)} authenticated={false} onAccepted={() => navigate("/login")} /></Suspense>;
    }
    return <LoginPage onLogin={async () => {
      const current = await refreshMe();
      navigate(current.user?.must_change_password ? "/change-password" : "/dashboard");
    }} />;
  }

  if (me?.user?.must_change_password) {
    return <Suspense fallback={<PageLoading />}><ChangePasswordPage onChanged={() => {
      setMe(null);
      setAuthState("anonymous");
      navigate("/login");
    }} /></Suspense>;
  }

  if (path.startsWith("/invite/")) {
    return <Suspense fallback={<PageLoading />}><InvitationAcceptPage token={path.slice(8)} authenticated onAccepted={() => navigate("/dashboard")} /></Suspense>;
  }

  return <AuthenticatedLayout me={me!} path={path} locale={locale} navigate={navigate} refreshMe={refreshMe} />;
}

function AuthenticatedLayout({
  me,
  path,
  locale,
  navigate,
  refreshMe
}: {
  me: ApiRecord;
  path: string;
  locale: AppLocale;
  navigate: (path: string, replace?: boolean) => void;
  refreshMe: () => Promise<ApiRecord>;
}) {
  const { t } = useTranslation();
  const [collapsed, setCollapsed] = useState(() => window.localStorage.getItem("leadflow_menu_collapsed") === "true");
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const role = String(me.role || "viewer");
  const isSystemAdmin = Boolean(me.user?.is_system_admin);
  const menuRoutes = useMemo(() => buildMenuRoutes(t, role, isSystemAdmin), [t, role, isSystemAdmin, locale]);

  useEffect(() => {
    apiGet<Tenant[]>("/api/tenants").then(setTenants).catch(() => setTenants([]));
  }, [me.tenant?.id]);

  const route = findRoute(path);
  const denied = route && !canAccessRoute(route, role, isSystemAdmin);
  const PageComponent = pageComponents[path];
  const content = denied ? (
    <Result status="403" title="403" subTitle={t("common.permissionDenied")} extra={<Button onClick={() => navigate("/dashboard")}>{t("common.backDashboard")}</Button>} />
  ) : path === "/members" ? (
    <MembersPage currentUserId={String(me.user?.id || "")} role={role} />
  ) : PageComponent ? (
    <PageComponent />
  ) : (
    <Result status="404" title="404" subTitle={t("common.pageNotFound")} extra={<Button onClick={() => navigate("/dashboard")}>{t("common.backDashboard")}</Button>} />
  );

  return (
    <ProLayout
      className="app-shell"
      title={t("app.name")}
      logo={<SafetyCertificateOutlined />}
      layout="mix"
      navTheme="light"
      fixedHeader
      fixSiderbar
      collapsed={collapsed}
      onCollapse={(value) => {
        setCollapsed(value);
        window.localStorage.setItem("leadflow_menu_collapsed", String(value));
      }}
      location={{ pathname: path }}
      route={{ path: "/", routes: menuRoutes }}
      menuItemRender={(item, dom) => item.path?.startsWith("/") ? <a href={item.path} onClick={(event) => { event.preventDefault(); navigate(item.path!); }}>{dom}</a> : dom}
      breadcrumbRender={(routers = []) => routers}
      actionsRender={() => [
        <WorkspaceSwitcher key="workspace" tenants={tenants} currentId={String(me.tenant?.id || "")} onSwitch={async (id) => {
          await apiPost(`/api/tenants/${id}/switch`);
          await refreshMe();
          navigate("/dashboard");
          message.success(t("app.switchWorkspace"));
        }} />,
        <Tooltip key="safety" title={t("app.safetyTip")}><Tag color="green" icon={<SafetyCertificateOutlined />}>{t("app.safety")}</Tag></Tooltip>,
        <Tooltip key="language" title={t("app.language")}>
          <Select
            aria-label={t("app.language")}
            className="language-switch"
            value={locale}
            suffixIcon={<GlobalOutlined />}
            onChange={(value: AppLocale) => void setAppLocale(value)}
            options={[{ value: "zh-CN", label: t("app.languageChinese") }, { value: "en-US", label: t("app.languageEnglish") }]}
          />
        </Tooltip>,
        <NotificationDrawer key="notifications" />,
        <UserMenu key="user" me={me} navigate={navigate} />
      ]}
    >
      <ConfigProvider theme={{ algorithm: antdTheme.defaultAlgorithm }}>
        <Suspense fallback={<PageLoading />}>{content}</Suspense>
      </ConfigProvider>
    </ProLayout>
  );
}

export function WorkspaceSwitcher({ tenants, currentId, onSwitch }: { tenants: Tenant[]; currentId: string; onSwitch: (id: string) => Promise<void> }) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  return (
    <Select
      aria-label={t("app.switchWorkspace")}
      className="workspace-switch"
      value={currentId}
      loading={loading}
      onChange={async (id) => {
        setLoading(true);
        try { await onSwitch(id); } finally { setLoading(false); }
      }}
      options={tenants.map((tenant) => ({ value: tenant.id, label: tenant.name }))}
    />
  );
}

function UserMenu({ me, navigate }: { me: ApiRecord; navigate: (path: string) => void }) {
  const { t } = useTranslation();
  const items = [
    { key: "profile", icon: <UserOutlined />, label: t("app.profile"), onClick: () => navigate("/settings") },
    { key: "members", icon: <TeamOutlined />, label: t("nav.members"), onClick: () => navigate("/members") },
    { key: "settings", icon: <SettingOutlined />, label: t("nav.settings"), onClick: () => navigate("/settings") },
    ...(me.user?.is_system_admin ? [{ key: "admin", icon: <SafetyCertificateOutlined />, label: t("nav.adminDashboard"), onClick: () => navigate("/admin") }] : []),
    { type: "divider" as const },
    { key: "logout", icon: <LogoutOutlined />, label: t("app.logout"), onClick: async () => {
      await apiPost("/api/auth/logout");
      window.location.assign("/login");
    } }
  ];
  return (
    <Dropdown menu={{ items }} trigger={["click"]}>
      <Button type="text" icon={<UserOutlined />}>{String(me.user?.display_name || "")}</Button>
    </Dropdown>
  );
}

function LoginPage({ onLogin }: { onLogin: () => Promise<void> }) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  return (
    <div className="login-page">
      <Card className="login-panel">
        <Space direction="vertical" size={20} style={{ width: "100%" }}>
          <div><div className="brand">{t("app.name")}</div><Typography.Text className="muted">{t("auth.signInHint")}</Typography.Text></div>
          <Form layout="vertical" onFinish={async (values) => {
            setLoading(true);
            try {
              await apiPost("/api/auth/login", values);
              await onLogin();
            } catch {
              message.error(t("auth.failed"));
            } finally {
              setLoading(false);
            }
          }}>
            <Form.Item name="email" label={t("common.email")} rules={[{ required: true }]}><Input autoComplete="email" /></Form.Item>
            <Form.Item name="password" label={t("auth.password")} rules={[{ required: true }]}><Input.Password autoComplete="current-password" /></Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block icon={<KeyOutlined />}>{t("auth.signIn")}</Button>
          </Form>
        </Space>
      </Card>
    </div>
  );
}
