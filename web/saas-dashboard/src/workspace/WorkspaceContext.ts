import { createContext } from "react";

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceContextValue {
  currentTenant: Workspace | null;
  availableTenants: Workspace[];
  isLoading: boolean;
  switchTenant: (tenantId: string) => Promise<void>;
  refreshTenants: () => Promise<void>;
}

export const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);
