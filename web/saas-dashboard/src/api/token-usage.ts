import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./client";

// Raw response from backend
interface RawTokenUsageSummary {
  today?: number | null;
  last_7_days?: number | null;
  this_month?: number | null;
  total?: number | null;
}

interface RawTokenUsageDetail {
  id: string;
  campaign_id?: string;
  execution_id?: string;
  operation?: string;
  tokens_used?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  request_count?: number;
  model: string;
  estimated_cost?: number | null;
  cost?: number | null;
  created_at: string;
}

// Normalized types for frontend
export interface TokenUsageSummary {
  total_tokens_used: number | null;
  tokens_used_today: number | null;
  tokens_used_this_month: number | null;
}

export interface TokenUsageDetail {
  id: string;
  campaign_id?: string;
  execution_id?: string;
  operation: string;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  tokens_used: number | null;
  request_count: number;
  model: string;
  cost: number | null;
  created_at: string;
}

function normalizeDetail(raw: RawTokenUsageDetail): TokenUsageDetail {
  const prompt = raw.prompt_tokens ?? null;
  const completion = raw.completion_tokens ?? null;
  const derivedTotal = prompt != null && completion != null ? prompt + completion : null;
  return {
    id: raw.id,
    campaign_id: raw.campaign_id,
    execution_id: raw.execution_id,
    operation: raw.operation || "lead_detection",
    prompt_tokens: prompt,
    completion_tokens: completion,
    tokens_used: raw.total_tokens ?? raw.tokens_used ?? derivedTotal,
    request_count: raw.request_count ?? 1,
    model: raw.model,
    cost: raw.estimated_cost ?? raw.cost ?? null,
    created_at: raw.created_at,
  };
}

function normalizeSummary(raw: RawTokenUsageSummary): TokenUsageSummary {
  return {
    total_tokens_used: raw.total ?? raw.last_7_days ?? raw.this_month ?? raw.today ?? null,
    tokens_used_today: raw.today ?? null,
    tokens_used_this_month: raw.this_month ?? null,
  };
}

export function useTokenUsageSummary() {
  return useQuery({
    queryKey: ["token-usage", "summary"],
    queryFn: async () => {
      const raw = await apiGet<RawTokenUsageSummary>("/api/token-usage/summary");
      return normalizeSummary(raw);
    },
  });
}

export function useTokenUsageDetails(params?: {
  start_date?: string;
  end_date?: string;
  campaign_id?: string;
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
    queryKey: ["token-usage", "details", params],
    queryFn: () =>
      apiGet<{
        items: RawTokenUsageDetail[];
        total: number;
        limit: number;
        offset: number;
        by_model?: Array<Record<string, unknown>>;
        by_campaign?: Array<Record<string, unknown>>;
      }>(`/api/token-usage/details?${searchParams.toString()}`),
    select: (raw) => ({
      ...raw,
      items: raw.items.map(normalizeDetail),
    }),
  });
}
