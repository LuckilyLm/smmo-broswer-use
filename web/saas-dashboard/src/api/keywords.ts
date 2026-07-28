import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost, apiPatch, apiDelete } from "./client";
import { toast } from "sonner";

export interface Keyword {
  id: string;
  campaign_id: string;
  keyword: string;
  enabled: boolean;
  priority: number;
  created_at: string;
  updated_at: string;
}

export function useKeywords(campaignId: string) {
  return useQuery({
    queryKey: ["keywords", campaignId],
    queryFn: () =>
      apiGet<Keyword[]>(`/api/campaigns/${campaignId}/keywords`),
    enabled: !!campaignId,
  });
}

export function useCreateKeyword() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ campaignId, keyword }: { campaignId: string; keyword: string }) =>
      apiPost<Keyword>(`/api/campaigns/${campaignId}/keywords`, { keyword }),
    onSuccess: (_, variables) => {
      toast.success("关键词添加成功");
      queryClient.invalidateQueries({ queryKey: ["keywords", variables.campaignId] });
    },
    onError: (error: any) => {
      toast.error(error.message || "添加失败");
    },
  });
}

export function useBulkCreateKeywords() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      campaignId,
      keywords,
    }: {
      campaignId: string;
      keywords: string[];
    }) =>
      apiPost<{ items: Keyword[]; created: number }>(
        `/api/campaigns/${campaignId}/keywords/bulk`,
        { keywords }
      ),
    onSuccess: (_, variables) => {
      toast.success("批量添加关键词成功");
      queryClient.invalidateQueries({ queryKey: ["keywords", variables.campaignId] });
    },
    onError: (error: any) => {
      toast.error(error.message || "批量添加失败");
    },
  });
}

export function useUpdateKeyword() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Keyword> }) =>
      apiPatch<Keyword>(`/api/keywords/${id}`, data),
    onSuccess: () => {
      toast.success("关键词更新成功");
      queryClient.invalidateQueries({ queryKey: ["keywords"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "更新失败");
    },
  });
}

export function useDeleteKeyword() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/api/keywords/${id}`),
    onSuccess: () => {
      toast.success("关键词已删除");
      queryClient.invalidateQueries({ queryKey: ["keywords"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "删除失败");
    },
  });
}
