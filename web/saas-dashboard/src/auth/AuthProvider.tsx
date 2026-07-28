import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from "react";
import { apiGet, apiPost } from "../api/client";

export type UserRole = "owner" | "admin" | "member" | "viewer";

export interface AuthUser {
  id: string;
  email: string;
  display_name?: string;
  avatar_url?: string;
  is_system_admin?: boolean;
}

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  status: string;
}

export interface AuthSession {
  user: AuthUser;
  tenant: Tenant;
  role: UserRole;
  permissions: string[];
}

export type AuthStatus = "initializing" | "authenticated" | "unauthenticated";

interface AuthContextValue {
  status: AuthStatus;
  user: AuthUser | null;
  tenant: Tenant | null;
  role: UserRole | null;
  permissions: string[];
  isSystemAdmin: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  refreshSession: () => Promise<void>;
  hasPermission: (permission: string) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [status, setStatus] = useState<AuthStatus>("initializing");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [tenant, setTenant] = useState<Tenant | null>(null);
  const [role, setRole] = useState<UserRole | null>(null);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [isSystemAdmin, setIsSystemAdmin] = useState(false);

  const parseSession = useCallback((data: any): AuthSession | null => {
    if (!data?.user || !data?.tenant) return null;
    return {
      user: data.user as AuthUser,
      tenant: data.tenant as Tenant,
      role: (data.role || "viewer") as UserRole,
      permissions: Array.isArray(data.permissions) ? data.permissions : [],
    };
  }, []);

  const refreshSession = useCallback(async () => {
    try {
      const data = await apiGet<any>("/api/auth/session");
      const session = parseSession(data);
      if (session) {
        setUser(session.user);
        setTenant(session.tenant);
        setRole(session.role);
        setPermissions(session.permissions);
        setIsSystemAdmin(!!session.user.is_system_admin);
        setStatus("authenticated");
      } else {
        setStatus("unauthenticated");
      }
    } catch {
      setStatus("unauthenticated");
    }
  }, [parseSession]);

  useEffect(() => {
    refreshSession();
  }, [refreshSession]);

  useEffect(() => {
    const handler = () => {
      setUser(null);
      setTenant(null);
      setRole(null);
      setPermissions([]);
      setIsSystemAdmin(false);
      setStatus("unauthenticated");
    };
    window.addEventListener("saas:session-expired", handler);
    return () => window.removeEventListener("saas:session-expired", handler);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    await apiPost("/api/auth/login", { email, password });
    // The login response only contains user + tenant_id. Restore the complete
    // session context (tenant, role and permissions) from the session endpoint.
    await refreshSession();
  }, [refreshSession]);

  const logout = useCallback(async () => {
    try {
      await apiPost("/api/auth/logout");
    } catch {
      // Ignore logout errors
    }
    setUser(null);
    setTenant(null);
    setRole(null);
    setPermissions([]);
    setIsSystemAdmin(false);
    setStatus("unauthenticated");
  }, []);

  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    await apiPost("/api/auth/change-password", {
      current_password: currentPassword,
      new_password: newPassword,
    });
  }, []);

  const hasPermission = useCallback((permission: string): boolean => {
    if (isSystemAdmin) return true;
    return permissions.includes(permission);
  }, [permissions, isSystemAdmin]);

  const value: AuthContextValue = {
    status,
    user,
    tenant,
    role,
    permissions,
    isSystemAdmin,
    login,
    logout,
    changePassword,
    refreshSession,
    hasPermission,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
