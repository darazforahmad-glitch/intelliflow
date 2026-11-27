"use client";

import { ShieldAlert } from "lucide-react";
import { useState } from "react";

import { RunsChart } from "@/components/charts";
import { StatusBadge } from "@/components/status";
import { useToast } from "@/components/toast";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  Input,
  Modal,
  PageHeader,
  Spinner,
} from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import {
  useAdminAction,
  useAdminMetrics,
  useAdminTemplates,
  useAdminWorkspaces,
  useAuditLogs,
} from "@/lib/queries";
import { useMe } from "@/lib/session";
import type { AdminWorkspace } from "@/lib/types";

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <Card className="p-4">
      <div className="text-sm text-slate-600">{label}</div>
      <div className="mt-1 text-2xl font-bold text-slate-900">{value}</div>
    </Card>
  );
}

function WorkspaceRow({ workspace }: { workspace: AdminWorkspace }) {
  const action = useAdminAction();
  const toast = useToast();
  const [suspending, setSuspending] = useState(false);
  const [reason, setReason] = useState("");
  const [limit, setLimit] = useState(String(workspace.ai_credit_limit ?? ""));

  async function run(path: string, body?: unknown, method: "POST" | "PATCH" = "POST") {
    try {
      await action.mutateAsync({ path, body, method });
      toast("Done.");
    } catch (error) {
      toast(errorMessage(error), "error");
    }
  }

  return (
    <tr className="border-t border-slate-100 align-middle">
      <td className="px-4 py-3">
        <div className="font-medium text-slate-900">{workspace.name}</div>
        <div className="text-xs text-slate-600">
          {workspace.owner_email} · since {formatDate(workspace.created_at)}
        </div>
        {workspace.suspended_reason ? (
          <div className="text-xs text-red-700">{workspace.suspended_reason}</div>
        ) : null}
      </td>
      <td className="px-3 py-3">
        <StatusBadge status={workspace.status === "suspended" ? "error" : "active"}>
          {workspace.status}
        </StatusBadge>
      </td>
      <td className="px-3 py-3 text-right tabular-nums">{workspace.runs_7d}</td>
      <td className="px-3 py-3">
        <div className="flex items-center gap-2">
          <span className="tabular-nums">{workspace.ai_credits_used} /</span>
          <input
            aria-label={`AI credit limit for ${workspace.name}`}
            className="min-h-9 w-24 rounded-lg border border-slate-300 px-2"
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
          />
          <Button
            size="sm"
            variant="ghost"
            onClick={() =>
              run(
                `/admin/workspaces/${workspace.id}/limits`,
                { ai_credit_limit: limit === "" ? null : Number(limit) },
                "PATCH",
              )
            }
          >
            Save
          </Button>
        </div>
      </td>
      <td className="px-4 py-3 text-right">
        {workspace.status === "suspended" ? (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => run(`/admin/workspaces/${workspace.id}/reactivate`)}
          >
            Reactivate
          </Button>
        ) : (
          <Button size="sm" variant="secondary" onClick={() => setSuspending(true)}>
            Suspend
          </Button>
        )}
        <Modal
          open={suspending}
          onClose={() => setSuspending(false)}
          title={`Suspend ${workspace.name}?`}
          footer={
            <>
              <Button variant="secondary" onClick={() => setSuspending(false)}>
                Cancel
              </Button>
              <Button
                variant="danger"
                disabled={reason.trim().length < 3}
                onClick={async () => {
                  await run(`/admin/workspaces/${workspace.id}/suspend`, { reason });
                  setSuspending(false);
                }}
              >
                Suspend workspace
              </Button>
            </>
          }
        >
          <p className="mb-3 text-sm text-slate-700">
            All automations pause and its users can no longer open the workspace.
          </p>
          <Input
            label="Reason (shown to the owner)"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </Modal>
      </td>
    </tr>
  );
}

export default function AdminPage() {
  const { data: me } = useMe();
  const metrics = useAdminMetrics();
  const workspaces = useAdminWorkspaces();
  const templates = useAdminTemplates();
  const audit = useAuditLogs();
  const action = useAdminAction();
  const toast = useToast();

  if (me && !me.is_platform_admin)
    return <EmptyState icon={<ShieldAlert className="size-6" />} title="Platform admins only" />;
  if (metrics.isLoading) return <Spinner />;
  if (metrics.error) return <Alert tone="error">{errorMessage(metrics.error)}</Alert>;
  const m = metrics.data!;

  return (
    <>
      <PageHeader
        title="Platform admin"
        description="Usage, AI cost and the shared template library. Message content is never shown here."
      />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Metric label="Active workspaces" value={m.workspaces.active} />
        <Metric label="Users" value={m.users} />
        <Metric label="Active automations" value={m.active_automations} />
        <Metric
          label="Failure rate (7 days)"
          value={m.failure_rate_7d === null ? "—" : `${m.failure_rate_7d}%`}
        />
        <Metric label="AI cost this month" value={`$${m.llm_month.cost_usd.toFixed(2)}`} />
      </div>
      <p className="mt-2 text-sm text-slate-600">
        {m.llm_month.calls} AI calls · {m.llm_month.input_tokens.toLocaleString()} input /{" "}
        {m.llm_month.output_tokens.toLocaleString()} output tokens this month.
      </p>
      <Card className="mt-6">
        <CardHeader title="Runs per day" description="Last 14 days, all workspaces." />
        <div className="p-4">
          <RunsChart data={m.runs_per_day} />
        </div>
      </Card>
      <Card className="mt-6">
        <CardHeader title="Workspaces" />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[48rem] text-sm">
            <thead className="text-left text-xs uppercase tracking-wide text-slate-600">
              <tr>
                <th className="px-4 py-2">Workspace</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2 text-right">Runs (7d)</th>
                <th className="px-3 py-2">AI credits used / limit</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody>
              {(workspaces.data ?? []).map((w) => (
                <WorkspaceRow key={w.id} workspace={w} />
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card className="mt-6">
        <CardHeader
          title="Template library"
          description="Publishing a version makes it the one new automations use."
        />
        <ul className="divide-y divide-slate-100">
          {(templates.data ?? []).map((t) => (
            <li key={t.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
              <div className="min-w-0 flex-1">
                <div className="font-medium text-slate-900">
                  {t.name} <span className="text-sm font-normal text-slate-500">v{t.version}</span>
                </div>
                <div className="text-xs text-slate-600">{t.code}</div>
              </div>
              {t.is_active ? (
                <Badge tone="green">published</Badge>
              ) : t.retired_at ? (
                <Badge>retired</Badge>
              ) : (
                <Badge tone="amber">draft</Badge>
              )}
              {t.is_active ? (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() =>
                    action
                      .mutateAsync({ path: `/admin/templates/${t.id}/retire` })
                      .then(() => toast("Template retired."))
                      .catch((e) => toast(errorMessage(e), "error"))
                  }
                >
                  Retire
                </Button>
              ) : (
                <Button
                  size="sm"
                  onClick={() =>
                    action
                      .mutateAsync({ path: `/admin/templates/${t.id}/publish` })
                      .then(() => toast("Template published."))
                      .catch((e) => toast(errorMessage(e), "error"))
                  }
                >
                  Publish
                </Button>
              )}
            </li>
          ))}
        </ul>
      </Card>
      <Card className="mt-6">
        <CardHeader title="Audit log" description="Latest 50 security and business events." />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[40rem] text-sm">
            <tbody>
              {(audit.data ?? []).map((entry) => (
                <tr key={entry.id} className="border-t border-slate-100">
                  <td className="whitespace-nowrap px-4 py-2 text-slate-600">
                    {formatDateTime(entry.created_at)}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-slate-900">{entry.action}</td>
                  <td className="px-3 py-2 text-slate-700">{entry.actor_email ?? "system"}</td>
                  <td className="px-4 py-2 text-xs text-slate-500">{entry.entity_type}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}
