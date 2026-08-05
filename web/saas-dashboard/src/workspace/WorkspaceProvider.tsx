import { useState, useCallback, useEffect, useMemo, useRef, type ReactNode } from "react";
import { apiGet, apiPost } from "../api/client";
import { useAuth } from "../auth/AuthProvider";
import { WorkspaceContext, type Workspace, type WorkspaceContextValue } from "./WorkspaceContext";

export type { Workspace } from "./WorkspaceContext";

interface WorkspaceProviderProps {
  children: ReactNode;
}

export function WorkspaceProvider({ children }: WorkspaceProviderProps) {
  const { status, tenant } = useAuth();
  const [currentTenant, setCurrentTenant] = useState<Workspace | null>(null);
  const [availableTenants, setAvailableTenants] = useState<Workspace[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const refreshRequestRef = useRef(0);

  const refreshTenants = useCallback(async () => {
    const requestId = ++refreshRequestRef.current;
    if (status !== "authenticated") {
      setCurrentTenant(null);
      setAvailableTenants([]);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    try {
      const data = await apiGet<Workspace[]>("/api/tenants");
      if (requestId !== refreshRequestRef.current) return;
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
      if (requestId === refreshRequestRef.current) setIsLoading(false);
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

  const value = useMemo<WorkspaceContextValue>(() => ({
    currentTenant,
    availableTenants,
    isLoading,
    switchTenant,
    refreshTenants,
  }), [currentTenant, availableTenants, isLoading, switchTenant, refreshTenants]);

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}
