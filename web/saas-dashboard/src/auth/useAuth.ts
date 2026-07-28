import { useCallback, useEffect, useState } from "react";
import type { AuthUser, UserRole } from "../auth/AuthProvider";
import type { Tenant } from "../types";

export function useAuth() {
  const [status, setStatus] = useState<"initializing" | "authenticated" | "unauthenticated">("initializing");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [role, setRole] = useState<UserRole | null>(null);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [isSystemAdmin, setIsSystemAdmin] = useState(false);

  const refreshSession = useCallback(async () => {
    try {
      const response = await fetch("/api/auth/session", {
        credentials: "include",
      });
      if (!response.ok) throw new Error("Session invalid");
      const data = await response.json();
      setUser(data.user);
      setTenant(data.tenant);
      setRole(data.role || "viewer");
      setPermissions(data.permissions || []);
      setIsSystemAdmin(!!data.user?.is_system_admin);
      setStatus("authenticated");
    } catch {
      setStatus("unauthenticated");
    }
  }, []);

  useEffect(() => {
    refreshSession();
  }, [refreshSession]);

  const login = useCallback(async (email: string, password: string) => {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!response.ok) throw new Error("Login failed");
    const data = await response.json();
    setUser(data.user);
    setTenant(data.tenant);
    setRole(data.role || "viewer");
    setPermissions(data.permissions || []);
    setIsSystemAdmin(!!data.user?.is_system_admin);
    setStatus("authenticated");
  }, []);

  const logout = useCallback(async () => {
    await fetch("/api/auth/logout", {
      method: "POST",
      credentials: "include",
    });
    setUser(null);
    setTenant(null);
    setRole(null);
    setPermissions([]);
    setIsSystemAdmin(false);
    setStatus("unauthenticated");
  }, []);

  const hasPermission = useCallback((permission: string) => {
    if (isSystemAdmin) return true;
    return permissions.includes(permission);
  }, [permissions, isSystemAdmin]);

  return {
    status,
    user,
    tenant,
    role,
    permissions,
    isSystemAdmin,
    login,
    logout,
    hasPermission,
    refreshSession,
  };
}
