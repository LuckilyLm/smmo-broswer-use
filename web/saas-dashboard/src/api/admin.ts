import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./client";

export interface PaginatedResponse<T> {
  items: T[];
  limit: number;
  offset: number;
  total: number;
}

export interface TenantPlan {
  id?: string;
  code?: string;
  name?: string;
}

export interface TenantUsage {
  campaigns?: number;
  members?: number;
  platform_accounts?: number;
  monthly_leads?: number;
  monthly_tokens?: number;
  [key: string]: number | undefined;
}

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  status: string;
  timezone?: string;
  plan?: TenantPlan;
  usage?: TenantUsage;
  created_at: string;
  updated_at: string;
}

export interface AdminUser {
  id: string;
  email: string;
  display_name: string;
  status: string;
  must_change_password: boolean;
  is_system_admin: boolean;
  created_at: string;
  updated_at: string;
}

export interface WorkerHealth {
  online: boolean;
  last_heartbeat_at?: string | null;
  worker_count: number;
}

export interface SchedulerHealth {
  online: boolean;
  last_tick_at?: string | null;
  due_campaign_count: number;
  last_error?: string | null;
  queued_tasks: number;
  running_tasks: number;
}

export interface SystemHealth {
  api: { status: string };
  postgres: { status: string };
  worker: WorkerHealth;
  scheduler: SchedulerHealth;
  queue: Record<string, number>;
  browser_runtimes: { count: number };
}

export interface BrowserRuntime {
  id: string;
  tenant_id: string;
  platform_account_id: string;
  runtime_type: string;
  status: string;
  cdp_port: number;
  browser_pid?: number | null;
  started_at?: string | null;
  last_health_check_at?: string | null;
  stopped_at?: string | null;
  last_error?: string | null;
  created_at: string;
  updated_at: string;
}

export interface QueueItem {
  id: string;
  tenant_id: string;
  campaign_id: string;
  execution_id: string;
  status: string;
  priority: number;
  queued_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  run_after: string;
  attempt_count: number;
  max_attempts: number;
  error_type?: string | null;
  error_message?: string | null;
}

export interface SystemUsage {
  tenants: number;
  users: number;
  executions: number;
  tokens: number;
  worker_health: number;
}

export function useAdminTenants() {
  return useQuery({
    queryKey: ["admin", "tenants"],
    queryFn: () => apiGet<PaginatedResponse<Tenant>>("/api/admin/tenants?limit=200"),
  });
}

export function useAdminUsers() {
  return useQuery({
    queryKey: ["admin", "users"],
    queryFn: () => apiGet<PaginatedResponse<AdminUser>>("/api/admin/users?limit=200"),
  });
}

export function useSystemUsage() {
  return useQuery({
    queryKey: ["admin", "system-usage"],
    queryFn: () => apiGet<SystemUsage>("/api/admin/system/usage"),
  });
}

export function useSystemHealth() {
  return useQuery({
    queryKey: ["admin", "system-health"],
    queryFn: () => apiGet<SystemHealth>("/api/admin/system/health"),
  });
}

export function useAdminRuntimes() {
  return useQuery({
    queryKey: ["admin", "runtimes"],
    queryFn: () => apiGet<PaginatedResponse<BrowserRuntime>>("/api/admin/system/runtimes?limit=200"),
  });
}

export function useAdminQueue() {
  return useQuery({
    queryKey: ["admin", "queue"],
    queryFn: () => apiGet<PaginatedResponse<QueueItem>>("/api/admin/system/queue?limit=200"),
  });
}
