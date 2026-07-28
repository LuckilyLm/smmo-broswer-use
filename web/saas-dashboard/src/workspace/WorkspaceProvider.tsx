import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from "react";
import { apiGet, apiPost } from "../api/client";
import { useAuth } from "../auth/AuthProvider";

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  status: string;
  created_at: string;
  updated_at: string;
}

interface WorkspaceContextValue {
  currentTenant: Workspace | null;
  availableTenants: Workspace[];
  isLoading: boolean;
  switchTenant: (tenantId: string) => Promise<void>;
  refreshTenants: () => Promise<void>;
}

export const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used within WorkspaceProvider");
  return ctx;
}

interface WorkspaceProviderProps {
  children: ReactNode;
}

export function WorkspaceProvider({ children }: WorkspaceProviderProps) {
  const { status, tenant } = useAuth();
  const [currentTenant, setCurrentTenant] = useState<Workspace | null>(null);
  const [availableTenants, setAvailableTenants] = useState<Workspace[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const refreshTenants = useCallback(async () => {
    if (status !== "authenticated") {
      setCurrentTenant(null);
      setAvailableTenants([]);
      return;
    }
    setIsLoading(true);
    try {
      const data = await apiGet<Workspace[]>("/api/tenants");
      const tenants = Array.isArray(data) ? data : [];
      setAvailableTenants(tenants);
      // Set current from auth context if available
      if (tenant) {
        const current = tenants.find((t: Workspace) => t.id === tenant.id);
        setCurrentTenant(current || {
          id: tenant.id,
          name: tenant.name,
          slug: tenant.slug,
          status: tenant.status,
          created_at: "",
          updated_at: "",
        });
      }
    } catch {
      // Silently fail
    } finally {
      setIsLoading(false);
    }
  }, [status, tenant]);

  useEffect(() => {
    void refreshTenants();
  }, [refreshTenants]);

  const switchTenant = useCallback(async (tenantId: string) => {
    setIsLoading(true);
    try {
      await apiPost(`/api/tenants/${tenantId}/switch`, {});
      // Refresh page to reload with new tenant context
      window.location.reload();
    } catch {
      // Ignore
    } finally {
      setIsLoading(false);
    }
  }, []);

  const value: WorkspaceContextValue = {
    currentTenant,
    availableTenants,
    isLoading,
    switchTenant,
    refreshTenants,
  };

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}
