import {
  ApartmentOutlined,
  BarChartOutlined,
  CommentOutlined,
  ControlOutlined,
  DeleteOutlined,
  DollarOutlined,
  EditOutlined,
  EyeOutlined,
  KeyOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  SettingOutlined,
  ThunderboltOutlined,
  UserOutlined
} from "@ant-design/icons";
import { PageContainer, ProCard, ProTable } from "@ant-design/pro-components";
import {
  Alert,
  Button,
  Card,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  Layout,
  Menu,
  Modal,
  Select,
  Space,
  Spin,
  Statistic,
  Steps,
  Switch,
  Progress,
  Tabs,
  Table,
  Tag,
  Typography,
  message
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useEffect, useMemo, useState } from "react";
import { apiDelete, apiGet, apiPatch, apiPost, apiPut, ApiRecord } from "./api";

const { Header, Sider, Content } = Layout;
const routeItems = [
  { key: "/dashboard", icon: <BarChartOutlined />, label: "Dashboard" },
  { key: "/platform-accounts", icon: <ApartmentOutlined />, label: "Platforms" },
  { key: "/campaigns", icon: <ThunderboltOutlined />, label: "Campaigns" },
  { key: "/keywords", icon: <SearchOutlined />, label: "Keywords" },
  { key: "/leads", icon: <CommentOutlined />, label: "Lead Inbox" },
  { key: "/reply-rules", icon: <ControlOutlined />, label: "Reply Rules" },
  { key: "/executions", icon: <PlayCircleOutlined />, label: "Executions" },
  { key: "/token-usage", icon: <DollarOutlined />, label: "Token Usage" },
  { key: "/settings", icon: <SettingOutlined />, label: "Settings" }
];
const campaignSteps = ["Account", "Configuration", "Keywords", "Policy", "Confirm"];
const statusColors: Record<string, string> = { active: "green", completed: "green", connected: "green", logged_in: "green", queued: "blue", retry_waiting: "gold", running: "blue", login_required: "gold", logged_out: "gold", checkpoint: "orange", captcha: "red", error: "red", unhealthy: "red", stopped: "default", high: "red", medium: "gold", low: "blue", failed: "red", paused: "orange", partial: "gold", cancelled: "default" };

export default function App() {
  const [authState, setAuthState] = useState<"checking" | "authenticated" | "anonymous">("checking");
  const [path, setPath] = useState(() => (window.location.pathname === "/" ? "/dashboard" : window.location.pathname));
  const [me, setMe] = useState<ApiRecord | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiGet<ApiRecord>("/api/auth/me")
      .then((value) => {
        if (!cancelled) {
          setMe(value);
          setAuthState("authenticated");
        }
      })
      .catch(() => {
        if (!cancelled) setAuthState("anonymous");
      });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    const expired = () => { setMe(null); setAuthState("anonymous"); window.history.replaceState({}, "", "/login"); };
    window.addEventListener("saas:session-expired", expired);
    return () => window.removeEventListener("saas:session-expired", expired);
  }, []);

  const navigate = (next: string) => {
    window.history.pushState({}, "", next);
    setPath(next);
  };

  if (authState === "checking") {
    return <div className="login-page"><Spin size="large" /></div>;
  }

  if (authState === "anonymous" || path === "/login") {
    return <LoginPage onLogin={async () => {
      setMe(await apiGet<ApiRecord>("/api/auth/me"));
      setAuthState("authenticated");
      navigate("/dashboard");
    }} />;
  }

  return (
    <Layout className="app-shell">
      <Sider width={228} className="side" breakpoint="lg" collapsedWidth={0}>
        <div className="logo">LeadFlow Console</div>
        <Menu theme="dark" mode="inline" selectedKeys={[path]} items={routeItems} onClick={(item) => navigate(item.key)} />
      </Sider>
      <Layout>
        <Header className="topbar">
          <span className="brand">{me?.tenant?.name || "Tenant Workspace"}</span>
          <Space>
            <Tag color="green">Manual approval</Tag>
            <UserOutlined />
            <span>{me?.user?.display_name || "User"}</span>
          </Space>
        </Header>
        <Content className="content">{renderRoute(path)}</Content>
      </Layout>
    </Layout>
  );
}

function LoginPage({ onLogin }: { onLogin: () => Promise<void> }) {
  const [loading, setLoading] = useState(false);
  return (
    <div className="login-page">
      <Card className="login-panel">
        <Space direction="vertical" size={20} style={{ width: "100%" }}>
          <div>
            <div className="brand">LeadFlow Console</div>
            <Typography.Text className="muted">Sign in to your tenant workspace.</Typography.Text>
          </div>
          <Form layout="vertical" onFinish={async (values) => {
            setLoading(true);
            try {
              await apiPost<ApiRecord>("/api/auth/login", values);
              await onLogin();
            } catch {
              message.error("Sign in failed");
            } finally {
              setLoading(false);
            }
          }}>
            <Form.Item name="email" label="Email" rules={[{ required: true }]}>
              <Input autoComplete="email" />
            </Form.Item>
            <Form.Item name="password" label="Password" rules={[{ required: true }]}>
              <Input.Password autoComplete="current-password" />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block icon={<KeyOutlined />}>Sign in</Button>
          </Form>
        </Space>
      </Card>
    </div>
  );
}

function renderRoute(path: string) {
  if (path === "/dashboard") return <Dashboard />;
  if (path === "/platform-accounts") return <Platforms />;
  if (path === "/campaigns") return <Campaigns />;
  if (path === "/keywords") return <Keywords />;
  if (path === "/leads") return <Leads />;
  if (path === "/reply-rules") return <ReplyRules />;
  if (path === "/executions") return <Executions />;
  if (path === "/token-usage") return <TokenUsage />;
  if (path === "/settings") return <Settings />;
  return <Dashboard />;
}

function Dashboard() {
  const { data, loading, error, refresh } = useResource<ApiRecord>("/api/dashboard/summary", {});
  const { data: worker } = useResource<ApiRecord>("/api/system/worker-status", {});
  const { data: scheduler } = useResource<ApiRecord>("/api/system/scheduler-status", {});
  return (
    <Page title="Dashboard" action={<Button icon={<ReloadOutlined />} onClick={refresh}>Refresh</Button>}>
      <ResourceState loading={loading} error={error} empty={false}>
        <div className="grid">
          <Card><Statistic title="Active campaigns" value={data.active_campaigns || 0} /></Card>
          <Card><Statistic title="Leads today" value={data.leads_today || 0} /></Card>
          <Card><Statistic title="High intent" value={data.high_intent_leads || 0} /></Card>
          <Card><Statistic title="Tokens this month" value={data.tokens_this_month || 0} /></Card>
          <Card><Statistic title="Queued tasks" value={data.queued_tasks || 0} /></Card>
          <Card><Statistic title="Running tasks" value={data.running_tasks || 0} /></Card>
          <Card><Statistic title="Auto tasks today" value={data.auto_tasks_today || 0} /></Card>
          <Card><Statistic title="Failed tasks" value={data.failed_tasks || 0} /></Card>
          <Card><Statistic title="Worker" value={worker.online ? "Online" : "Offline"} /></Card>
          <Card><Statistic title="Scheduler" value={scheduler.online ? "Online" : "Offline"} /></Card>
        </div>
        <div className="wide-grid">
          <ProCard title="Recent executions"><DataList rows={data.recent_executions || []} fields={["run_id", "status", "selected_count"]} /></ProCard>
          <ProCard title="Latest leads"><DataList rows={data.latest_leads || []} fields={["author_name", "rule_intent_level", "status"]} /></ProCard>
        </div>
      </ResourceState>
    </Page>
  );
}

function Platforms() {
  const { data: rows, loading, error, refresh } = useResource<ApiRecord[]>("/api/platform-accounts", []);
  const [selectedRuntime, setSelectedRuntime] = useState<ApiRecord | null>(null);
  const [busyId, setBusyId] = useState("");
  const runAction = async (account: ApiRecord, action: string, body?: ApiRecord) => {
    setBusyId(`${account.id}:${action}`);
    try {
      const result = await apiPost<ApiRecord>(`/api/platform-accounts/${account.id}/${action}`, body);
      if (action === "connect") {
        Modal.info({
          title: "Complete sign in",
          content: "A dedicated browser window was opened. Complete Facebook sign in there, then return here and check the login status."
        });
      }
      if (result.runtime) setSelectedRuntime(result.runtime);
      message.success("Action completed");
      refresh();
    } catch {
      message.error("Action failed");
    } finally {
      setBusyId("");
    }
  };
  return (
    <Page title="Platform Accounts" action={<Button type="primary" icon={<PlusOutlined />}>Connect</Button>}>
      <ResourceState loading={loading} error={error} empty={rows.length === 0}>
        <Table rowKey="id" dataSource={rows} columns={[
          { title: "Platform", dataIndex: "platform" },
          { title: "Name", dataIndex: "display_name" },
          { title: "Connection", dataIndex: "connection_status", render: (value) => <StatusTag value={value} /> },
          { title: "Login", dataIndex: "login_status", render: (value) => <StatusTag value={value} /> },
          { title: "Runtime", render: (_, row) => <StatusTag value={row.runtime?.status || "stopped"} /> },
          { title: "Last check", dataIndex: "last_login_check_at" },
          { title: "Last error", dataIndex: "last_connection_error", ellipsis: true },
          {
            title: "Actions",
            render: (_, row) => (
              <Space wrap>
                <Button loading={busyId === `${row.id}:connect`} onClick={() => runAction(row, "connect")}>Connect</Button>
                <Button loading={busyId === `${row.id}:check-login`} onClick={() => runAction(row, "check-login")}>Check Login</Button>
                <Button loading={busyId === `${row.id}:reconnect`} onClick={() => runAction(row, "reconnect")}>Reconnect</Button>
                <Button loading={busyId === `${row.id}:stop-runtime`} onClick={() => runAction(row, "stop-runtime")}>Stop</Button>
                <Button loading={busyId === `${row.id}:restart-runtime`} onClick={() => runAction(row, "restart-runtime")}>Restart</Button>
                <Button icon={<EyeOutlined />} onClick={() => apiGet<ApiRecord>(`/api/platform-accounts/${row.id}/runtime`).then(setSelectedRuntime)}>Runtime</Button>
                <Button danger onClick={() => runAction(row, "reset-profile", { confirm: "RESET PROFILE" })}>Reset</Button>
              </Space>
            )
          }
        ]} />
      </ResourceState>
      <RuntimeDrawer runtime={selectedRuntime} onClose={() => setSelectedRuntime(null)} />
    </Page>
  );
}

function RuntimeDrawer({ runtime, onClose }: { runtime: ApiRecord | null; onClose: () => void }) {
  return (
    <Drawer open={Boolean(runtime)} width={520} title="Runtime details" onClose={onClose}>
      {runtime && <Descriptions column={1} bordered size="small" items={[
        { key: "status", label: "Runtime status", children: <StatusTag value={runtime.status} /> },
        { key: "type", label: "Runtime type", children: runtime.runtime_type || "-" },
        { key: "port", label: "Debug port", children: runtime.cdp_port || "-" },
        { key: "pid", label: "Process ID", children: runtime.browser_pid || "-" },
        { key: "started", label: "Started at", children: runtime.started_at || "-" },
        { key: "checked", label: "Last health check", children: runtime.last_health_check_at || "-" },
        { key: "error", label: "Last error", children: runtime.last_error || "-" }
      ]} />}
    </Drawer>
  );
}

function Campaigns() {
  const { data: rows, loading, error, refresh } = useResource<ApiRecord[]>("/api/campaigns", []);
  const { data: accounts } = useResource<ApiRecord[]>("/api/platform-accounts", []);
  const [editing, setEditing] = useState<ApiRecord | null>(null);
  const [scheduleCampaign, setScheduleCampaign] = useState<ApiRecord | null>(null);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [runningIds, setRunningIds] = useState<Set<string>>(new Set());

  const runCampaign = async (campaign: ApiRecord) => {
    setRunningIds((ids) => new Set(ids).add(campaign.id));
    try {
      await apiPost(`/api/campaigns/${campaign.id}/run`);
      message.success("Run queued");
      await pollExecutions();
      refresh();
    } catch {
      message.error("Run failed");
    } finally {
      setRunningIds((ids) => {
        const next = new Set(ids);
        next.delete(campaign.id);
        return next;
      });
    }
  };

  return (
    <Page title="Campaigns" action={<Button type="primary" icon={<PlusOutlined />} onClick={() => setWizardOpen(true)}>New Campaign</Button>}>
      <ResourceState loading={loading} error={error} empty={rows.length === 0}>
        <ProTable search={false} rowKey="id" dataSource={rows} columns={[
          { title: "Name", dataIndex: "name" },
          { title: "Status", dataIndex: "status", render: (value) => <StatusTag value={value} /> },
          { title: "Policy", dataIndex: "target_policy" },
          { title: "Comments", dataIndex: "max_comments" },
          { title: "Confidence", dataIndex: "min_confidence" },
          { title: "Schedule", render: (_, row) => <ScheduleLabel schedule={row.schedule} /> },
          {
            title: "Actions",
            render: (_, row) => (
              <Space wrap>
                <Button icon={<PlayCircleOutlined />} loading={runningIds.has(row.id)} onClick={() => runCampaign(row)}>Run once</Button>
                <Button icon={<EditOutlined />} onClick={() => setEditing(row)}>Edit</Button>
                <Button icon={<SettingOutlined />} onClick={() => setScheduleCampaign(row)}>Schedule</Button>
                <Button icon={row.status === "active" ? <PauseCircleOutlined /> : <ThunderboltOutlined />} onClick={() => updateCampaign(row.id, { status: row.status === "active" ? "paused" : "active" }, refresh)}>
                  {row.status === "active" ? "Pause" : "Enable"}
                </Button>
                <Button danger icon={<DeleteOutlined />} onClick={() => deleteCampaign(row.id, refresh)}>Delete</Button>
              </Space>
            )
          }
        ]} />
      </ResourceState>
      <CampaignWizard open={wizardOpen} accounts={accounts} onClose={() => setWizardOpen(false)} onSaved={refresh} />
      <CampaignEditor campaign={editing} onClose={() => setEditing(null)} onSaved={refresh} />
      <ScheduleDrawer campaign={scheduleCampaign} onClose={() => setScheduleCampaign(null)} onSaved={refresh} />
    </Page>
  );
}

function ScheduleLabel({ schedule }: { schedule?: ApiRecord | null }) {
  if (!schedule || !schedule.enabled || schedule.schedule_type === "manual") return <Tag>Manual only</Tag>;
  if (schedule.schedule_type === "interval") return <Tag color="blue">Every {Math.round(Number(schedule.interval_minutes || 0) / 60)} hours</Tag>;
  if (schedule.schedule_type === "daily") return <Tag color="green">Daily {schedule.daily_time || "09:00"}</Tag>;
  return <Tag>{schedule.schedule_type}</Tag>;
}

function ScheduleDrawer({ campaign, onClose, onSaved }: { campaign: ApiRecord | null; onClose: () => void; onSaved: () => void }) {
  const [form] = Form.useForm();
  const { data: schedule, refresh } = useResource<ApiRecord>(campaign ? `/api/campaigns/${campaign.id}/schedule` : "", {});
  useEffect(() => {
    if (campaign) {
      form.setFieldsValue({ schedule_type: "manual", enabled: false, interval_minutes: 360, daily_time: "09:00", timezone: "Asia/Shanghai", ...schedule });
    }
  }, [campaign, schedule, form]);
  return (
    <Drawer open={Boolean(campaign)} width={520} title="Campaign schedule" onClose={onClose}>
      {campaign && <Form form={form} layout="vertical" onFinish={async (values) => {
        await apiPut(`/api/campaigns/${campaign.id}/schedule`, values);
        message.success("Schedule saved");
        refresh();
        onSaved();
      }}>
        <Form.Item name="schedule_type" label="Run plan">
          <Select options={[{ value: "manual", label: "Manual only" }, { value: "interval", label: "Every N hours" }, { value: "daily", label: "Daily fixed time" }]} />
        </Form.Item>
        <Form.Item name="enabled" label="Enabled" valuePropName="checked"><Switch /></Form.Item>
        <Form.Item noStyle shouldUpdate>
          {() => form.getFieldValue("schedule_type") === "interval" && <Form.Item name="interval_minutes" label="Interval"><Select options={[{ value: 180, label: "Every 3 hours" }, { value: 360, label: "Every 6 hours" }, { value: 720, label: "Every 12 hours" }]} /></Form.Item>}
        </Form.Item>
        <Form.Item noStyle shouldUpdate>
          {() => form.getFieldValue("schedule_type") === "daily" && <Form.Item name="daily_time" label="Daily time"><Input placeholder="09:00" /></Form.Item>}
        </Form.Item>
        <Form.Item name="timezone" label="Timezone"><Select options={[{ value: "Asia/Shanghai" }, { value: "Asia/Singapore" }, { value: "UTC" }]} /></Form.Item>
        <Descriptions column={1} size="small" bordered items={[
          { key: "next", label: "Next run", children: schedule.next_run_at || "-" },
          { key: "last", label: "Last run", children: schedule.last_run_at || "-" }
        ]} />
        <Space style={{ marginTop: 16 }}>
          <Button type="primary" htmlType="submit">Save</Button>
          <Button onClick={async () => { await apiPost(`/api/campaigns/${campaign.id}/schedule/disable`); message.success("Schedule disabled"); refresh(); onSaved(); }}>Disable</Button>
        </Space>
      </Form>}
    </Drawer>
  );
}

function CampaignWizard({ open, accounts, onClose, onSaved }: { open: boolean; accounts: ApiRecord[]; onClose: () => void; onSaved: () => void }) {
  const [step, setStep] = useState(0);
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);

  const save = async () => {
    const values = await form.validateFields();
    setSaving(true);
    try {
      const campaign = await apiPost<ApiRecord>("/api/campaigns", {
        name: values.name,
        platform_account_id: values.platform_account_id,
        status: "active",
        target_policy: values.target_policy,
        max_contents: values.max_contents,
        max_comments: values.max_comments,
        min_confidence: values.min_confidence,
        max_leads: values.max_leads,
        daily_limit: values.daily_limit,
        llm_enabled: values.llm_enabled
      });
      const keywords = String(values.keywords || "").split("\n").map((item) => item.trim()).filter(Boolean);
      await Promise.all(keywords.map((keyword) => apiPost(`/api/campaigns/${campaign.id}/keywords`, { keyword, enabled: true, priority: 100 })));
      if (values.reply_template) {
        await apiPost("/api/reply-rules", {
          campaign_id: campaign.id,
          name: "Default price response",
          intent_type: "price_query",
          min_confidence: values.min_confidence,
          reply_template: values.reply_template,
          language: "en",
          approval_mode: "manual"
        });
      }
      message.success("Campaign created");
      onSaved();
      onClose();
      form.resetFields();
      setStep(0);
    } catch {
      message.error("Could not create campaign");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} width={760} title="Create campaign" onCancel={onClose} onOk={step === campaignSteps.length - 1 ? save : () => setStep(step + 1)} confirmLoading={saving} okText={step === campaignSteps.length - 1 ? "Create" : "Next"}>
      <Steps current={step} size="small" items={campaignSteps.map((title) => ({ title }))} />
      <Form form={form} layout="vertical" className="wizard-form" initialValues={{ max_contents: 5, max_comments: 80, min_confidence: 0.9, max_leads: 5, daily_limit: 10, target_policy: "discovery_only", llm_enabled: true, keywords: "massage chair" }}>
        {step === 0 && <Form.Item name="platform_account_id" label="Platform account" rules={[{ required: true }]}><Select options={accounts.map((account) => ({ value: account.id, label: `${account.platform} - ${account.display_name}` }))} /></Form.Item>}
        {step === 1 && <>
          <Form.Item name="name" label="Campaign name" rules={[{ required: true }]}><Input /></Form.Item>
          <Space wrap>
            <Form.Item name="max_contents" label="Contents"><InputNumber min={1} max={20} /></Form.Item>
            <Form.Item name="max_comments" label="Comments"><InputNumber min={1} max={300} /></Form.Item>
            <Form.Item name="min_confidence" label="Confidence"><InputNumber min={0.1} max={1} step={0.05} /></Form.Item>
            <Form.Item name="max_leads" label="Lead cap"><InputNumber min={1} max={50} /></Form.Item>
            <Form.Item name="daily_limit" label="Daily limit"><InputNumber min={1} max={100} /></Form.Item>
          </Space>
        </>}
        {step === 2 && <Form.Item name="keywords" label="Keywords" rules={[{ required: true }]}><Input.TextArea rows={5} /></Form.Item>}
        {step === 3 && <>
          <Form.Item name="target_policy" label="Target policy"><Select options={[{ value: "discovery_only", label: "Discovery only" }, { value: "owned_only", label: "Owned sources" }, { value: "allowlist", label: "Allowlist" }]} /></Form.Item>
          <Form.Item name="llm_enabled" label="AI review" valuePropName="checked"><Switch /></Form.Item>
        </>}
        {step === 4 && <Form.Item name="reply_template" label="Reply strategy"><Input.TextArea rows={4} placeholder="Thanks for your interest. Our team can share current details." /></Form.Item>}
      </Form>
    </Modal>
  );
}

function CampaignEditor({ campaign, onClose, onSaved }: { campaign: ApiRecord | null; onClose: () => void; onSaved: () => void }) {
  const [form] = Form.useForm();
  useEffect(() => { if (campaign) form.setFieldsValue(campaign); }, [campaign, form]);
  return (
    <Modal open={Boolean(campaign)} title="Edit campaign" onCancel={onClose} onOk={async () => {
      const values = await form.validateFields();
      await updateCampaign(campaign!.id, values, onSaved);
      onClose();
    }}>
      <Form form={form} layout="vertical">
        <Form.Item name="name" label="Name"><Input /></Form.Item>
        <Form.Item name="status" label="Status"><Select options={[{ value: "active" }, { value: "paused" }, { value: "draft" }]} /></Form.Item>
        <Form.Item name="target_policy" label="Policy"><Select options={[{ value: "discovery_only" }, { value: "owned_only" }, { value: "allowlist" }]} /></Form.Item>
      </Form>
    </Modal>
  );
}

function Keywords() {
  const { data: campaigns } = useResource<ApiRecord[]>("/api/campaigns", []);
  const [campaignId, setCampaignId] = useState<string>("");
  const [keyword, setKeyword] = useState("");
  const { data: rows, loading, error, refresh } = useResource<ApiRecord[]>(campaignId ? `/api/campaigns/${campaignId}/keywords` : "", []);
  useEffect(() => { if (!campaignId && campaigns[0]) setCampaignId(campaigns[0].id); }, [campaigns, campaignId]);
  return (
    <Page title="Keywords" action={<Space><Select value={campaignId} style={{ width: 260 }} onChange={setCampaignId} options={campaigns.map((item) => ({ value: item.id, label: item.name }))} /><Input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="Keyword" /><Button icon={<PlusOutlined />} onClick={async () => { await apiPost(`/api/campaigns/${campaignId}/keywords`, { keyword }); setKeyword(""); refresh(); }}>Add</Button></Space>}>
      <ResourceState loading={loading} error={error} empty={rows.length === 0}>
        <Table rowKey="id" dataSource={rows} columns={[
          { title: "Keyword", dataIndex: "keyword" },
          { title: "Enabled", dataIndex: "enabled", render: (value, row) => <Switch checked={Boolean(value)} onChange={(checked) => apiPatch(`/api/keywords/${row.id}`, { enabled: checked }).then(refresh)} /> },
          { title: "Priority", dataIndex: "priority" },
          { title: "Action", render: (_, row) => <Button danger icon={<DeleteOutlined />} onClick={() => apiDelete(`/api/keywords/${row.id}`).then(refresh)}>Delete</Button> }
        ]} />
      </ResourceState>
    </Page>
  );
}

function Leads() {
  const [filters, setFilters] = useState({ status: "", rule_intent_level: "" });
  const [selected, setSelected] = useState<ApiRecord | null>(null);
  const queryEntries = Object.entries(filters).reduce<string[][]>((items, [key, value]) => {
    if (value) items.push([key, value]);
    return items;
  }, []);
  const query = new URLSearchParams(queryEntries).toString();
  const { data, loading, error, refresh } = useResource<ApiRecord>(`/api/leads?limit=25${query ? `&${query}` : ""}`, { items: [] });
  return (
    <Page title="Lead Inbox" action={<Space><Select allowClear placeholder="Status" style={{ width: 140 }} onChange={(value) => setFilters((next) => ({ ...next, status: value || "" }))} options={[{ value: "new" }, { value: "blocked" }]} /><Select allowClear placeholder="Intent" style={{ width: 140 }} onChange={(value) => setFilters((next) => ({ ...next, rule_intent_level: value || "" }))} options={[{ value: "high" }, { value: "medium" }, { value: "low" }]} /><Button icon={<ReloadOutlined />} onClick={refresh}>Refresh</Button></Space>}>
      <ResourceState loading={loading} error={error} empty={(data.items || []).length === 0}>
        <Table<ApiRecord> rowKey="id" dataSource={data.items || []} pagination={{ pageSize: 10 }} columns={[
          { title: "Author", dataIndex: "author_name" },
          { title: "Comment", dataIndex: "comment_text", ellipsis: true },
          { title: "Intent", dataIndex: "rule_intent_level", render: (value) => <StatusTag value={value} /> },
          { title: "Allowed", dataIndex: "reply_allowed", render: (value) => <Tag color={value ? "green" : "orange"}>{value ? "yes" : "no"}</Tag> },
          { title: "Action", render: (_, row) => <Button icon={<EyeOutlined />} onClick={() => setSelected(row)}>Details</Button> }
        ]} />
      </ResourceState>
      <LeadDrawer lead={selected} onClose={() => setSelected(null)} />
    </Page>
  );
}

function LeadDrawer({ lead, onClose }: { lead: ApiRecord | null; onClose: () => void }) {
  return (
    <Drawer open={Boolean(lead)} width={620} title="Lead details" onClose={onClose}>
      {lead && <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <Descriptions column={1} bordered size="small" items={[
          { key: "author", label: "Author", children: lead.author_name || "-" },
          { key: "comment", label: "Comment", children: lead.comment_text || "-" },
          { key: "confidence", label: "AI confidence", children: lead.llm_confidence || "-" },
          { key: "reason", label: "AI reason", children: lead.llm_reason || "-" },
          { key: "ownership", label: "Ownership", children: lead.ownership_status || "-" },
          { key: "allowed", label: "Reply allowed", children: String(Boolean(lead.reply_allowed)) },
          { key: "reply", label: "Suggested reply", children: lead.suggested_reply || "-" }
        ]} />
        <Space>
          {lead.source_content_url && <Button href={lead.source_content_url} target="_blank">Open post</Button>}
          {lead.direct_comment_url && <Button href={lead.direct_comment_url} target="_blank">Open comment</Button>}
        </Space>
      </Space>}
    </Drawer>
  );
}

function ReplyRules() {
  const { data: rows, loading, error, refresh } = useResource<ApiRecord[]>("/api/reply-rules", []);
  return (
    <Page title="Reply Rules">
      <ResourceState loading={loading} error={error} empty={rows.length === 0}>
        <Table rowKey="id" dataSource={rows} columns={[
          { title: "Name", dataIndex: "name" },
          { title: "Intent", dataIndex: "intent_type" },
          { title: "Confidence", dataIndex: "min_confidence" },
          { title: "Approval", dataIndex: "approval_mode" },
          { title: "Enabled", dataIndex: "enabled", render: (value, row) => <Switch checked={Boolean(value)} onChange={(checked) => apiPatch(`/api/reply-rules/${row.id}`, { enabled: checked }).then(refresh)} /> }
        ]} />
      </ResourceState>
    </Page>
  );
}

function Executions() {
  const { data: rows, loading, error, refresh } = useResource<ApiRecord[]>("/api/executions", []);
  const [selected, setSelected] = useState<ApiRecord | null>(null);
  useEffect(() => {
    if (!rows.some((row) => ["queued", "running", "pending", "retry_waiting"].includes(row.status))) return;
    const timer = window.setInterval(refresh, 3000);
    return () => window.clearInterval(timer);
  }, [rows, refresh]);
  return (
    <Page title="Executions" action={<Button icon={<ReloadOutlined />} onClick={refresh}>Refresh</Button>}>
      <ResourceState loading={loading} error={error} empty={rows.length === 0}>
        <Table<ApiRecord> rowKey="id" dataSource={rows} columns={[
          { title: "Trigger", dataIndex: "trigger_type" },
          { title: "Status", dataIndex: "status", render: (value) => <StatusTag value={value} /> },
          { title: "Progress", render: (_, row) => <Progress percent={Number(row.progress_percent || 0)} size="small" /> },
          { title: "Current keyword", dataIndex: "current_keyword", render: (value) => value || "-" },
          { title: "Keywords", render: (_, row) => `${row.completed_keywords || 0}/${row.total_keywords || 0} ok, ${row.failed_keywords || 0} failed` },
          { title: "Tokens", dataIndex: "total_tokens", render: (_, row) => row.total_tokens || "-" },
          { title: "Elapsed", dataIndex: "elapsed_ms", render: (value) => value ? `${Math.round(Number(value) / 1000)}s` : "-" },
          { title: "Action", render: (_, row) => <Space><Button icon={<EyeOutlined />} onClick={() => setSelected(row)}>Details</Button>{["queued", "running"].includes(row.status) && <Button danger onClick={() => apiPost(`/api/executions/${row.id}/cancel`).then(refresh)}>Cancel</Button>}</Space> }
        ]} />
      </ResourceState>
      <ExecutionDrawer execution={selected} onClose={() => setSelected(null)} />
    </Page>
  );
}

function ExecutionDrawer({ execution, onClose }: { execution: ApiRecord | null; onClose: () => void }) {
  const { data: fresh } = useResource<ApiRecord>(execution ? `/api/executions/${execution.id}` : "", execution || {});
  const { data: keywords } = useResource<ApiRecord[]>(execution ? `/api/executions/${execution.id}/keywords` : "", []);
  const row = fresh.id ? fresh : execution;
  return (
    <Drawer open={Boolean(execution)} width={760} title="Execution detail" onClose={onClose}>
      {row && <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <Descriptions column={2} bordered size="small" items={[
          { key: "trigger", label: "Trigger", children: row.trigger_type || "-" },
          { key: "status", label: "Status", children: <StatusTag value={row.status} /> },
          { key: "progress", label: "Progress", children: <Progress percent={Number(row.progress_percent || 0)} size="small" /> },
          { key: "current", label: "Current keyword", children: row.current_keyword || "-" },
          { key: "ok", label: "Completed keywords", children: row.completed_keywords || 0 },
          { key: "failed", label: "Failed keywords", children: row.failed_keywords || 0 },
          { key: "tokens", label: "Total tokens", children: row.total_tokens || 0 },
          { key: "elapsed", label: "Elapsed", children: row.elapsed_ms ? `${Math.round(Number(row.elapsed_ms) / 1000)}s` : "-" }
        ]} />
        <Tabs items={[{ key: "keywords", label: "Keywords", children: <Table<ApiRecord> size="small" rowKey="id" dataSource={keywords} pagination={false} columns={[
          { title: "Keyword", dataIndex: "keyword" },
          { title: "Status", dataIndex: "status", render: (value) => <StatusTag value={value} /> },
          { title: "Comments", dataIndex: "scanned_comments" },
          { title: "Leads", dataIndex: "lead_candidates" },
          { title: "Eligible", dataIndex: "eligible_count" },
          { title: "Tokens", dataIndex: "total_tokens" },
          { title: "Elapsed", dataIndex: "elapsed_ms", render: (value) => value ? `${Math.round(Number(value) / 1000)}s` : "-" },
          { title: "Error", dataIndex: "error_message", ellipsis: true }
        ]} /> }]} />
      </Space>}
    </Drawer>
  );
}

function TokenUsage() {
  const { data: summary, loading, error } = useResource<ApiRecord>("/api/token-usage/summary", {});
  const { data: details } = useResource<ApiRecord>("/api/token-usage/details", { by_model: [], by_campaign: [] });
  return (
    <Page title="Token Usage">
      <ResourceState loading={loading} error={error} empty={false}>
        <div className="grid">
          <Card><Statistic title="Today" value={summary.today || 0} /></Card>
          <Card><Statistic title="Last 7 days" value={summary.last_7_days || 0} /></Card>
          <Card><Statistic title="This month" value={summary.this_month || 0} /></Card>
        </div>
        <div className="wide-grid">
          <ProCard title="By model"><DataList rows={details.by_model || []} fields={["model", "total_tokens"]} /></ProCard>
          <ProCard title="By campaign"><DataList rows={details.by_campaign || []} fields={["campaign_id", "total_tokens"]} /></ProCard>
        </div>
      </ResourceState>
    </Page>
  );
}

function Settings() {
  const { data } = useResource<ApiRecord>("/api/settings", {});
  const { data: backend } = useResource<ApiRecord>("/api/version", {});
  const frontendVersion = import.meta.env.VITE_APP_VERSION || "0.1.0";
  const frontendCommit = import.meta.env.VITE_GIT_COMMIT || "unknown";
  return (
    <Page title="Settings">
      <ProCard title="Safety">
        <Space direction="vertical">
          <Typography.Text>Manual approval is required for every campaign run.</Typography.Text>
          <Switch checked={Boolean(data.send_disabled)} disabled />
        </Space>
      </ProCard>
      <ProCard title="Version">
        <Descriptions column={1} size="small" items={[
          { key: "frontend", label: "Frontend", children: `${frontendVersion} (${frontendCommit})` },
          { key: "backend", label: "Backend", children: `${backend.app_version || "unknown"} (${backend.git_commit || "unknown"})` },
          { key: "build", label: "Backend build", children: backend.build_time || "unknown" }
        ]} />
      </ProCard>
    </Page>
  );
}

function Page({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <PageContainer header={{ title }} extra={action ? [action] : []}>
      <div className="page-head"><h1>{title}</h1>{action}</div>
      {children}
    </PageContainer>
  );
}

function ResourceState({ loading, error, empty, children }: { loading: boolean; error: string | null; empty: boolean; children: React.ReactNode }) {
  if (loading) return <div className="state"><Spin /></div>;
  if (error) return <Alert type="error" message="Could not load data" description={error} showIcon />;
  if (empty) return <Empty />;
  return <>{children}</>;
}

function DataList({ rows, fields }: { rows: ApiRecord[]; fields: string[] }) {
  const columns: ColumnsType<ApiRecord> = useMemo(() => fields.map((field) => ({ title: field.split("_").join(" "), dataIndex: field, render: (value) => field === "status" ? <StatusTag value={value} /> : value || "-" })), [fields]);
  return <Table size="small" rowKey={(row) => row.id || row.model || row.campaign_id || row.run_id} dataSource={rows} columns={columns} pagination={false} />;
}

function StatusTag({ value }: { value: unknown }) {
  const text = String(value || "unknown");
  return <Tag color={statusColors[text] || "default"}>{text}</Tag>;
}

function useResource<T>(path: string, fallback: T) {
  const [data, setData] = useState<T>(fallback);
  const [loading, setLoading] = useState(Boolean(path));
  const [error, setError] = useState<string | null>(null);
  const refresh = async () => {
    if (!path) return;
    setLoading(true);
    setError(null);
    try {
      setData(await apiGet<T>(path));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    let cancelled = false;
    if (!path) return () => { cancelled = true; };
    setLoading(true);
    setError(null);
    apiGet<T>(path)
      .then((value) => { if (!cancelled) setData(value); })
      .catch((err) => { if (!cancelled) setError(err instanceof Error ? err.message : "Request failed"); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [path]);
  return { data, loading, error, refresh };
}

async function updateCampaign(id: string, values: ApiRecord, refresh: () => void) {
  await apiPatch(`/api/campaigns/${id}`, values);
  message.success("Campaign updated");
  refresh();
}

async function deleteCampaign(id: string, refresh: () => void) {
  await apiDelete(`/api/campaigns/${id}`);
  message.success("Campaign deleted");
  refresh();
}

async function pollExecutions() {
  await new Promise((resolve) => window.setTimeout(resolve, 3000));
}
