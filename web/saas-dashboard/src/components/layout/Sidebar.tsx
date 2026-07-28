import { useNavigate, useLocation } from "react-router-dom";
import {
  LayoutDashboard, Users, Megaphone, Tag, Inbox,
  FileText, GitBranch, CheckSquare, Clock,
  Activity, Zap, UserCheck, ScrollText,
  Bell, Settings, Shield, LogOut
} from "lucide-react";
import { useAuth } from "../../auth/AuthProvider";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent } from "@/components/ui/sheet";

interface NavItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  badge?: number;
  adminOnly?: boolean;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

function getNavGroups(isSystemAdmin?: boolean): NavGroup[] {
  const groups: NavGroup[] = [
    {
      label: "概览",
      items: [
        { id: "dashboard", label: "仪表盘", icon: <LayoutDashboard className="h-4 w-4" /> },
      ],
    },
    {
      label: "获客管理",
      items: [
        { id: "platform-accounts", label: "平台账号", icon: <Users className="h-4 w-4" /> },
        { id: "campaigns", label: "营销活动", icon: <Megaphone className="h-4 w-4" /> },
        { id: "keywords", label: "关键词", icon: <Tag className="h-4 w-4" /> },
        { id: "leads-inbox", label: "线索收件箱", icon: <Inbox className="h-4 w-4" /> },
      ],
    },
    {
      label: "回复自动化",
      items: [
        { id: "reply-templates", label: "回复模板", icon: <FileText className="h-4 w-4" /> },
        { id: "matching-rules", label: "匹配规则", icon: <GitBranch className="h-4 w-4" /> },
        { id: "reply-tasks", label: "回复任务", icon: <CheckSquare className="h-4 w-4" /> },
        { id: "reply-records", label: "回复记录", icon: <Clock className="h-4 w-4" /> },
      ],
    },
    {
      label: "运营管理",
      items: [
        { id: "execution-records", label: "执行记录", icon: <Activity className="h-4 w-4" /> },
        { id: "token-usage", label: "Token 用量", icon: <Zap className="h-4 w-4" /> },
      ],
    },
    {
      label: "组织管理",
      items: [
        { id: "members", label: "成员管理", icon: <UserCheck className="h-4 w-4" /> },
        { id: "audit-logs", label: "审计日志", icon: <ScrollText className="h-4 w-4" /> },
        { id: "notifications", label: "通知中心", icon: <Bell className="h-4 w-4" /> },
      ],
    },
  ];

  if (isSystemAdmin) {
    groups.push({
      label: "系统",
      items: [
        { id: "settings", label: "设置", icon: <Settings className="h-4 w-4" /> },
        { id: "system-admin", label: "系统管理", icon: <Shield className="h-4 w-4" />, adminOnly: true },
      ],
    });
  } else {
    groups.push({
      label: "系统",
      items: [
        { id: "settings", label: "设置", icon: <Settings className="h-4 w-4" /> },
      ],
    });
  }

  return groups;
}

interface SidebarProps {
  mobileOpen?: boolean;
  onMobileClose?: () => void;
}

function NavContent({ activePage, onNavigate, collapsed }: { activePage: string; onNavigate: (page: string) => void; collapsed?: boolean }) {
  const { isSystemAdmin } = useAuth();
  const navGroups = getNavGroups(isSystemAdmin);

  return (
    <nav className="flex flex-col gap-1 p-2">
      {navGroups.map((group) => (
        <div key={group.label} className="mb-2">
          {!collapsed && (
            <div className="px-3 py-1.5 text-xs font-medium text-muted-foreground uppercase tracking-wider">
              {group.label}
            </div>
          )}
          {group.items.map((item) => {
            const isActive = activePage === item.id;
            return (
              <Button
                key={item.id}
                variant={isActive ? "secondary" : "ghost"}
                className={collapsed ? "w-full justify-center h-9 px-0" : "w-full justify-start gap-2 h-9 text-sm"}
                title={collapsed ? item.label : undefined}
                onClick={() => onNavigate(item.id)}
              >
                <span className={isActive ? "text-primary" : "text-muted-foreground"}>
                  {item.icon}
                </span>
                {!collapsed && <span className="flex-1 text-left">{item.label}</span>}
                {!collapsed && item.badge !== undefined && item.badge > 0 && (
                  <Badge variant={isActive ? "default" : "secondary"} className="h-5 min-w-5 px-1 text-xs">
                    {item.badge}
                  </Badge>
                )}
              </Button>
            );
          })}
        </div>
      ))}
    </nav>
  );
}

function UserMenu({ collapsed }: { collapsed?: boolean }) {
  const { user, role, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  const roleText = role === "owner" ? "所有者" : role === "admin" ? "管理员" : role === "member" ? "成员" : "访客";
  const userInitial = user?.display_name?.[0] || user?.email?.[0] || "?";

  if (collapsed) {
    return (
      <DropdownMenu>
        <DropdownMenuTrigger>
          <Button variant="ghost" size="icon" className="h-8 w-8 rounded-full" title={user?.display_name || user?.email || "用户"}>
            <Avatar className="h-8 w-8">
              <AvatarFallback className="bg-primary text-primary-foreground text-xs font-medium">
                {userInitial}
              </AvatarFallback>
            </Avatar>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-48">
          <div className="px-2 py-1.5 text-sm font-medium">{user?.display_name || user?.email || "用户"}</div>
          <div className="px-2 pb-2 text-xs text-muted-foreground">{roleText}</div>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => navigate("/settings")}>
            <Settings className="mr-2 h-4 w-4" />
            设置
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={handleLogout} className="text-destructive focus:text-destructive">
            <LogOut className="mr-2 h-4 w-4" />
            退出登录
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger>
        <Button variant="ghost" className="w-full justify-start gap-2 px-2 h-auto py-2">
          <Avatar className="h-8 w-8">
            <AvatarFallback className="bg-primary text-primary-foreground text-xs font-medium">
              {userInitial}
            </AvatarFallback>
          </Avatar>
          <div className="flex-1 min-w-0 text-left">
            <p className="text-sm font-medium truncate">{user?.display_name || user?.email || "用户"}</p>
            <p className="text-xs text-muted-foreground truncate">{roleText}</p>
          </div>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        <DropdownMenuItem onClick={() => navigate("/settings")}>
          <Settings className="mr-2 h-4 w-4" />
          设置
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={handleLogout} className="text-destructive focus:text-destructive">
          <LogOut className="mr-2 h-4 w-4" />
          退出登录
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export default function Sidebar({ mobileOpen, onMobileClose }: SidebarProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { tenant } = useAuth();
  const activePage = location.pathname.split("/")[1] || "dashboard";

  const handleNavigate = (page: string) => {
    navigate(`/${page}`);
    onMobileClose?.();
  };

  return (
    <>
      {/* Desktop Sidebar */}
      <aside data-testid="desktop-sidebar" className="hidden h-full min-h-0 w-[220px] shrink-0 flex-col overflow-hidden border-r bg-sidebar md:flex">
        <div data-testid="sidebar-nav-scroll" data-scroll-region className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
          <NavContent activePage={activePage} onNavigate={handleNavigate} collapsed={false} />
        </div>

        <div data-testid="sidebar-footer" className="shrink-0 border-t bg-sidebar p-2">
          <UserMenu />
        </div>
      </aside>

      {/* Mobile Drawer */}
      <Sheet open={mobileOpen} onOpenChange={onMobileClose}>
        <SheetContent side="left" className="h-dvh max-h-dvh w-60 min-h-0 gap-0 overflow-hidden p-0 pb-[env(safe-area-inset-bottom)]">
          <div data-testid="mobile-sidebar-header" className="flex shrink-0 items-center gap-2 border-b p-3">
            <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center">
              <span className="text-primary-foreground font-bold text-sm">SM</span>
            </div>
            <span className="font-medium truncate">{tenant?.name}</span>
          </div>
          <div data-testid="mobile-sidebar-nav-scroll" data-scroll-region className="min-h-0 flex-1 overflow-y-auto overscroll-contain touch-pan-y">
            <NavContent activePage={activePage} onNavigate={handleNavigate} collapsed={false} />
          </div>
          <div data-testid="mobile-sidebar-footer" className="shrink-0 border-t bg-sidebar p-2">
            <UserMenu />
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
