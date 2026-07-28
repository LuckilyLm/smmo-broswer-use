import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost, apiPatch, apiDelete } from "./client";
import { toast } from "sonner";

// Backend returns nested runtime object
interface RawPlatformAccount {
  id: string;
  platform: string;
  handle?: string;
  display_name?: string;
  external_account_name?: string | null;
  connection_status?: string;
  login_status?: string;
  runtime?: {
    status?: string;
    cdp_port?: number;
    profile_status?: string;
  } | null;
  last_checked?: string;
  last_checked_at?: string | null;
  last_login_check_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlatformAccount {
  id: string;
  platform: string;
  handle: string;
  display_name: string;
  connection_status: string;
  login_status: string;
  runtime_status: string;
  cdp_port: number | null;
  profile_status: string;
  last_checked: string;
  color: string;
}

export interface RuntimeCapabilities {
  runtime_host: string;
  runtime_available: boolean;
  browser_platform: string;
  local_browser_supported: boolean;
  browser_backend?: string;
  browser_headless?: boolean;
}

const PLATFORM_COLORS: Record<string, string> = {
  facebook: "#1877f2",
  instagram: "#e1306c",
  tiktok: "#010101",
  x: "#1da1f2",
  youtube: "#ff0000",
  twitter: "#1da1f2",
};

function normalizeAccount(raw: RawPlatformAccount): PlatformAccount {
  const runtime = raw.runtime || {};
  const handle = raw.external_account_name || raw.handle || `@${raw.platform}_account`;
  const lastChecked = raw.last_checked_at || raw.last_login_check_at || raw.last_checked || "—";
  return {
    id: raw.id,
    platform: raw.platform,
    handle,
    display_name: raw.display_name || handle || `${raw.platform} 账号`,
    connection_status: raw.connection_status || "unknown",
    login_status: raw.login_status || "unknown",
    runtime_status: runtime.status || "stopped",
    cdp_port: runtime.cdp_port ?? null,
    profile_status: runtime.profile_status || "unknown",
    last_checked: formatCheckedAt(lastChecked),
    color: PLATFORM_COLORS[raw.platform.toLowerCase()] || "#6366f1",
  };
}

function formatCheckedAt(value: string): string {
  if (!value || value === "—") return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function usePlatformAccounts() {
  return useQuery({
    queryKey: ["platform-accounts"],
    queryFn: async () => {
      const raw = await apiGet<RawPlatformAccount[]>("/api/platform-accounts");
      return raw.map(normalizeAccount);
    },
  });
}

export function useRuntimeCapabilities() {
  return useQuery({
    queryKey: ["runtime-capabilities"],
    queryFn: () => apiGet<RuntimeCapabilities>("/api/system/runtime-capabilities"),
  });
}

export function useCreatePlatformAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { platform: string; handle?: string; display_name?: string }) =>
      apiPost<RawPlatformAccount>("/api/platform-accounts", data),
    onSuccess: () => {
      toast.success("账号添加成功");
      queryClient.invalidateQueries({ queryKey: ["platform-accounts"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "添加失败");
    },
  });
}

export function useUpdatePlatformAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<PlatformAccount> }) =>
      apiPatch<RawPlatformAccount>(`/api/platform-accounts/${id}`, data),
    onSuccess: () => {
      toast.success("更新成功");
      queryClient.invalidateQueries({ queryKey: ["platform-accounts"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "更新失败");
    },
  });
}

export function useDeletePlatformAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/api/platform-accounts/${id}`),
    onSuccess: () => {
      toast.success("账号已删除");
      queryClient.invalidateQueries({ queryKey: ["platform-accounts"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "删除失败");
    },
  });
}

export function useConnectPlatformAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiPost(`/api/platform-accounts/${id}/connect`),
    onSuccess: () => {
      toast.success("连接成功");
      queryClient.invalidateQueries({ queryKey: ["platform-accounts"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "连接失败");
    },
  });
}

export function useCheckLoginPlatformAccount() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiPost(`/api/platform-accounts/${id}/check-login`),
    onSuccess: () => {
      toast.success("登录状态检查完成");
      queryClient.invalidateQueries({ queryKey: ["platform-accounts"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "检查失败");
    },
  });
}

export function useStopRuntime() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiPost(`/api/platform-accounts/${id}/stop-runtime`),
    onSuccess: () => {
      toast.success("运行时已停止");
      queryClient.invalidateQueries({ queryKey: ["platform-accounts"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "操作失败");
    },
  });
}

export function useRestartRuntime() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiPost(`/api/platform-accounts/${id}/restart-runtime`),
    onSuccess: () => {
      toast.success("运行时已重启");
      queryClient.invalidateQueries({ queryKey: ["platform-accounts"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "操作失败");
    },
  });
}
