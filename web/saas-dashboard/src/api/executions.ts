import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { apiGet, apiPost } from "./client";

export type ExecutionStatus = "queued" | "running" | "completed" | "partial" | "failed" | "cancelled";

export interface ExecutionKeyword {
  id: string;
  keyword: string;
  status: string;
  attempt_number: number;
  discovered_contents: number;
  scanned_comments: number;
  lead_candidates: number;
  eligible_count: number;
  selected_count: number;
  elapsed_ms?: number | null;
  error_type?: string | null;
  error_message?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface ExecutionArtifact {
  type: string;
  name: string;
  url: string;
  external_url?: string | null;
  created_at?: string | null;
}

export interface ExecutionQueue {
  id: string;
  status: string;
  claimed_by?: string | null;
  attempt_count?: number | null;
  max_attempts?: number | null;
  queued_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  error_type?: string | null;
  error_message?: string | null;
}

export interface Execution {
  id: string;
  tenant_id?: string;
  campaign_id: string;
  campaign_name?: string;
  run_id?: string | null;
  platform?: string;
  status: ExecutionStatus;
  trigger_type?: string;
  stage?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  elapsed_ms?: number | null;
  total_keywords: number;
  completed_keywords: number;
  failed_keywords: number;
  current_keyword?: string | null;
  progress_percent: number;
  scanned_contents: number;
  scanned_comments: number;
  lead_candidates: number;
  eligible_count: number;
  selected_count: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  send_disabled: boolean;
  error_type?: string | null;
  error_message?: string | null;
  config_snapshot?: {
    provenance?: string;
    demo_seed?: boolean;
    keywords?: Array<{ id?: string; keyword: string }>;
    artifacts?: {
      object_storage?: {
        enabled?: boolean;
        uploaded?: number;
        error?: string | null;
        items?: Array<{ name: string; url?: string; key?: string }>;
      };
    };
    [key: string]: unknown;
  };
  created_at: string;
  updated_at?: string;
  queue?: ExecutionQueue | null;
}

export interface PaginatedExecutions {
  items: Execution[];
  total: number;
  limit: number;
  offset: number;
}

export interface PaginatedArtifacts {
  items: ExecutionArtifact[];
  total: number;
  limit: number;
  offset: number;
}

export interface ExecutionLogLine {
  line_number?: number;
  source?: string;
  line: string;
}

export interface PaginatedExecutionLogs {
  items: ExecutionLogLine[];
  total: number;
  limit: number;
  offset: number;
}

export function useExecutions(params?: {
  status?: string;
  campaign_id?: string;
  limit?: number;
  offset?: number;
}) {
  const searchParams = new URLSearchParams();
  searchParams.set("limit", String(params?.limit ?? 50));
  searchParams.set("offset", String(params?.offset ?? 0));
  if (params?.status) searchParams.set("status", params.status);
  if (params?.campaign_id) searchParams.set("campaign_id", params.campaign_id);

  return useQuery({
    queryKey: ["executions", params],
    queryFn: () => apiGet<PaginatedExecutions>(`/api/executions?${searchParams.toString()}`),
    refetchInterval: (query) => {
      const items = query.state.data?.items || [];
      return items.some((item) => item.status === "queued" || item.status === "running") ? 5000 : false;
    },
  });
}

export function useExecution(id: string | null) {
  return useQuery({
    queryKey: ["executions", id],
    queryFn: () => apiGet<Execution>(`/api/executions/${id}`),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 3000 : false;
    },
  });
}

export function useExecutionKeywords(id: string | null, poll = false) {
  return useQuery({
    queryKey: ["executions", id, "keywords"],
    queryFn: () => apiGet<ExecutionKeyword[]>(`/api/executions/${id}/keywords`),
    enabled: !!id,
    refetchInterval: poll ? 3000 : false,
  });
}

export function useExecutionArtifacts(id: string | null, poll = false) {
  return useQuery({
    queryKey: ["executions", id, "artifacts"],
    queryFn: () => apiGet<PaginatedArtifacts>(`/api/executions/${id}/artifacts`),
    enabled: !!id,
    refetchInterval: poll ? 3000 : false,
  });
}

export function useExecutionLogs(id: string | null, limit = 100, poll = false) {
  return useQuery({
    queryKey: ["executions", id, "logs", limit],
    queryFn: () => apiGet<PaginatedExecutionLogs>(`/api/executions/${id}/logs?limit=${limit}&offset=0`),
    enabled: !!id,
    refetchInterval: poll ? 3000 : false,
  });
}

export function useCancelExecution() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiPost<Execution>(`/api/executions/${id}/cancel`, {}),
    onSuccess: () => {
      toast.success("执行已取消");
      queryClient.invalidateQueries({ queryKey: ["executions"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "取消失败");
    },
  });
}
