import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiPost, apiPatch, apiDelete } from "./client";
import { toast } from "sonner";

// Backend returns pagination object with items/limit/offset/total
interface PaginatedResponse<T> {
  items: T[];
  limit: number;
  offset: number;
  total: number;
}

// Raw types from backend
interface RawMember {
  id: string;
  email: string;
  display_name?: string;
  role: string;
  status: string;
  joined_at: string;
  last_active_at?: string;
}

interface RawInvitation {
  id: string;
  email: string;
  role: string;
  invited_by: string;
  invited_at: string;
  expires_at: string;
  status: string;
}

// Normalized types for frontend
export interface Member {
  id: string;
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

function normalizeMember(raw: RawMember): Member {
  return {
    id: raw.id,
    email: raw.email,
    display_name: raw.display_name || raw.email,
    role: (raw.role as Member["role"]) || "viewer",
    status: (raw.status === "active" ? "active" : "inactive") as Member["status"],
    joined_at: raw.joined_at,
    last_active_at: raw.last_active_at,
  };
}

function normalizeInvitation(raw: RawInvitation): Invitation {
  return {
    id: raw.id,
    email: raw.email,
    role: (raw.role as Invitation["role"]) || "member",
    invited_by: raw.invited_by,
    invited_at: raw.invited_at,
    expires_at: raw.expires_at,
    status: (raw.status as Invitation["status"]) || "pending",
  };
}

export function useMembers() {
  return useQuery({
    queryKey: ["members"],
    queryFn: async () => {
      const raw = await apiGet<PaginatedResponse<RawMember>>("/api/tenant/members");
      return {
        ...raw,
        items: raw.items?.map(normalizeMember) || [],
      };
    },
  });
}

export function useInvitations() {
  return useQuery({
    queryKey: ["invitations"],
    queryFn: async () => {
      const raw = await apiGet<PaginatedResponse<RawInvitation>>("/api/tenant/invitations");
      return {
        ...raw,
        items: raw.items?.map(normalizeInvitation) || [],
      };
    },
  });
}

export function useInviteMember() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: { email: string; role: string }) =>
      apiPost<RawInvitation>("/api/tenant/members", data),
    onSuccess: () => {
      toast.success("邀请已发送");
      queryClient.invalidateQueries({ queryKey: ["invitations"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "邀请失败");
    },
  });
}

export function useUpdateMemberRole() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, role }: { id: string; role: string }) =>
      apiPatch<RawMember>(`/api/tenant/members/${id}`, { role }),
    onSuccess: () => {
      toast.success("角色已更新");
      queryClient.invalidateQueries({ queryKey: ["members"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "更新失败");
    },
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
    onError: (error: any) => {
      toast.error(error.message || "移除失败");
    },
  });
}

export function useDeleteInvitation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => apiDelete(`/api/tenant/invitations/${id}`),
    onSuccess: () => {
      toast.success("邀请已取消");
      queryClient.invalidateQueries({ queryKey: ["invitations"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "取消失败");
    },
  });
}

export function useTransferOwnership() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (targetUserId: string) =>
      apiPost("/api/tenant/transfer-ownership", { target_user_id: targetUserId }),
    onSuccess: () => {
      toast.success("所有权已转移");
      queryClient.invalidateQueries({ queryKey: ["members"] });
    },
    onError: (error: any) => {
      toast.error(error.message || "转移失败");
    },
  });
}
