import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPatch } from "./client";
import { toast } from "sonner";

// Raw response from backend
interface RawSettings {
  tenant: {
    id: string;
    name: string;
    slug: string;
    timezone?: string;
    language?: string;
    status: string;
    default_target_policy?: "owned_only" | "allowlist" | "discovery_only";
    default_min_confidence?: number;
    default_daily_limit?: number;
    default_whatsapp?: string;
    default_email?: string;
    default_website?: string;
    default_contact_text?: string;
    tenant_reply_enabled?: boolean;
    created_at: string;
    updated_at: string;
  };
  system_send_enabled: boolean;
  reply_safety_message: string;
  approval_mode: string;
}

// Normalized for frontend. Read-only system fields are retained for display,
// but useUpdateSettings only sends UpdateTenantSettingsRequest fields.
export interface Settings {
  tenant_id: string;
  tenant_name: string;
  timezone: string;
  language: string;
  default_target_policy: "owned_only" | "allowlist" | "discovery_only";
  default_min_confidence: number;
  default_daily_limit: number;
  default_whatsapp: string;
  default_email: string;
  default_website: string;
  default_contact_text: string;
  tenant_reply_enabled: boolean;
  system_send_enabled: boolean;
  reply_safety_message: string;
  approval_mode: string;
  created_at: string;
  updated_at: string;
}

export type UpdateSettingsInput = Partial<Pick<
  Settings,
  | "tenant_name"
  | "timezone"
  | "default_target_policy"
  | "default_min_confidence"
  | "default_daily_limit"
  | "default_whatsapp"
  | "default_email"
  | "default_website"
  | "default_contact_text"
  | "tenant_reply_enabled"
>>;

function normalizeSettings(raw: RawSettings): Settings {
  return {
    tenant_id: raw.tenant?.id || "",
    tenant_name: raw.tenant?.name || "",
    timezone: raw.tenant?.timezone || "UTC",
    language: raw.tenant?.language || "zh-CN",
    default_target_policy: raw.tenant?.default_target_policy || "discovery_only",
    default_min_confidence: raw.tenant?.default_min_confidence ?? 0.5,
    default_daily_limit: raw.tenant?.default_daily_limit ?? 100,
    default_whatsapp: raw.tenant?.default_whatsapp || "",
    default_email: raw.tenant?.default_email || "",
    default_website: raw.tenant?.default_website || "",
    default_contact_text: raw.tenant?.default_contact_text || "",
    tenant_reply_enabled: raw.tenant?.tenant_reply_enabled ?? false,
    system_send_enabled: raw.system_send_enabled ?? false,
    reply_safety_message: raw.reply_safety_message || "",
    approval_mode: raw.approval_mode || "manual",
    created_at: raw.tenant?.created_at || "",
    updated_at: raw.tenant?.updated_at || "",
  };
}

export function useSettings() {
  return useQuery({
    queryKey: ["settings"],
    queryFn: async () => {
      const raw = await apiGet<RawSettings>("/api/settings");
      return normalizeSettings(raw);
    },
  });
}

export function useUpdateSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: UpdateSettingsInput) => {
      const backendData: Record<string, unknown> = {};
      if (data.tenant_name !== undefined) backendData.name = data.tenant_name;
      if (data.timezone !== undefined) backendData.timezone = data.timezone;
      if (data.default_target_policy !== undefined) backendData.default_target_policy = data.default_target_policy;
      if (data.default_min_confidence !== undefined) backendData.default_min_confidence = data.default_min_confidence;
      if (data.default_daily_limit !== undefined) backendData.default_daily_limit = data.default_daily_limit;
      if (data.default_whatsapp !== undefined) backendData.default_whatsapp = data.default_whatsapp;
      if (data.default_email !== undefined) backendData.default_email = data.default_email;
      if (data.default_website !== undefined) backendData.default_website = data.default_website;
      if (data.default_contact_text !== undefined) backendData.default_contact_text = data.default_contact_text;
      if (data.tenant_reply_enabled !== undefined) backendData.tenant_reply_enabled = data.tenant_reply_enabled;
      return apiPatch<RawSettings>("/api/settings", backendData);
    },
    onSuccess: () => {
      toast.success("设置已保存");
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "保存失败");
    },
  });
}
