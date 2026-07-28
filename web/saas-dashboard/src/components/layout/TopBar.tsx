import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  Bell,
  Building2,
  ChevronDown,
  Globe,
  LogOut,
  Menu,
  Settings,
} from "lucide-react";
import { useAuth } from "../../auth/AuthProvider";
import { useWorkspace } from "../../workspace/WorkspaceProvider";
import { setAppLocale, type AppLocale } from "../../i18n";
import { useNotifications } from "../../api/notifications";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

interface TopBarProps {
  onMenuOpen: () => void;
}

export default function TopBar({ onMenuOpen }: TopBarProps) {
  const navigate = useNavigate();
  const { i18n } = useTranslation();
  const { user, logout } = useAuth();
  const { currentTenant, availableTenants, switchTenant } = useWorkspace();
  const { data: notifications } = useNotifications(true, 5);

  const locale: AppLocale = i18n.language.startsWith("zh") ? "zh-CN" : "en-US";
  const userInitial = user?.display_name?.[0] || user?.email?.[0] || "?";
  const unreadCount = notifications?.unread_count || 0;

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <header className="relative z-30 flex h-16 shrink-0 items-center border-b bg-card/95 backdrop-blur">
      <div className="hidden h-full w-[220px] shrink-0 items-center overflow-hidden border-r px-4 md:flex">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary text-sm font-bold text-primary-foreground shadow-sm">
          SM
        </div>
      </div>

      <div className="flex min-w-0 flex-1 items-center justify-end gap-2 px-3 md:px-6">
      <Button
        variant="ghost"
        size="icon"
        className="md:hidden"
        onClick={onMenuOpen}
        aria-label="打开导航菜单"
      >
        <Menu className="h-5 w-5" />
      </Button>

      <div className="min-w-0 flex-1" />

      <div className="hidden w-64 min-w-0 md:block">
        <DropdownMenu>
          <DropdownMenuTrigger>
            <Button variant="outline" className="h-10 w-full min-w-0 justify-start gap-2 px-3">
              <Building2 className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="min-w-0 flex-1 truncate text-left font-medium">{currentTenant?.name || "加载中..."}</span>
              <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-64">
            {availableTenants.map((tenant: { id: string; name: string }) => (
              <DropdownMenuItem key={tenant.id} onClick={() => switchTenant(tenant.id)}>
                <Building2 className="mr-2 h-4 w-4 text-muted-foreground" />
                <span className="flex-1 truncate">{tenant.name}</span>
                {tenant.id === currentTenant?.id && <span className="h-2 w-2 rounded-full bg-primary" />}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <Button variant="ghost" size="icon" className="relative" onClick={() => navigate("/notifications")} aria-label="通知中心">
        <Bell className="h-4 w-4 text-muted-foreground" />
        {unreadCount > 0 && (
          <span className="absolute right-2 top-2 h-2 w-2 rounded-full bg-destructive ring-2 ring-card" />
        )}
      </Button>

      <DropdownMenu>
        <DropdownMenuTrigger>
          <Button variant="outline" className="hidden h-9 gap-1.5 px-3 md:flex">
            <Globe className="h-4 w-4" />
            {locale === "zh-CN" ? "中文" : "EN"}
            <ChevronDown className="h-3 w-3 text-muted-foreground" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={() => setAppLocale("zh-CN")}>中文</DropdownMenuItem>
          <DropdownMenuItem onClick={() => setAppLocale("en-US")}>English</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <DropdownMenu>
        <DropdownMenuTrigger>
          <Button variant="ghost" size="icon" className="rounded-full">
            <Avatar className="h-8 w-8">
              <AvatarFallback className="bg-primary text-xs font-semibold text-primary-foreground">
                {userInitial}
              </AvatarFallback>
            </Avatar>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-52">
          <div className="px-2 py-1.5">
            <p className="truncate text-sm font-medium">{user?.display_name || "用户"}</p>
            <p className="truncate text-xs text-muted-foreground">{user?.email}</p>
          </div>
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
      </div>
    </header>
  );
}
