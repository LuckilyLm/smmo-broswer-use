import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost, apiPatch, apiDelete } from "./client";
import { toast } from "sonner";

// Raw types from backend
interface RawCampaign {
  id: string;
  name: string;
  description?: string | null;
  platform_account_id: string;
  platform_account_name?: string;
  platform?: string;
  status: string;
  target_policy?: string;
  max_contents?: number;
  max_comments?: number;
  min_confidence?: number;
  max_leads?: number;
  daily_limit?: number;
  llm_enabled?: boolean;
  lead_detection_mode?: string;
  reply_mode?: string;
  default_reply_template_id?: string | null;
  positive_keywords_json?: string[];
  negative_keywords_json?: string[];
  default_whatsapp?: string | null;
  default_email?: string | null;
  default_website?: string | null;
  default_contact_text?: string | null;
  reply_daily_limit?: number;
  reply_per_minute_limit?: number;
  reply_per_hour_limit?: number;
  reply_min_interval_seconds?: number;
  target_regions_json?: string[];
  content_types_json?: string[];
  content_language?: string;
  keyword_count: number;
  lead_count: number;
  pending_reply_count: number;
  last_execution_at?: string;
  created_at: string;
  updated_at: string;
}

interface RawCampaignDetail {
  campaign: RawCampaign;
  platform_account?: Record<string, any>;
  keywords?: any[];
  schedule?: Record<string, any>;
}

// Normalized types for frontend
export interface Campaign {
  id: string;
  name: string;
  description?: string | null;
  platform: string;
  platform_account_id: string;
  platform_account_name: string;
  status: string;
  target_policy?: string;
  max_contents?: number;
  max_comments?: number;
  min_confidence?: number;
  max_leads?: number;
  daily_limit?: number;
  llm_enabled?: boolean;
  lead_detection_mode?: string;
  reply_mode?: string;
  default_reply_template_id?: string | null;
  positive_keywords_json?: string[];
  negative_keywords_json?: string[];
  default_whatsapp?: string | null;
  default_email?: string | null;
  default_website?: string | null;
  default_contact_text?: string | null;
  reply_daily_limit?: number;
  reply_per_minute_limit?: number;
  reply_per_hour_limit?: number;
  reply_min_interval_seconds?: number;
  target_regions_json?: string[];
  content_types_json?: string[];
  content_language?: string;
  keywords_count: number;
  leads_count: number;
  pending_replies: number;
  last_run: string;
  created_at: string;
}

export interface CampaignDetail extends Campaign {
  platform_account_id: string;
  platform_account?: Record<string, any>;
  schedule?: {
    enabled: boolean;
    cron: string;
    timezone: string;
  };
  keywords?: any[];
}

export interface CampaignPayload extends Record<string, unknown> {
  name: string;
  description?: string | null;
  platform_account_id: string;
  status?: string;
  target_policy?: string;
  max_contents?: number;
  max_comments?: number;
  min_confidence?: number;
  max_leads?: number;
  daily_limit?: number;
  llm_enabled?: boolean;
  lead_detection_mode?: string;
  reply_mode?: string;
  default_reply_template_id?: string | null;
  positive_keywords_json?: string[];
  negative_keywords_json?: string[];
  default_whatsapp?: string | null;
  default_email?: string | null;
  default_website?: string | null;
  default_contact_text?: string | null;
  reply_daily_limit?: number;
  reply_per_minute_limit?: number;
  reply_per_hour_limit?: number;
  reply_min_interval_seconds?: number;
  target_regions_json?: string[];
  content_types_json?: string[];
  content_language?: string;
  initial_keywords?: string[];
}

function normalizeCampaign(raw: RawCampaign): Campaign {
  return {
    id: raw.id,
    name: raw.name,
    description: raw.description,
    platform: raw.platform || "unknown",
    platform_account_id: raw.platform_account_id,
    platform_account_name: raw.platform_account_name || raw.platform_account_id,
    status: raw.status,
    target_policy: raw.target_policy,
    max_contents: raw.max_contents,
    max_comments: raw.max_comments,
    min_confidence: raw.min_confidence,
    max_leads: raw.max_leads,
    daily_limit: raw.daily_limit,
    llm_enabled: raw.llm_enabled,
    lead_detection_mode: raw.lead_detection_mode,
    reply_mode: raw.reply_mode,
    default_reply_template_id: raw.default_reply_template_id,
    positive_keywords_json: raw.positive_keywords_json || [],
    negative_keywords_json: raw.negative_keywords_json || [],
    default_whatsapp: raw.default_whatsapp,
    default_email: raw.default_email,
    default_website: raw.default_website,
    default_contact_text: raw.default_contact_text,
    reply_daily_limit: raw.reply_daily_limit,
    reply_per_minute_limit: raw.reply_per_minute_limit,
    reply_per_hour_limit: raw.reply_per_hour_limit,
    reply_min_interval_seconds: raw.reply_min_interval_seconds,
    target_regions_json: raw.target_regions_json || [],
    content_types_json: raw.content_types_json || [],
    content_language: raw.content_language,
    keywords_count: raw.keyword_count || 0,
    leads_count: raw.lead_count || 0,
    pending_replies: raw.pending_reply_count || 0,
    last_run: raw.last_execution_at
      ? new Date(raw.last_execution_at).toLocaleString("zh-CN")
      : "—",
    created_at: raw.created_at,
  };
}

function normalizeCampaignDetail(raw: RawCampaignDetail): CampaignDetail {
  const campaign = normalizeCampaign(raw.campaign);
  return {
    ...campaign,
    platform_account_id: raw.campaign.platform_account_id,
    platform_account: raw.platform_account,
    schedule: raw.schedule
      ? {
          enabled: raw.schedule.enabled ?? false,
          cron: raw.schedule.cron || "",
          timezone: raw.schedule.timezone || "UTC",
        }
      : undefined,
    keywords: raw.keywords || [],
  };
}

export function useCampaigns() {
  return useQuery({
    queryKey: ["campaigns"],
    queryFn: async () => {
      const raw = await apiGet<RawCampaign[] | { items: RawCampaign[] }>("/api/campaigns");
      const items = Array.isArray(raw) ? raw : raw.items || [];
      return items.map(normalizeCampaign);
    },
  });
}

export function useCampaign(id: string) {
  return useQuery({
    queryKey: ["campaigns", id],
    queryFn: async () => {
      const raw = await apiGet<RawCampaignDetail>(`/api/campaigns/${id}`);
      return normalizeCampaignDetail(raw);
    },
    enabled: !!id,
  });
}

export function useCreateCampaign() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CampaignPayload) =>
      apiPost<RawCampaign>("/api/campaigns", data),
    onSuccess: () => {
      toast.success("活动创建成功");
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "创建失败");
    },
  });
}

export function useUpdateCampaign() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<CampaignPayload> }) =>
      apiPatch<RawCampaign>(`/api/campaigns/${id}`, data),
    onSuccess: (_, variables) => {
      toast.success("更新成功");
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      queryClient.invalidateQueries({ queryKey: ["campaigns", variables.id] });
    },
    onError: (error: any) => {
      toast.error(error.message || "更新失败");
    },
  });
}

export function useDeleteCampaign() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/api/campaigns/${id}`),
    onSuccess: () => {
      toast.success("活动已删除");
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "删除失败");
    },
  });
}

export function useRunCampaign() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiPost<{ execution_id: string }>(`/api/campaigns/${id}/run`, {}),
    onSuccess: () => {
      toast.success("活动已开始执行");
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
      queryClient.invalidateQueries({ queryKey: ["executions"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "执行失败");
    },
  });
}
