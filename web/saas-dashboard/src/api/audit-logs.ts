import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./client";

export interface AuditLog {
  id: string;
  tenant_id?: string;
  timestamp: string;
  created_at?: string;
  user_id: string;
  user_email?: string;
  user_display_name?: string;
  action: string;
  resource_type: string;
  resource_id?: string | null;
  resource_name?: string;
  result?: "success" | "failure";
  ip_address?: string;
  user_agent?: string;
  details?: Record<string, any>;
  metadata_json?: Record<string, any>;
}

export function useAuditLogs(params?: {
  user_id?: string;
  action?: string;
  resource_type?: string;
  start_date?: string;
  end_date?: string;
  limit?: number;
  offset?: number;
}) {
  const searchParams = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) searchParams.append(key, String(value));
    });
  }

  return useQuery({
    queryKey: ["audit-logs", params],
    queryFn: () =>
      apiGet<{
        items: AuditLog[];
        total: number;
        limit: number;
        offset: number;
      }>(`/api/audit-logs?${searchParams.toString()}`),
  });
}
