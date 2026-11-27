"use client";

import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";

import { api } from "./api";
import { useWorkspaceId } from "./session";
import type {
  AdminMetrics,
  AdminTemplate,
  AdminWorkspace,
  AppNotification,
  Approval,
  AuditEntry,
  Automation,
  AutomationListItem,
  Connection,
  ConnectorCatalog,
  Dashboard,
  InterviewSession,
  InterviewSummary,
  Invitation,
  Member,
  ProcessMap,
  ProcessMapSummary,
  Run,
  RunDetail,
  SandboxView,
  Template,
  TestResult,
  ValidationIssue,
  WorkflowDefinition,
  Workspace,
} from "./types";

/** Workspace-scoped path and key helpers. */
function useWs() {
  const workspaceId = useWorkspaceId();
  return {
    workspaceId,
    path: (suffix: string) => `/workspaces/${workspaceId}${suffix}`,
    key: (...parts: unknown[]): QueryKey => ["ws", workspaceId, ...parts],
  };
}

function useWsQuery<T>(
  parts: unknown[],
  suffix: string,
  options: { enabled?: boolean; refetchInterval?: number } = {},
) {
  const ws = useWs();
  return useQuery({
    queryKey: ws.key(...parts),
    queryFn: ({ signal }) => api.get<T>(ws.path(suffix), signal),
    enabled: Boolean(ws.workspaceId) && options.enabled !== false,
    refetchInterval: options.refetchInterval,
  });
}

/** Mutation that invalidates the given workspace query prefixes afterwards. */
function useWsMutation<TVars, TResult>(
  fn: (vars: TVars, path: (s: string) => string) => Promise<TResult>,
  invalidate: string[],
) {
  const ws = useWs();
  const client = useQueryClient();
  return useMutation({
    mutationFn: (vars: TVars) => fn(vars, ws.path),
    onSuccess: async () => {
      await Promise.all(invalidate.map((part) => client.invalidateQueries({ queryKey: ws.key(part) })));
    },
  });
}

/* ------------------------------------------------------------------ workspace & team */
export const useWorkspace = () => useWsQuery<Workspace>(["workspace"], "");
export const useMembers = () => useWsQuery<Member[]>(["members"], "/members");
export const useInvitations = (enabled = true) =>
  useWsQuery<Invitation[]>(["invitations"], "/invitations", { enabled });
export const useUpdateWorkspace = () =>
  useWsMutation(
    (body: Partial<Workspace>, path) => api.patch<Workspace>(path(""), body),
    ["workspace", "dashboard"],
  );
export const useInvite = () =>
  useWsMutation(
    (body: { email: string }, path) => api.post<Invitation>(path("/invitations"), body),
    ["invitations", "members"],
  );
export const useRevokeInvitation = () =>
  useWsMutation((id: string, path) => api.del(path(`/invitations/${id}`)), ["invitations"]);
export const useRemoveMember = () =>
  useWsMutation((id: string, path) => api.del(path(`/members/${id}`)), ["members"]);
export const useKillSwitch = () =>
  useWsMutation(
    (_: void, path) => api.post<{ paused_automations: number }>(path("/kill-switch")),
    ["automations", "dashboard"],
  );

/* ------------------------------------------------------------------ flow mapper */
export const useInterviews = () => useWsQuery<InterviewSummary[]>(["interviews"], "/interviews");
export const useInterview = (id: string) =>
  useWsQuery<InterviewSession>(["interviews", id], `/interviews/${id}`);
export const useStartInterview = () =>
  useWsMutation(
    (body: { process_name: string }, path) => api.post<InterviewSession>(path("/interviews"), body),
    ["interviews"],
  );
export const useAnswer = (id: string) =>
  useWsMutation(
    (content: string, path) => api.post<InterviewSession>(path(`/interviews/${id}/messages`), { content }),
    ["interviews"],
  );
export const useCompleteInterview = (id: string) =>
  useWsMutation(
    (_: void, path) => api.post<ProcessMap>(path(`/interviews/${id}/complete`)),
    ["interviews", "maps"],
  );
export const useProcessMaps = () => useWsQuery<ProcessMapSummary[]>(["maps"], "/process-maps");
export const useProcessMap = (id: string | null | undefined) =>
  useWsQuery<ProcessMap>(["maps", id], `/process-maps/${id}`, { enabled: Boolean(id) });
export const useSaveMapVersion = (mapId: string) =>
  useWsMutation(
    (body: unknown, path) => api.post<ProcessMap>(path(`/process-maps/${mapId}/versions`), body),
    ["maps"],
  );
export const useDismissOpportunity = () =>
  useWsMutation((id: string, path) => api.post<ProcessMap>(path(`/opportunities/${id}/dismiss`)), ["maps"]);
export const useRestoreOpportunity = () =>
  useWsMutation((id: string, path) => api.post<ProcessMap>(path(`/opportunities/${id}/restore`)), ["maps"]);

/* ------------------------------------------------------------------ automations */
export const useAutomations = () => useWsQuery<AutomationListItem[]>(["automations"], "/automations");
export const useAutomation = (id: string) =>
  useWsQuery<Automation>(["automations", id], `/automations/${id}`);
export const useGenerateAutomation = () =>
  useWsMutation(
    (opportunityId: string, path) => api.post<Automation>(path(`/opportunities/${opportunityId}/automation`)),
    ["automations", "maps"],
  );
export const useCreateFromTemplate = () =>
  useWsMutation(
    (templateCode: string, path) =>
      api.post<Automation>(path("/automations/from-template"), { template_code: templateCode }),
    ["automations"],
  );
export const useSaveDefinition = (id: string) =>
  useWsMutation(
    (definition: WorkflowDefinition, path) =>
      api.put<Automation>(path(`/automations/${id}/definition`), { definition }),
    ["automations"],
  );
export const useValidateDefinition = (id: string) =>
  useWsMutation(
    (definition: WorkflowDefinition, path) =>
      api.post<{ valid: boolean; issues: ValidationIssue[] }>(path(`/automations/${id}/validate`), {
        definition,
      }),
    [],
  );
export const useTestAutomation = (id: string) =>
  useWsMutation(
    (sample: Record<string, unknown>, path) =>
      api.post<TestResult>(path(`/automations/${id}/test`), { sample }),
    ["automations"],
  );
export const useAutomationAction = (id: string) =>
  useWsMutation(
    (action: "activate" | "pause" | "archive" | "repair", path) =>
      api.post<Automation>(path(`/automations/${id}/${action}`)),
    ["automations", "dashboard", "maps"],
  );
export const useRollback = (id: string) =>
  useWsMutation(
    (versionNo: number, path) =>
      api.post<Automation>(path(`/automations/${id}/rollback`), { version_no: versionNo }),
    ["automations"],
  );
export const useAutoSend = (id: string) =>
  useWsMutation(
    (enabled: boolean, path) => api.post<Automation>(path(`/automations/${id}/auto-send`), { enabled }),
    ["automations"],
  );

/* ------------------------------------------------------------------ runs & approvals */
export const useRuns = (filters: { status?: string; automation_id?: string } = {}) => {
  const query = new URLSearchParams(
    Object.entries(filters).filter(([, v]) => v) as [string, string][],
  ).toString();
  return useWsQuery<Run[]>(["runs", filters], `/runs${query ? `?${query}` : ""}`);
};
export const useRun = (id: string) => useWsQuery<RunDetail>(["runs", "detail", id], `/runs/${id}`);
export const useApprovals = (state: "open" | "decided" | "all" = "open") =>
  useWsQuery<Approval[]>(["approvals", state], state === "open" ? "/approvals" : `/approvals?state=${state}`);
export const useApproval = (id: string) =>
  useWsQuery<Approval>(["approvals", "detail", id], `/approvals/${id}`);
export const useDecide = () =>
  useWsMutation(
    (
      vars: {
        id: string;
        decision: "approve" | "edit" | "reject";
        edited_params?: Record<string, unknown>;
        edited_fields?: Record<string, unknown>;
        note?: string;
      },
      path,
    ) => {
      const { id, ...body } = vars;
      return api.post<Approval>(path(`/approvals/${id}/decision`), body);
    },
    ["approvals", "runs", "dashboard", "automations"],
  );

/* ------------------------------------------------------------------ integrations */
export const useConnections = () => useWsQuery<Connection[]>(["connections"], "/connections");
export const useSandboxRecords = (id: string | null, enabled = true) =>
  useWsQuery<SandboxView>(["connections", id, "sandbox"], `/connections/${id}/sandbox`, {
    enabled: Boolean(id) && enabled,
  });
export const useCreateSandbox = () =>
  useWsMutation(
    (provider: string, path) => api.post<Connection>(path("/connections/sandbox"), { provider }),
    ["connections", "automations"],
  );
export const useConnectWhatsApp = () =>
  useWsMutation(
    (body: Record<string, string>, path) => api.post<Connection>(path("/connections/whatsapp"), body),
    ["connections"],
  );
export const useCreateWebform = () =>
  useWsMutation(
    (name: string, path) => api.post<Connection>(path("/connections/webform"), { name }),
    ["connections"],
  );
export const useDisconnect = () =>
  useWsMutation(
    (id: string, path) => api.del<{ message: string }>(path(`/connections/${id}`)),
    ["connections", "automations"],
  );
export const useSimulate = () =>
  useWsMutation(
    (vars: { id: string; body: Record<string, unknown> }, path) =>
      api.post<Record<string, unknown>>(path(`/connections/${vars.id}/simulate`), vars.body),
    ["runs", "approvals", "dashboard", "connections", "automations"],
  );

/* ------------------------------------------------------------------ dashboard & notifications */
export const useDashboard = (days: number) =>
  useWsQuery<Dashboard>(["dashboard", days], `/dashboard?days=${days}`);

export function useNotifications() {
  return useQuery({
    queryKey: ["notifications"],
    queryFn: () => api.get<{ unread: number; items: AppNotification[] }>("/notifications"),
    refetchInterval: 60_000,
  });
}

export function useMarkAllRead() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => api.post("/notifications/read-all"),
    onSuccess: () => client.invalidateQueries({ queryKey: ["notifications"] }),
  });
}

/* ------------------------------------------------------------------ catalogues */
export const useTemplates = () =>
  useQuery({ queryKey: ["templates"], queryFn: () => api.get<Template[]>("/templates"), staleTime: 300_000 });
export const useConnectorCatalog = () =>
  useQuery({
    queryKey: ["connector-catalog"],
    queryFn: () => api.get<ConnectorCatalog[]>("/connectors"),
    staleTime: 300_000,
  });

/* ------------------------------------------------------------------ platform admin */
export const useAdminMetrics = () =>
  useQuery({ queryKey: ["admin", "metrics"], queryFn: () => api.get<AdminMetrics>("/admin/metrics") });
export const useAdminWorkspaces = () =>
  useQuery({
    queryKey: ["admin", "workspaces"],
    queryFn: () => api.get<AdminWorkspace[]>("/admin/workspaces"),
  });
export const useAdminTemplates = () =>
  useQuery({ queryKey: ["admin", "templates"], queryFn: () => api.get<AdminTemplate[]>("/admin/templates") });
export const useAuditLogs = () =>
  useQuery({
    queryKey: ["admin", "audit"],
    queryFn: () => api.get<AuditEntry[]>("/admin/audit-logs?limit=50"),
  });

export function useAdminAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (vars: { path: string; body?: unknown; method?: "POST" | "PATCH" }) =>
      vars.method === "PATCH" ? api.patch(vars.path, vars.body) : api.post(vars.path, vars.body),
    onSuccess: () => client.invalidateQueries({ queryKey: ["admin"] }),
  });
}
