import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost } from "./client";
import { toast } from "sonner";

export interface Notification {
  id: string;
  type: string;
  severity?: "info" | "warning" | "error" | "success";
  title: string;
  message: string;
  read: boolean;
  action_url?: string;
  action_label?: string;
  created_at: string;
}

export function useNotifications(unreadOnly = false, limit = 50) {
  return useQuery({
    queryKey: ["notifications", { unreadOnly, limit }],
    queryFn: () =>
      apiGet<{
        items: Notification[];
        total: number;
        unread_count: number;
      }>(`/api/notifications?unread_only=${unreadOnly}&limit=${limit}`),
  });
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      apiPost<Notification>(`/api/notifications/${id}/read`, {}),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "操作失败");
    },
  });
}

export function useMarkAllNotificationsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => apiPost("/api/notifications/read-all", {}),
    onSuccess: () => {
      toast.success("全部已标记为已读");
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "操作失败");
    },
  });
}
