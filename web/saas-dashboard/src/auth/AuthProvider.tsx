import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  type ReactNode,
} from "react";
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

interface AuthState {
  status: AuthStatus;
  user: AuthUser | null;
  tenant: Tenant | null;
  role: UserRole | null;
  permissions: string[];
}

type AuthAction =
  | { type: "session-restored"; session: AuthSession }
  | { type: "session-cleared" };

const initialAuthState: AuthState = {
  status: "initializing",
  user: null,
  tenant: null,
  role: null,
  permissions: [],
};

const unauthenticatedState: AuthState = {
  status: "unauthenticated",
  user: null,
  tenant: null,
  role: null,
  permissions: [],
};

function authReducer(_state: AuthState, action: AuthAction): AuthState {
  if (action.type === "session-cleared") return unauthenticatedState;

  return {
    status: "authenticated",
    user: action.session.user,
    tenant: action.session.tenant,
    role: action.session.role,
    permissions: action.session.permissions,
  };
}

function parseSession(data: unknown): AuthSession | null {
  if (!data || typeof data !== "object") return null;
  const candidate = data as Partial<AuthSession>;
  if (!candidate.user || !candidate.tenant) return null;
  return {
    user: candidate.user,
    tenant: candidate.tenant,
    role: candidate.role || "viewer",
    permissions: Array.isArray(candidate.permissions) ? candidate.permissions : [],
  };
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
  const [state, dispatch] = useReducer(authReducer, initialAuthState);

  const refreshSession = useCallback(async () => {
    try {
      const data = await apiGet<unknown>("/api/auth/session");
      const session = parseSession(data);
      if (session) dispatch({ type: "session-restored", session });
      else dispatch({ type: "session-cleared" });
    } catch {
      dispatch({ type: "session-cleared" });
    }
  }, []);

  useEffect(() => {
    void refreshSession();
  }, [refreshSession]);

  useEffect(() => {
    const handler = () => dispatch({ type: "session-cleared" });
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
      // Local authentication state must still be cleared if the server is unavailable.
    } finally {
      dispatch({ type: "session-cleared" });
    }
  }, []);

  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    await apiPost("/api/auth/change-password", {
      current_password: currentPassword,
      new_password: newPassword,
    });
  }, []);

  const isSystemAdmin = !!state.user?.is_system_admin;
  const hasPermission = useCallback((permission: string): boolean => {
    if (isSystemAdmin) return true;
    return state.permissions.includes(permission);
  }, [state.permissions, isSystemAdmin]);

  const value = useMemo<AuthContextValue>(() => ({
    ...state,
    isSystemAdmin,
    login,
    logout,
    changePassword,
    refreshSession,
    hasPermission,
  }), [state, isSystemAdmin, login, logout, changePassword, refreshSession, hasPermission]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
