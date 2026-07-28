import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost, apiPatch } from "./client";
import { toast } from "sonner";

export interface Lead {
  id: string;
  campaign_id: string;
  platform: string;
  external_id: string;
  author_name: string;
  comment_text: string;
  final_intent_level: string;
  manual_intent_level: string | null;
  status: string;
  matched_search_keywords: string[];
  created_at: string;
  updated_at: string;
}

export interface LeadDetail extends Lead {
  campaign?: Record<string, any>;
  platform_account?: Record<string, any>;
  notes?: Array<{
    id: string;
    note: string;
    created_at: string;
  }>;
}

export interface LeadsFilter {
  campaign_id?: string;
  platform?: string;
  intent_level?: string;
  status?: string;
  start_date?: string;
  end_date?: string;
  search?: string;
}

export interface LeadsResponse {
  items: Lead[];
  total: number;
  limit: number;
  offset: number;
}

function normalizeLead(raw: any): Lead {
  return {
    id: raw.id,
    campaign_id: raw.campaign_id,
    platform: raw.platform,
    external_id: raw.external_id,
    author_name: raw.author_name || raw.author || "",
    comment_text: raw.comment_text || raw.content || "",
    final_intent_level: raw.final_intent_level || raw.intent_level || "low",
    manual_intent_level: raw.manual_intent_level || null,
    status: raw.status || "new",
    matched_search_keywords: raw.matched_search_keywords || raw.matched_keywords || [],
    created_at: raw.created_at,
    updated_at: raw.updated_at,
  };
}

export function useLeads(filters?: LeadsFilter, limit = 50, offset = 0) {
  const params = new URLSearchParams();
  if (filters) {
    Object.entries(filters).forEach(([key, value]) => {
      if (value) params.append(key, value);
    });
  }
  params.append("limit", String(limit));
  params.append("offset", String(offset));

  return useQuery({
    queryKey: ["leads", filters, limit, offset],
    queryFn: async () => {
      const raw = await apiGet<LeadsResponse>(`/api/leads?${params.toString()}`);
      return {
        ...raw,
        items: raw.items?.map(normalizeLead) || [],
      };
    },
  });
}

export function useLead(id: string) {
  return useQuery({
    queryKey: ["leads", id],
    queryFn: async () => {
      const raw = await apiGet<LeadDetail>(`/api/leads/${id}`);
      return { ...raw, ...normalizeLead(raw) };
    },
    enabled: !!id,
  });
}

export function useUpdateLead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Lead> }) =>
      apiPatch<Lead>(`/api/leads/${id}`, data),
    onSuccess: (_, variables) => {
      toast.success("线索更新成功");
      queryClient.invalidateQueries({ queryKey: ["leads"] });
      queryClient.invalidateQueries({ queryKey: ["leads", variables.id] });
    },
    onError: (error: any) => {
      toast.error(error.message || "更新失败");
    },
  });
}

export function useMarkLeadContacted() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiPost<Lead>(`/api/leads/${id}/mark-contacted`, {}),
    onSuccess: () => {
      toast.success("已标记为已联系");
      queryClient.invalidateQueries({ queryKey: ["leads"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "操作失败");
    },
  });
}

export function useMarkLeadInvalid() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      apiPost<Lead>(`/api/leads/${id}/mark-invalid`, { invalid_reason: reason }),
    onSuccess: () => {
      toast.success("已标记为无效");
      queryClient.invalidateQueries({ queryKey: ["leads"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "操作失败");
    },
  });
}

export function useAssignLead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, assignedUserId }: { id: string; assignedUserId: string }) =>
      apiPost<Lead>(`/api/leads/${id}/assign`, { assigned_user_id: assignedUserId }),
    onSuccess: () => {
      toast.success("已分配");
      queryClient.invalidateQueries({ queryKey: ["leads"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "操作失败");
    },
  });
}
