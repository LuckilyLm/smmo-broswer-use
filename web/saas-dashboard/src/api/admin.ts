import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPatch } from "./client";
import { toast } from "sonner";

// Backend returns pagination object
interface PaginatedResponse<T> {
  items: T[];
  limit: number;
  offset: number;
  total: number;
}

// Raw types from backend
interface RawTenant {
  id: string;
  name: string;
  slug: string;
  status: string;
  subscription_plan: string;
  subscription_status: string;
  subscription_expires_at?: string;
  member_count: number;
  campaign_count: number;
  created_at: string;
  updated_at: string;
}

interface RawPlan {
  id: string;
  name: string;
  description: string;
  price_monthly: number;
  price_yearly: number;
  currency: string;
  features: Record<string, any>;
  limits: {
    campaigns: number;
    platform_accounts: number;
    members: number;
    keywords: number;
    reply_templates: number;
    monthly_tokens: number;
    monthly_leads: number;
  };
}

interface RawSystemUsage {
  total_tenants: number;
  active_tenants: number;
  total_campaigns: number;
  total_leads: number;
  total_tokens_used: number;
  total_platform_accounts: number;
}

// Normalized types for frontend
export interface Tenant {
  id: string;
  name: string;
  slug: string;
  status: "active" | "suspended" | "cancelled";
  subscription_plan: string;
  subscription_status: string;
  subscription_expires_at?: string;
  member_count: number;
  campaign_count: number;
  created_at: string;
  updated_at: string;
}

export interface SubscriptionPlan {
  id: string;
  name: string;
  description: string;
  price_monthly: number;
  price_yearly: number;
  currency: string;
  features: Record<string, any>;
  limits: {
    campaigns: number;
    platform_accounts: number;
    members: number;
    keywords: number;
    reply_templates: number;
    monthly_tokens: number;
    monthly_leads: number;
  };
}

export interface SystemUsage {
  total_tenants: number;
  active_tenants: number;
  total_campaigns: number;
  total_leads: number;
  total_tokens_used: number;
  total_platform_accounts: number;
}

function normalizeTenant(raw: RawTenant): Tenant {
  return {
    ...raw,
    status: (raw.status as Tenant["status"]) || "active",
  };
}

export function useAdminTenants() {
  return useQuery({
    queryKey: ["admin", "tenants"],
    queryFn: async () => {
      const raw = await apiGet<PaginatedResponse<RawTenant>>("/api/admin/tenants");
      return {
        ...raw,
        items: raw.items?.map(normalizeTenant) || [],
      };
    },
  });
}

export function useAdminTenant(id: string) {
  return useQuery({
    queryKey: ["admin", "tenants", id],
    queryFn: async () => {
      const raw = await apiGet<RawTenant>(`/api/admin/tenants/${id}`);
      return normalizeTenant(raw);
    },
    enabled: !!id,
  });
}

export function useAdminPlans() {
  return useQuery({
    queryKey: ["admin", "plans"],
    queryFn: () => apiGet<RawPlan[]>("/api/admin/plans"),
  });
}

export function useSystemUsage() {
  return useQuery({
    queryKey: ["admin", "system-usage"],
    queryFn: () => apiGet<RawSystemUsage>("/api/admin/system/usage"),
  });
}

export function useUpdateTenantSubscription() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: { plan_id: string; status?: string; expires_at?: string };
    }) => apiPatch<RawTenant>(`/api/admin/tenants/${id}/subscription`, data),
    onSuccess: () => {
      toast.success("订阅已更新");
      queryClient.invalidateQueries({ queryKey: ["admin", "tenants"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "更新失败");
    },
  });
}
