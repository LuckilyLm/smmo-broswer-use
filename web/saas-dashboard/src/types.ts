export type ApiRecord = Record<string, unknown>;

export interface PaginatedResponse<T> {
  items: T[];
  limit: number;
  offset: number;
  total: number;
}

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  status: string;
}

export interface BrowserRuntime {
  id: string;
  status: string;
  runtime_type: string;
  cdp_port?: number;
  browser_pid?: number;
  started_at?: string;
  last_health_check_at?: string;
  last_error?: string;
}

export interface PlatformAccount {
  id: string;
  platform: string;
  display_name: string;
  connection_status: string;
  login_status: string;
  runtime?: BrowserRuntime | null;
}

export interface Campaign {
  id: string;
  name: string;
  platform_account_id: string;
  status: string;
  target_policy: string;
  max_contents: number;
  max_comments: number;
  min_confidence: number;
}

export interface Lead {
  id: string;
  author_name?: string;
  comment_text?: string;
  status: string;
  final_intent_level?: string;
}

export interface Execution {
  id: string;
  campaign_id: string;
  status: string;
  send_disabled: true;
  config_snapshot?: Record<string, unknown>;
}

export interface ExecutionKeyword {
  id: string;
  execution_id: string;
  keyword: string;
  status: string;
  attempt_number: number;
}

export interface TokenUsage {
  id: string;
  model?: string;
  total_tokens?: number;
  estimated_cost?: number | null;
  elapsed_ms?: number | null;
}

export interface RuntimeCapabilities {
  runtime_host: string;
  runtime_available: boolean;
  browser_platform: string;
  local_browser_supported: boolean;
}

export interface Plan {
  id: string;
  code: string;
  name: string;
  allow_scheduler: boolean;
  allow_multi_keyword: boolean;
  allow_advanced_reports: boolean;
}

export interface UsageSummary {
  plan: Plan;
  subscription: ApiRecord;
  usage: Record<string, number>;
  limits: Record<string, number | null>;
  remaining: Record<string, number | null>;
}

export interface TenantMember {
  id: string;
  user_id: string;
  display_name: string;
  email: string;
  role: "owner" | "admin" | "member" | "viewer";
  status: string;
}

export interface Invitation {
  id: string;
  email: string;
  role: string;
  status: string;
  expires_at: string;
  token?: string;
}

export interface AuditLog {
  id: string;
  created_at: string;
  user_id?: string;
  user_display_name?: string;
  action: string;
  resource_type: string;
  resource_id?: string;
}

export interface Notification {
  id: string;
  type: string;
  severity: string;
  title: string;
  message: string;
  read_at?: string;
  created_at: string;
}
