import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiDelete, apiGet, apiPatch, apiPost } from "./client";

export interface PaginatedResponse<T> {
  items: T[];
  limit: number;
  offset: number;
  total: number;
}

interface RawMember {
  id: string;
  user_id?: string;
  email: string;
  display_name?: string;
  role: string;
  status?: string;
  joined_at?: string;
  created_at?: string;
  last_active_at?: string;
}

interface RawInvitation {
  id: string;
  email: string;
  role: string;
  invited_by?: string;
  invited_by_user_id?: string;
  invited_at?: string;
  created_at?: string;
  expires_at: string;
  status: string;
}

export interface Member {
  id: string;
  user_id?: string;
  email: string;
  display_name: string;
  role: "owner" | "admin" | "member" | "viewer";
  status: "active" | "inactive";
  joined_at: string;
  last_active_at?: string;
}

export interface Invitation {
  id: string;
  email: string;
  role: "admin" | "member" | "viewer";
  invited_by: string;
  invited_at: string;
  expires_at: string;
  status: "pending" | "accepted" | "expired" | "revoked";
}

export function normalizeMember(raw: RawMember): Member {
  return {
    id: raw.id,
    user_id: raw.user_id,
    email: raw.email,
    display_name: raw.display_name || raw.email,
    role: (raw.role as Member["role"]) || "viewer",
    status: raw.status === "active" ? "active" : "inactive",
    joined_at: raw.joined_at || raw.created_at || "",
    last_active_at: raw.last_active_at,
  };
}

export function normalizeInvitation(raw: RawInvitation): Invitation {
  return {
    id: raw.id,
    email: raw.email,
    role: (raw.role as Invitation["role"]) || "member",
    invited_by: raw.invited_by || raw.invited_by_user_id || "",
    invited_at: raw.invited_at || raw.created_at || "",
    expires_at: raw.expires_at,
    status: (raw.status as Invitation["status"]) || "pending",
  };
}

export function useMembers() {
  return useQuery({
    queryKey: ["members"],
    queryFn: async () => {
      const raw = await apiGet<PaginatedResponse<RawMember>>("/api/tenant/members");
      return { ...raw, items: raw.items?.map(normalizeMember) || [] };
    },
  });
}

export function useInvitations() {
  return useQuery({
    queryKey: ["invitations"],
    queryFn: async () => {
      const raw = await apiGet<PaginatedResponse<RawInvitation>>("/api/tenant/invitations");
      return { ...raw, items: raw.items?.map(normalizeInvitation) || [] };
    },
  });
}

/** Creates an invitation. Adding an already-registered user is a separate backend operation. */
export function useInviteMember() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { email: string; role: Invitation["role"] }) =>
      apiPost<RawInvitation>("/api/tenant/invitations", data),
    onSuccess: () => {
      toast.success("邀请已创建");
      queryClient.invalidateQueries({ queryKey: ["invitations"] });
    },
    onError: (error: Error) => toast.error(error.message || "邀请失败"),
  });
}

export function useUpdateMemberRole() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, role }: { id: string; role: Exclude<Member["role"], "owner"> }) =>
      apiPatch<RawMember>(`/api/tenant/members/${id}`, { role }),
    onSuccess: () => {
      toast.success("角色已更新");
      queryClient.invalidateQueries({ queryKey: ["members"] });
    },
    onError: (error: Error) => toast.error(error.message || "更新失败"),
  });
}

export function useRemoveMember() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/api/tenant/members/${id}`),
    onSuccess: () => {
      toast.success("成员已移除");
      queryClient.invalidateQueries({ queryKey: ["members"] });
    },
    onError: (error: Error) => toast.error(error.message || "移除失败"),
  });
}

export function useResendInvitation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiPost<RawInvitation>(`/api/tenant/invitations/${id}/resend`),
    onSuccess: () => {
      toast.success("邀请已重发");
      queryClient.invalidateQueries({ queryKey: ["invitations"] });
    },
    onError: (error: Error) => toast.error(error.message || "重发失败"),
  });
}

export function useDeleteInvitation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/api/tenant/invitations/${id}`),
    onSuccess: () => {
      toast.success("邀请已撤销");
      queryClient.invalidateQueries({ queryKey: ["invitations"] });
    },
    onError: (error: Error) => toast.error(error.message || "撤销失败"),
  });
}

export function useTransferOwnership() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (targetUserId: string) => apiPost("/api/tenant/transfer-ownership", { target_user_id: targetUserId }),
    onSuccess: () => {
      toast.success("所有权已转移");
      queryClient.invalidateQueries({ queryKey: ["members"] });
    },
    onError: (error: Error) => toast.error(error.message || "转移失败"),
  });
}
