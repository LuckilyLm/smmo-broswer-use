import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./client";

export interface ReplyRecord {
  id: string;
  reply_candidate_id?: string | null;
  reply_plan_id?: string | null;
  campaign_id: string;
  platform_account_id?: string;
  comment_id?: string | null;
  reply_text: string;
  status: "sent" | "failed" | "pending" | "blocked" | "verified" | "cancelled";
  verified?: boolean;
  error_type?: string | null;
  error_message?: string | null;
  execution_id?: string | null;
  provenance?: string;
  created_at: string;
  updated_at?: string;
}

export interface ReplyRecordDetail {
  record: ReplyRecord;
  candidate?: {
    id: string;
    author_name?: string | null;
    comment_text?: string | null;
    rendered_reply_text?: string | null;
  } | null;
  campaign?: {
    id: string;
    name: string;
    platform?: string;
  } | null;
  account?: {
    id: string;
    display_name?: string | null;
    platform?: string;
  } | null;
  original_comment?: {
    comment_id?: string | null;
    text?: string | null;
  };
}

export function useReplyRecords(params?: {
  campaign_id?: string;
  platform_account_id?: string;
  status?: string;
  verified?: boolean;
  error_type?: string;
  author_name?: string;
  keyword?: string;
  created_from?: string;
  created_to?: string;
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
    queryKey: ["reply-records", params],
    queryFn: () =>
      apiGet<{
        items: ReplyRecord[];
        total: number;
        limit: number;
        offset: number;
      }>(`/api/reply-records?${searchParams.toString()}`),
  });
}

export function useReplyRecord(recordId?: string | null) {
  return useQuery({
    queryKey: ["reply-record", recordId],
    enabled: Boolean(recordId),
    queryFn: () => apiGet<ReplyRecordDetail>(`/api/reply-records/${recordId}`),
  });
}
