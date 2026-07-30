import { useQuery, useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "./client";
import { toast } from "sonner";

export type ReplyCandidateStatus = "pending_approval" | "approved" | "blocked" | "rejected" | "cancelled" | "sent" | "failed";
export type ReplyPlanStatus = "pending_approval" | "approved" | "blocked" | "executed" | "cancelled";

export interface ReplyCandidate {
  id: string;
  campaign_id: string;
  execution_id?: string | null;
  reply_plan_id?: string | null;
  platform_account_id?: string;
  platform: string;
  author_name?: string | null;
  comment_text?: string | null;
  matched_rule_id?: string | null;
  matched_rule_name?: string | null;
  reply_template_id?: string | null;
  rendered_reply_text?: string | null;
  source_content_url?: string | null;
  direct_comment_url?: string | null;
  status: ReplyCandidateStatus;
  blocked_reason?: string | null;
  last_error?: string | null;
  provenance?: string;
  created_at: string;
}

export interface ReplyPlan {
  id: string;
  campaign_id: string;
  execution_id?: string | null;
  platform_account_id?: string;
  status: ReplyPlanStatus;
  reply_mode?: string;
  total_candidates: number;
  approved_count: number;
  sent_count: number;
  failed_count: number;
  blocked_reason?: string | null;
  executed_at?: string | null;
  provenance?: string;
  created_at: string;
}

export function canApproveReplyPlan(plan: Pick<ReplyPlan, "status" | "total_candidates">) {
  return plan.status === "pending_approval" && plan.total_candidates > 0;
}

export function invalidateReplyLifecycleQueries(queryClient: QueryClient) {
  for (const queryKey of [
    ["reply-plans"],
    ["reply-candidates"],
    ["reply-records"],
    ["reply-record"],
    ["executions"],
    ["dashboard"],
  ]) {
    queryClient.invalidateQueries({ queryKey });
  }
}

export function useReplyCandidates(status?: ReplyCandidateStatus) {
  const params = new URLSearchParams();
  if (status) params.append("status", status);

  return useQuery({
    queryKey: ["reply-candidates", status],
    queryFn: () =>
      apiGet<{
        items: ReplyCandidate[];
        total: number;
      }>(`/api/reply-candidates?${params.toString()}`),
  });
}

export function useReplyPlans(status?: ReplyPlanStatus) {
  const params = new URLSearchParams();
  if (status) params.append("status", status);

  return useQuery({
    queryKey: ["reply-plans", status],
    queryFn: () =>
      apiGet<{
        items: ReplyPlan[];
        total: number;
      }>(`/api/reply-plans?${params.toString()}`),
  });
}

export function useApproveCandidate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiPost<ReplyCandidate>(`/api/reply-candidates/${id}/approve`, {}),
    onSuccess: () => {
      toast.success("已批准");
      invalidateReplyLifecycleQueries(queryClient);
    },
    onError: (error: any) => {
      toast.error(error.message || "操作失败");
    },
  });
}

export function useRejectCandidate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      apiPost<ReplyCandidate>(`/api/reply-candidates/${id}/reject`, { reason }),
    onSuccess: () => {
      toast.success("已拒绝");
      invalidateReplyLifecycleQueries(queryClient);
    },
    onError: (error: any) => {
      toast.error(error.message || "操作失败");
    },
  });
}

export function useCancelCandidate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiPost<ReplyCandidate>(`/api/reply-candidates/${id}/cancel`, {}),
    onSuccess: () => {
      toast.success("已取消");
      invalidateReplyLifecycleQueries(queryClient);
    },
    onError: (error: any) => {
      toast.error(error.message || "操作失败");
    },
  });
}

export function useBulkApproveCandidates() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) =>
      apiPost("/api/reply-candidates/bulk-approve", { candidate_ids: ids }),
    onSuccess: () => {
      toast.success("批量批准成功");
      invalidateReplyLifecycleQueries(queryClient);
    },
    onError: (error: any) => {
      toast.error(error.message || "批量操作失败");
    },
  });
}

export function useBulkRejectCandidates() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ ids, reason }: { ids: string[]; reason: string }) =>
      apiPost("/api/reply-candidates/bulk-reject", { candidate_ids: ids, reason }),
    onSuccess: () => {
      toast.success("批量拒绝成功");
      invalidateReplyLifecycleQueries(queryClient);
    },
    onError: (error: any) => {
      toast.error(error.message || "批量操作失败");
    },
  });
}

export function useApprovePlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiPost<ReplyPlan>(`/api/reply-plans/${id}/approve`, {}),
    onSuccess: () => {
      toast.success("计划已批准");
      invalidateReplyLifecycleQueries(queryClient);
    },
    onError: (error: any) => {
      toast.error(error.message || "操作失败");
    },
  });
}

export function useCancelPlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiPost<ReplyPlan>(`/api/reply-plans/${id}/cancel`, {}),
    onSuccess: () => {
      toast.success("计划已取消");
      invalidateReplyLifecycleQueries(queryClient);
    },
    onError: (error: any) => {
      toast.error(error.message || "操作失败");
    },
  });
}

export function useExecutePlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiPost<ReplyPlan>(`/api/reply-plans/${id}/execute`, {}),
    onSuccess: () => {
      toast.success("计划开始执行");
      invalidateReplyLifecycleQueries(queryClient);
    },
    onError: (error: any) => {
      toast.error(error.message || "执行失败");
    },
  });
}
