/** Types mirroring the IntelliFlow REST API (/api/v1). */

export type Role = "owner" | "staff";
export type Language = "en" | "ur" | "roman-ur";

export interface User {
  id: string;
  full_name: string;
  email: string;
  phone: string | null;
  email_verified: boolean;
  is_platform_admin: boolean;
  created_at: string;
}

export interface MembershipSummary {
  membership_id: string;
  workspace_id: string;
  workspace_name: string;
  role: Role;
  status: string;
  workspace_status: string;
}

export interface Me extends User {
  memberships: MembershipSummary[];
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: User;
}

export interface Workspace {
  id: string;
  name: string;
  business_type: string | null;
  language_pref: Language;
  timezone: string;
  status: string;
  approval_threshold: string;
  currency: string;
  ai_credit_limit: number | null;
  created_at: string;
  role: Role | null;
}

export interface Member {
  membership_id: string;
  user_id: string;
  full_name: string;
  email: string;
  role: Role;
  status: string;
  joined_at: string;
}

export interface Invitation {
  id: string;
  email: string;
  role: Role;
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  created_at: string;
}

export interface InterviewMessage {
  id: string;
  sender: "ai" | "user";
  content: string;
  language: string | null;
  created_at: string;
  meta_json: { status?: string; missing?: string[]; kind?: string };
}

export interface InterviewSession {
  id: string;
  process_name: string;
  status: "in_progress" | "completed" | "abandoned";
  started_at: string;
  completed_at: string | null;
  question_count: number;
  max_questions: number;
  ready_for_mapping: boolean;
  language: string | null;
  messages: InterviewMessage[];
  latest_map_id: string | null;
}

export interface InterviewSummary {
  id: string;
  process_name: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  latest_map_id: string | null;
  latest_version: number | null;
}

export type StepType = "start" | "manual" | "automated" | "human_only" | "end";

export interface ProcessStep {
  id: string;
  key: string;
  seq_no: number;
  title: string;
  actor: string | null;
  action: string | null;
  step_type: StepType;
  app: string | null;
  minutes_per_run: string | null;
  runs_per_week: number | null;
  weekly_minutes: string;
  is_manual: boolean;
  predecessor_key: string | null;
  involves_customer_messaging: boolean;
  involves_money: boolean;
  support_status: string | null;
}

export interface TemplateRef {
  id: string;
  code: string;
  name: string;
  category: string | null;
  required_connections: string[];
}

export interface Opportunity {
  id: string;
  rank: number | null;
  score: string;
  status: "suggested" | "selected" | "dismissed" | "automated";
  fit: string;
  risk: string;
  minutes_saved_per_week: string;
  minutes_saved_per_day: string;
  reason: string;
  step_id: string;
  step_key: string;
  step_title: string;
  template: TemplateRef | null;
  automation_id: string | null;
}

export interface GraphNode {
  id: string;
  position: { x: number; y: number };
  data: Record<string, unknown>;
}

export interface ProcessMap {
  id: string;
  session_id: string;
  name: string;
  version: number;
  is_latest: boolean;
  created_at: string;
  change_note: string | null;
  graph_json: { nodes: GraphNode[]; edges: { id: string; source: string; target: string }[] };
  steps: ProcessStep[];
  total_weekly_minutes: string;
  manual_weekly_minutes: string;
  opportunities: Opportunity[];
  other_opportunities: Opportunity[];
  dismissed_opportunities: Opportunity[];
  unsupported_steps: string[];
  versions: { id: string; version: number; created_at: string; change_note: string | null }[];
}

export interface ProcessMapSummary {
  id: string;
  session_id: string;
  name: string;
  version: number;
  created_at: string;
  step_count: number;
  manual_weekly_minutes: string;
  top_opportunity: string | null;
}

export interface Template {
  id: string;
  code: string;
  name: string;
  category: string | null;
  description: string | null;
  version: number;
  required_connections: string[];
  trigger_type: string;
  steps: string[];
  estimated_minutes_saved: number | null;
}

/* ---------------------------------------------------------------- workflow definitions */
export interface ExtractField {
  name: string;
  type: "string" | "number" | "integer" | "boolean";
  description?: string;
  required?: boolean;
}

export interface ProposedAction {
  connector: string;
  operation: string;
  params: Record<string, unknown>;
}

export interface Block {
  key: string;
  type:
    "ai.classify" | "ai.extract" | "ai.draft_reply" | "ai.summarize" | "condition" | "approval" | "action";
  title?: string;
  description?: string;
  input?: string;
  labels?: string[];
  instructions?: string;
  fields?: ExtractField[];
  language?: string;
  facts?: Record<string, string>;
  if?: string;
  else?: "stop" | "continue";
  kind?: "customer_message" | "money" | "review";
  when?: string;
  message?: string;
  show?: string[];
  proposed_action?: ProposedAction;
  editable?: string[];
  connector?: string;
  operation?: string;
  params?: Record<string, unknown>;
}

export interface Trigger {
  type: string;
  filters?: Record<string, unknown>;
  at?: string;
  every_minutes?: number;
}

export interface WorkflowDefinition {
  schema_version: 1;
  name: string;
  description?: string;
  trigger: Trigger;
  blocks: Block[];
  settings?: Record<string, unknown>;
}

export interface ValidationIssue {
  code: string;
  message: string;
  path: (string | number)[];
  block: string | null;
  details: Record<string, unknown> | null;
}

export interface AutomationVersion {
  id: string;
  version_no: number;
  definition_json: WorkflowDefinition;
  validated: boolean;
  test_passed: boolean;
  validation_errors: ValidationIssue[];
  source: string;
  created_at: string;
}

export interface AutomationStats {
  runs_total: number;
  runs_succeeded: number;
  runs_failed: number;
  runs_waiting: number;
  minutes_saved: string;
  last_run_at: string | null;
}

export type AutomationStatus = "draft" | "validated" | "tested" | "active" | "paused" | "error" | "archived";

export interface Automation {
  id: string;
  name: string;
  description: string | null;
  status: AutomationStatus;
  status_reason: string | null;
  trigger_type: string | null;
  template_code: string | null;
  template_name: string | null;
  opportunity_id: string | null;
  auto_send: boolean;
  clean_approvals: number;
  auto_send_threshold: number;
  estimated_minutes_per_run: string;
  activated_at: string | null;
  created_at: string;
  updated_at: string;
  current_version: AutomationVersion | null;
  versions: Omit<AutomationVersion, "definition_json" | "validation_errors">[];
  connections: { provider: string; label: string; connected: boolean; mode: string | null }[];
  stats: AutomationStats;
}

export interface AutomationListItem {
  id: string;
  name: string;
  status: AutomationStatus;
  status_reason: string | null;
  trigger_type: string | null;
  template_name: string | null;
  auto_send: boolean;
  version_no: number | null;
  stats: AutomationStats;
}

export type RunStatus = "queued" | "running" | "waiting_approval" | "succeeded" | "failed" | "cancelled";

export interface Run {
  id: string;
  automation_id: string;
  automation_name: string;
  version_no: number | null;
  status: RunStatus;
  is_test: boolean;
  trigger_type: string;
  minutes_saved: string;
  summary: string | null;
  error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
}

export interface StepRun {
  id: string;
  step_key: string;
  seq_no: number;
  block_type: string;
  status: string;
  input_json: Record<string, unknown> | null;
  output_json: Record<string, unknown> | null;
  error: string | null;
  attempt: number;
  started_at: string | null;
  finished_at: string | null;
}

export interface RunDetail extends Run {
  steps: StepRun[];
  approvals: {
    id: string;
    kind: string;
    title: string;
    status: string;
    created_at: string;
    decided_at: string | null;
  }[];
}

export interface TestResult {
  passed: boolean;
  message: string;
  run: Run;
  steps: {
    key: string;
    type: string;
    title: string;
    status: string;
    input: Record<string, unknown>;
    output: Record<string, unknown>;
    attempts: number;
  }[];
  sandbox_records: { ref: string; provider: string; operation: string; payload: Record<string, unknown> }[];
}

export type ApprovalKind = "customer_message" | "money" | "review" | "window_closed";

export interface Approval {
  id: string;
  status: "pending" | "reminded" | "approved" | "edited" | "rejected" | "expired";
  kind: ApprovalKind;
  title: string;
  automation_id: string;
  automation_name: string;
  run_id: string;
  step_title: string | null;
  payload: {
    message?: string | null;
    input?: string | null;
    show?: Record<string, unknown>;
    ai_output?: Record<string, unknown>;
    proposed_action?: ProposedAction | null;
    editable?: string[];
    missing?: string[];
    fields?: ExtractField[];
    confidence?: number;
  };
  decision_payload: Record<string, unknown> | null;
  decided_by_name: string | null;
  decided_at: string | null;
  decision_note: string | null;
  created_at: string;
  remind_at: string | null;
  expires_at: string | null;
}

export interface Connection {
  id: string;
  provider: "whatsapp" | "gmail" | "google_sheets" | "webform";
  label: string;
  mode: "live" | "sandbox";
  status: "connected" | "needs_attention" | "disconnected";
  display_name: string | null;
  external_account_id: string | null;
  config: Record<string, unknown>;
  last_error: string | null;
  created_at: string;
  webhook_url: string | null;
  has_credentials: boolean;
}

export interface SandboxView {
  sheets: Record<string, Record<string, unknown>[]>;
  outbox: Record<string, unknown>[];
}

export interface Dashboard {
  period: { days: number; start: string; end: string; timezone: string };
  kpis: {
    hours_saved: number;
    hours_saved_previous_period: number;
    tasks_handled: number;
    runs: number;
    runs_succeeded: number;
    runs_failed: number;
    runs_waiting: number;
    approvals_pending: number;
    active_automations: number;
    success_rate: number | null;
  };
  hours_saved_per_day: { date: string; iso_date: string; label: string; hours: number }[];
  recent_failures: {
    run_id: string;
    automation_id: string;
    automation_name: string;
    error: string | null;
    created_at: string;
  }[];
  ai_credits: { used: number; limit: number | null };
}

export interface AppNotification {
  id: string;
  kind: string;
  title: string;
  body: string;
  url: string | null;
  workspace_id: string | null;
  read: boolean;
  created_at: string;
}

export interface AdminMetrics {
  workspaces: { active: number; suspended: number };
  users: number;
  active_automations: number;
  runs_per_day: { date: string; runs: number; failed: number }[];
  failure_rate_7d: number | null;
  llm_month: { input_tokens: number; output_tokens: number; cost_usd: number; calls: number };
}

export interface AdminWorkspace {
  id: string;
  name: string;
  business_type: string | null;
  status: string;
  suspended_reason: string | null;
  owner_email: string | null;
  created_at: string;
  runs_7d: number;
  ai_credits_used: number;
  ai_credit_limit: number | null;
}

export interface AdminTemplate {
  id: string;
  code: string;
  name: string;
  category: string | null;
  version: number;
  is_active: boolean;
  retired_at: string | null;
  required_connections: string[];
  description: string | null;
  updated_at: string;
}

export interface AuditEntry {
  id: string;
  action: string;
  workspace_id: string | null;
  actor_email: string | null;
  entity_type: string | null;
  entity_id: string | null;
  data: Record<string, unknown>;
  created_at: string;
}

export interface ConnectorCatalog {
  provider: string;
  label: string;
  operations: {
    name: string;
    label: string;
    writes: boolean;
    customer_message: boolean;
    required: string[];
  }[];
}
