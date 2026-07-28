import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost, apiPatch, apiDelete } from "./client";
import { toast } from "sonner";

// Raw types from backend
interface RawReplyTemplate {
  id: string;
  name: string;
  content: string;
  description?: string;
  platform: string;
  language: string;
  enabled: boolean;
  priority: number;
  is_default: boolean;
  archived_at?: string;
  created_at: string;
  updated_at: string;
}

// Normalized types for frontend
export interface ReplyTemplate {
  id: string;
  name: string;
  content: string;
  variables: string[];
  status: "active" | "draft" | "archived";
  usage_count: number;
  created_at: string;
  updated_at: string;
}

function normalizeTemplate(raw: RawReplyTemplate): ReplyTemplate {
  // Extract variables from content using {{variable}} pattern
  const varMatches = raw.content.match(/\{\{(\w+)\}\}/g) || [];
  const variables = varMatches.map((v: string) => v.slice(2, -2));

  let status: "active" | "draft" | "archived" = "draft";
  if (raw.archived_at) {
    status = "archived";
  } else if (raw.enabled) {
    status = "active";
  }

  return {
    id: raw.id,
    name: raw.name,
    content: raw.content,
    variables,
    status,
    usage_count: raw.is_default ? 1 : 0, // Backend doesn't track usage yet
    created_at: raw.created_at,
    updated_at: raw.updated_at,
  };
}

export function useReplyTemplates() {
  return useQuery({
    queryKey: ["reply-templates"],
    queryFn: async () => {
      const raw = await apiGet<RawReplyTemplate[]>("/api/reply-templates");
      return raw.map(normalizeTemplate);
    },
  });
}

export function useCreateReplyTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { name: string; content: string; platform?: string; language?: string }) =>
      apiPost<RawReplyTemplate>("/api/reply-templates", {
        ...data,
        enabled: true,
        priority: 100,
      }),
    onSuccess: () => {
      toast.success("模板创建成功");
      queryClient.invalidateQueries({ queryKey: ["reply-templates"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "创建失败");
    },
  });
}

export function useUpdateReplyTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<ReplyTemplate> }) => {
      // Map frontend fields to backend
      const backendData: any = {};
      if (data.name !== undefined) backendData.name = data.name;
      if (data.content !== undefined) backendData.content = data.content;
      if (data.status !== undefined) {
        backendData.enabled = data.status === "active";
        if (data.status === "archived") {
          backendData.archived_at = new Date().toISOString();
        }
      }
      return apiPatch<RawReplyTemplate>(`/api/reply-templates/${id}`, backendData);
    },
    onSuccess: () => {
      toast.success("模板更新成功");
      queryClient.invalidateQueries({ queryKey: ["reply-templates"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "更新失败");
    },
  });
}

export function useDeleteReplyTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/api/reply-templates/${id}`),
    onSuccess: () => {
      toast.success("模板已删除");
      queryClient.invalidateQueries({ queryKey: ["reply-templates"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "删除失败");
    },
  });
}
