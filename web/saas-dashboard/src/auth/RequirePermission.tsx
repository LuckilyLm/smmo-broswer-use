import { useAuth } from "./AuthProvider";
import type { ReactNode } from "react";

interface RequirePermissionProps {
  permission: string;
  children: ReactNode;
  fallback?: ReactNode;
}

export function RequirePermission({ permission, children, fallback }: RequirePermissionProps) {
  const { hasPermission, status } = useAuth();

  if (status === "initializing") {
    return (
      <div className="flex items-center justify-center h-screen bg-background">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <span className="text-sm text-gray-500">加载中...</span>
        </div>
      </div>
    );
  }

  if (!hasPermission(permission)) {
    if (fallback) return <>{fallback}</>;
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-background">
        <div className="text-sm text-gray-500">权限不足，无法访问此页面</div>
      </div>
    );
  }

  return <>{children}</>;
}
