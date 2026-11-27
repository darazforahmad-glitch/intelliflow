"use client";

import clsx from "clsx";
import {
  AlertTriangle,
  ArrowRight,
  Clock,
  Download,
  ListChecks,
  MessagesSquare,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";

import { HoursSavedChart } from "@/components/charts";
import { APPROVAL_KIND, StatusBadge } from "@/components/status";
import { useToast } from "@/components/toast";
import {
  Badge,
  Button,
  ButtonLink,
  Card,
  CardHeader,
  EmptyState,
  PageHeader,
  Segmented,
  Skeleton,
} from "@/components/ui";
import { apiFetch, errorMessage } from "@/lib/api";
import { minutesLabel, timeAgo, TRIGGER_LABELS } from "@/lib/format";
import { useApprovals, useAutomations, useDashboard } from "@/lib/queries";
import { useMe, useWorkspaceId } from "@/lib/session";

function Kpi({
  icon,
  label,
  value,
  detail,
  href,
  tone = "brand",
}: {
  icon: ReactNode;
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  href?: string;
  tone?: "brand" | "green" | "amber" | "red";
}) {
  const body = (
    <Card className={clsx("h-full p-5 transition-shadow", href && "hover:shadow-md")}>
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-600">{label}</span>
        <span
          className={clsx(
            "rounded-xl p-2",
            tone === "brand" && "bg-brand-50 text-brand-600",
            tone === "green" && "bg-saved-50 text-saved-600",
            tone === "amber" && "bg-amber-50 text-amber-600",
            tone === "red" && "bg-red-50 text-red-600",
          )}
        >
          {icon}
        </span>
      </div>
      <div className="mt-3 text-3xl font-bold tracking-tight text-slate-900">{value}</div>
      {detail ? <div className="mt-1 text-sm text-slate-600">{detail}</div> : null}
    </Card>
  );
  return href ? (
    <Link href={href} className="block rounded-2xl">
      {body}
    </Link>
  ) : (
    body
  );
}

function greeting() {
  const hour = new Date().getHours();
  return hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
}

export default function DashboardPage() {
  const [days, setDays] = useState<"7" | "30">("7");
  const { data, isLoading } = useDashboard(Number(days));
  const automations = useAutomations();
  const approvals = useApprovals("open");
  const { data: me } = useMe();
  const workspaceId = useWorkspaceId();
  const toast = useToast();
  const [exporting, setExporting] = useState(false);

  async function exportCsv() {
    setExporting(true);
    try {
      const csv = await apiFetch<string>(`/workspaces/${workspaceId}/reports/weekly.csv?days=${days}`);
      const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
      const link = Object.assign(document.createElement("a"), {
        href: url,
        download: `intelliflow-report-${days}d.csv`,
      });
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      toast(errorMessage(error), "error");
    } finally {
      setExporting(false);
    }
  }

  const k = data?.kpis;
  const delta = k ? k.hours_saved - k.hours_saved_previous_period : 0;

  return (
    <>
      <PageHeader
        eyebrow={`${greeting()}, ${me?.full_name.split(" ")[0] ?? ""}`}
        title="Operations dashboard"
        description="What your automations did, what is waiting for you and the time you got back."
        actions={
          <>
            <Segmented
              label="Period"
              value={days}
              onChange={setDays}
              options={[
                { value: "7", label: "7 days" },
                { value: "30", label: "30 days" },
              ]}
            />
            <Button
              variant="secondary"
              icon={<Download className="size-4" />}
              onClick={exportCsv}
              loading={exporting}
            >
              Export CSV
            </Button>
          </>
        }
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {isLoading || !k ? (
          Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-32" />)
        ) : (
          <>
            <Kpi
              icon={<Clock className="size-5" />}
              tone="green"
              label="Hours saved"
              value={`${k.hours_saved} h`}
              detail={
                delta >= 0
                  ? `+${delta.toFixed(1)} h vs previous period`
                  : `${delta.toFixed(1)} h vs previous period`
              }
            />
            <Kpi
              icon={<ListChecks className="size-5" />}
              label="Tasks handled"
              value={k.tasks_handled}
              detail={`${k.runs} ${k.runs === 1 ? "run" : "runs"} · ${k.success_rate ?? "—"}% succeeded`}
            />
            <Kpi
              icon={<MessagesSquare className="size-5" />}
              tone="amber"
              label="Approvals waiting"
              value={k.approvals_pending}
              detail="Tap to review"
              href="/approvals"
            />
            <Kpi
              icon={<AlertTriangle className="size-5" />}
              tone={k.runs_failed ? "red" : "brand"}
              label="Failures"
              value={k.runs_failed}
              detail={`${k.active_automations} automation(s) active`}
            />
          </>
        )}
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title="Hours saved per day"
            description={
              data
                ? `${data.hours_saved_per_day[0]?.date} – ${data.hours_saved_per_day.at(-1)?.date}`
                : undefined
            }
          />
          <div className="p-4">
            {data ? <HoursSavedChart data={data.hours_saved_per_day} /> : <Skeleton className="h-64" />}
          </div>
        </Card>
        <Card>
          <CardHeader
            title="Approvals queue"
            actions={
              <ButtonLink href="/approvals" variant="ghost" size="sm">
                Open
              </ButtonLink>
            }
          />
          <ul className="divide-y divide-slate-100">
            {(approvals.data ?? []).slice(0, 5).map((a) => (
              <li key={a.id}>
                <Link
                  href={`/approvals/${a.id}`}
                  className="flex items-start gap-3 px-5 py-3 hover:bg-slate-50"
                >
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium text-slate-900">{a.title}</div>
                    <div className="truncate text-xs text-slate-600">
                      {a.automation_name} · {timeAgo(a.created_at)}
                    </div>
                  </div>
                  <Badge tone={APPROVAL_KIND[a.kind]?.tone ?? "gray"}>
                    {APPROVAL_KIND[a.kind]?.label ?? a.kind}
                  </Badge>
                </Link>
              </li>
            ))}
            {approvals.data && !approvals.data.length ? (
              <li className="px-5 py-8 text-center text-sm text-slate-600">Nothing is waiting for you. 🎉</li>
            ) : null}
          </ul>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader
          title="Automations"
          description="Status, runs and time saved over all time."
          actions={
            <ButtonLink href="/automations" variant="ghost" size="sm">
              Manage
            </ButtonLink>
          }
        />
        {automations.data && !automations.data.length ? (
          <EmptyState
            icon={<Sparkles className="size-6" />}
            title="No automations yet"
            description="Interview the Flow Mapper about one process and it will suggest what to automate first."
            action={<ButtonLink href="/flow-mapper?new=1">Start an interview</ButtonLink>}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[40rem] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-600">
                <tr className="border-b border-slate-100">
                  <th className="px-5 py-3 font-semibold">Automation</th>
                  <th className="px-3 py-3 font-semibold">Status</th>
                  <th className="px-3 py-3 text-right font-semibold">Runs</th>
                  <th className="px-3 py-3 text-right font-semibold">Time saved</th>
                  <th className="px-5 py-3 font-semibold">Last run</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {(automations.data ?? []).map((a) => (
                  <tr key={a.id} className="hover:bg-slate-50">
                    <td className="px-5 py-3">
                      <Link
                        href={`/automations/${a.id}`}
                        className="font-medium text-slate-900 hover:text-brand-700"
                      >
                        {a.name}
                      </Link>
                      <div className="text-xs text-slate-600">
                        {TRIGGER_LABELS[a.trigger_type ?? ""] ?? "—"}
                      </div>
                    </td>
                    <td className="px-3 py-3">
                      <StatusBadge status={a.status} />
                    </td>
                    <td className="px-3 py-3 text-right tabular-nums">{a.stats.runs_total}</td>
                    <td className="px-3 py-3 text-right tabular-nums">
                      {minutesLabel(a.stats.minutes_saved)}
                    </td>
                    <td className="px-5 py-3 text-slate-600">{timeAgo(a.stats.last_run_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Recent failures" />
          <ul className="divide-y divide-slate-100">
            {(data?.recent_failures ?? []).map((f) => (
              <li key={f.run_id}>
                <Link
                  href={`/runs/${f.run_id}`}
                  className="flex items-center gap-3 px-5 py-3 hover:bg-slate-50"
                >
                  <AlertTriangle className="size-4 shrink-0 text-red-500" aria-hidden />
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-medium text-slate-900">{f.automation_name}</div>
                    <div className="truncate text-xs text-slate-600">{f.error}</div>
                  </div>
                  <span className="text-xs text-slate-500">{timeAgo(f.created_at)}</span>
                  <ArrowRight className="size-4 text-slate-400" aria-hidden />
                </Link>
              </li>
            ))}
            {data && !data.recent_failures.length ? (
              <li className="px-5 py-6 text-sm text-slate-600">
                No failed runs. Everything is running smoothly.
              </li>
            ) : null}
          </ul>
        </Card>
        <Card className="p-5">
          <h2 className="font-semibold text-slate-900">AI credits this month</h2>
          {data ? (
            <>
              <div className="mt-3 text-2xl font-bold">
                {data.ai_credits.used}
                <span className="text-base font-medium text-slate-500">
                  {" "}
                  / {data.ai_credits.limit ?? "∞"}
                </span>
              </div>
              <div
                className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100"
                role="progressbar"
                aria-valuenow={data.ai_credits.used}
                aria-valuemax={data.ai_credits.limit ?? undefined}
                aria-label="AI credits used"
              >
                <div
                  className={clsx(
                    "h-full rounded-full",
                    data.ai_credits.limit && data.ai_credits.used / data.ai_credits.limit >= 0.8
                      ? "bg-amber-500"
                      : "bg-brand-500",
                  )}
                  style={{
                    width: `${data.ai_credits.limit ? Math.min(100, (data.ai_credits.used / data.ai_credits.limit) * 100) : 5}%`,
                  }}
                />
              </div>
              <p className="mt-2 text-xs text-slate-600">
                One credit per AI step. You will be warned at 80%; AI steps pause at 100%.
              </p>
            </>
          ) : (
            <Skeleton className="mt-3 h-16" />
          )}
        </Card>
      </div>
    </>
  );
}
