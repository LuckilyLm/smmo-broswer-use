import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost, apiPatch, apiDelete } from "./client";
import { toast } from "sonner";

// Raw types from backend
interface RawMatchingRule {
  id: string;
  campaign_id?: string;
  name: string;
  reply_template_id?: string;
  enabled: boolean;
  priority: number;
  contains_any_json?: string[];
  contains_all_json?: string[];
  exact_text?: string;
  regex_pattern?: string;
  author_exclude_json?: string[];
  comment_language?: string;
  minimum_length?: number;
  maximum_length?: number;
  created_at: string;
  updated_at: string;
}

// Normalized types for frontend
export interface MatchingRule {
  id: string;
  campaign_id?: string;
  name: string;
  pattern: string;
  match_type: "exact" | "contains" | "regex" | "keyword";
  template_id: string;
  priority: number;
  status: "active" | "paused";
  created_at: string;
  updated_at: string;
}

function normalizeRule(raw: RawMatchingRule): MatchingRule {
  // Determine match type and pattern from raw data
  let match_type: MatchingRule["match_type"] = "contains";
  let pattern = "";

  if (raw.exact_text) {
    match_type = "exact";
    pattern = raw.exact_text;
  } else if (raw.regex_pattern) {
    match_type = "regex";
    pattern = raw.regex_pattern;
  } else if (raw.contains_any_json?.length) {
    match_type = "contains";
    pattern = raw.contains_any_json.join(",");
  } else if (raw.contains_all_json?.length) {
    match_type = "contains";
    pattern = raw.contains_all_json.join(",");
  }

  return {
    id: raw.id,
    campaign_id: raw.campaign_id,
    name: raw.name,
    pattern,
    match_type,
    template_id: raw.reply_template_id || "",
    priority: raw.priority || 100,
    status: raw.enabled ? "active" : "paused",
    created_at: raw.created_at,
    updated_at: raw.updated_at,
  };
}

function denormalizeRule(data: Partial<MatchingRule>): Record<string, unknown> {
  const result: any = {};

  // Only include fields that are explicitly provided
  if (data.name !== undefined) result.name = data.name;
  if (data.campaign_id !== undefined) result.campaign_id = data.campaign_id;
  if (data.priority !== undefined) result.priority = data.priority;
  if (data.template_id !== undefined) result.reply_template_id = data.template_id;

  // For status, only set enabled if status is explicitly provided
  if (data.status !== undefined) {
    result.enabled = data.status === "active";
  }

  if (data.pattern !== undefined && data.match_type !== undefined) {
    switch (data.match_type) {
      case "exact":
        result.exact_text = data.pattern;
        break;
      case "regex":
        result.regex_pattern = data.pattern;
        break;
      case "contains":
      case "keyword":
        result.contains_any_json = data.pattern.split(",").map((s) => s.trim());
        break;
    }
  }

  return result;
}

export function useMatchingRules(campaignId?: string) {
  const url = campaignId
    ? `/api/reply-match-rules?campaign_id=${campaignId}`
    : "/api/reply-match-rules";

  return useQuery({
    queryKey: ["matching-rules", campaignId],
    queryFn: async () => {
      const raw = await apiGet<RawMatchingRule[]>(url);
      return raw.map(normalizeRule);
    },
  });
}

export function useCreateMatchingRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { campaign_id: string; name: string; pattern: string; match_type: MatchingRule["match_type"]; template_id: string; priority?: number }) =>
      apiPost<RawMatchingRule>("/api/reply-match-rules", denormalizeRule(data)),
    onSuccess: () => {
      toast.success("规则创建成功");
      queryClient.invalidateQueries({ queryKey: ["matching-rules"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "创建失败");
    },
  });
}

export function useUpdateMatchingRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<MatchingRule> }) =>
      apiPatch<RawMatchingRule>(`/api/reply-match-rules/${id}`, denormalizeRule(data)),
    onSuccess: () => {
      toast.success("规则更新成功");
      queryClient.invalidateQueries({ queryKey: ["matching-rules"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "更新失败");
    },
  });
}

export function useDeleteMatchingRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/api/reply-match-rules/${id}`),
    onSuccess: () => {
      toast.success("规则已删除");
      queryClient.invalidateQueries({ queryKey: ["matching-rules"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "删除失败");
    },
  });
}

export function useTestMatchingRule() {
  return useMutation({
    mutationFn: ({
      pattern,
      match_type,
      comment_text,
    }: {
      pattern: string;
      match_type: string;
      comment_text: string;
    }) => {
      const backendData: any = { comment_text };
      switch (match_type) {
        case "exact":
          backendData.exact_text = pattern;
          break;
        case "regex":
          backendData.regex_pattern = pattern;
          break;
        case "contains":
        case "keyword":
          backendData.contains_any_json = pattern.split(",").map((s) => s.trim());
          break;
      }
      return apiPost<{ matched: boolean; extracted_vars?: Record<string, string> }>(
        "/api/reply-match-rules/test",
        backendData
      );
    },
    onError: (error: any) => {
      toast.error(error.message || "测试失败");
    },
  });
}
