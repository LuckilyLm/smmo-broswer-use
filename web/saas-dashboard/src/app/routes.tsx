import {
  ApartmentOutlined,
  AuditOutlined,
  BarChartOutlined,
  CommentOutlined,
  ControlOutlined,
  DashboardOutlined,
  DollarOutlined,
  FileTextOutlined,
  KeyOutlined,
  PlayCircleOutlined,
  ProfileOutlined,
  SafetyCertificateOutlined,
  SettingOutlined,
  TeamOutlined,
  ThunderboltOutlined
} from "@ant-design/icons";
import type { MenuDataItem } from "@ant-design/pro-components";
import type { ReactNode } from "react";
import type { TFunction } from "i18next";

export type RouteDefinition = {
  path: string;
  nameKey: string;
  icon: ReactNode;
  group: "overview" | "leadGeneration" | "operations" | "workspace" | "system";
  managerOnly?: boolean;
  systemAdminOnly?: boolean;
};

export const appRoutes: RouteDefinition[] = [
  { path: "/dashboard", nameKey: "nav.dashboard", icon: <DashboardOutlined />, group: "overview" },
  { path: "/platform-accounts", nameKey: "nav.platforms", icon: <ApartmentOutlined />, group: "leadGeneration" },
  { path: "/campaigns", nameKey: "nav.campaigns", icon: <ThunderboltOutlined />, group: "leadGeneration" },
  { path: "/keywords", nameKey: "nav.keywords", icon: <KeyOutlined />, group: "leadGeneration" },
  { path: "/leads", nameKey: "nav.leads", icon: <CommentOutlined />, group: "leadGeneration" },
  { path: "/reply-templates", nameKey: "nav.replyTemplates", icon: <FileTextOutlined />, group: "leadGeneration" },
  { path: "/reply-match-rules", nameKey: "nav.replyMatchRules", icon: <ControlOutlined />, group: "leadGeneration" },
  { path: "/reply-tasks", nameKey: "nav.replyTasks", icon: <ProfileOutlined />, group: "leadGeneration" },
  { path: "/reply-records", nameKey: "nav.replyRecords", icon: <AuditOutlined />, group: "leadGeneration" },
  { path: "/reply-rules", nameKey: "nav.replyRules", icon: <ControlOutlined />, group: "leadGeneration" },
  { path: "/executions", nameKey: "nav.executions", icon: <PlayCircleOutlined />, group: "operations" },
  { path: "/token-usage", nameKey: "nav.tokenUsage", icon: <DollarOutlined />, group: "operations" },
  { path: "/usage", nameKey: "nav.usage", icon: <BarChartOutlined />, group: "workspace" },
  { path: "/members", nameKey: "nav.members", icon: <TeamOutlined />, group: "workspace", managerOnly: true },
  { path: "/audit-logs", nameKey: "nav.audit", icon: <AuditOutlined />, group: "workspace", managerOnly: true },
  { path: "/settings", nameKey: "nav.settings", icon: <SettingOutlined />, group: "workspace" },
  { path: "/admin", nameKey: "nav.adminDashboard", icon: <SafetyCertificateOutlined />, group: "system", systemAdminOnly: true },
  { path: "/admin/tenants", nameKey: "nav.tenants", icon: <ApartmentOutlined />, group: "system", systemAdminOnly: true },
  { path: "/admin/plans", nameKey: "nav.plans", icon: <BarChartOutlined />, group: "system", systemAdminOnly: true }
];

const groupKeys = ["overview", "leadGeneration", "operations", "workspace", "system"] as const;

export function canAccessRoute(route: RouteDefinition, role: string, isSystemAdmin: boolean) {
  if (route.systemAdminOnly) return isSystemAdmin;
  if (route.managerOnly) return role === "owner" || role === "admin";
  return true;
}

export function buildMenuRoutes(t: TFunction, role: string, isSystemAdmin: boolean): MenuDataItem[] {
  const menu: MenuDataItem[] = [];
  groupKeys.forEach((group) => {
    const routes = appRoutes.filter((route) => route.group === group && canAccessRoute(route, role, isSystemAdmin));
    if (routes.length) {
      menu.push({
        path: `group-${group}`,
        name: t(`nav.${group}`),
        type: "group",
        children: routes.map((route) => ({
          path: route.path,
          name: t(route.nameKey),
          icon: route.icon
        }))
      });
    }
  });
  return menu;
}

export function findRoute(path: string) {
  return appRoutes.find((route) => route.path === path);
}
