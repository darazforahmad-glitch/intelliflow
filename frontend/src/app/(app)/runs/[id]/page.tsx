"use client";

import { ArrowLeft, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { BLOCK_META } from "@/components/builder";
import { APPROVAL_KIND, StatusBadge } from "@/components/status";
import { Alert, Badge, Card, CardHeader, KeyValue, PageHeader, Spinner } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { formatDateTime, minutesLabel, TRIGGER_LABELS } from "@/lib/format";
import { useRun } from "@/lib/queries";
import type { Block } from "@/lib/types";

export default function RunPage() {
  const { id } = useParams<{ id: string }>();
  const { data: run, isLoading, error } = useRun(id);
  if (isLoading) return <Spinner />;
  if (error || !run) return <Alert tone="error">{errorMessage(error)}</Alert>;
  return (
    <>
      <Link
        href={`/automations/${run.automation_id}`}
        className="mb-3 inline-flex min-h-9 items-center gap-1 text-sm font-medium text-slate-600 hover:text-slate-900"
      >
        <ArrowLeft className="size-4" aria-hidden /> {run.automation_name}
      </Link>
      <PageHeader
        title={`Run of ${run.automation_name}`}
        description={`${TRIGGER_LABELS[run.trigger_type] ?? run.trigger_type} · version ${run.version_no} · ${formatDateTime(run.created_at)}${run.duration_seconds !== null ? ` · took ${run.duration_seconds.toFixed(1)} s` : ""}`}
        actions={
          <>
            {run.is_test ? <Badge tone="purple">Test run</Badge> : null}
            <StatusBadge status={run.status} />
            {Number(run.minutes_saved) ? (
              <Badge tone="green">saved {minutesLabel(run.minutes_saved)}</Badge>
            ) : null}
          </>
        }
      />
      {run.error ? (
        <Alert tone="error" className="mb-4" title="Why it failed">
          {run.error}
        </Alert>
      ) : run.summary ? (
        <Alert tone="info" className="mb-4">
          {run.summary}
        </Alert>
      ) : null}
      <Card>
        <CardHeader title="Steps" description="Inputs and outputs are shown with personal data masked." />
        <ol className="divide-y divide-slate-100">
          {run.steps.map((step) => {
            const meta = BLOCK_META[step.block_type as Block["type"]] ?? BLOCK_META.action;
            return (
              <li key={step.id} className="px-5 py-4">
                <div className="flex flex-wrap items-center gap-3">
                  <span className={`grid size-8 place-items-center rounded-lg ${meta.tone}`}>
                    {meta.icon}
                  </span>
                  <span className="font-medium text-slate-900">
                    {step.seq_no + 1}. {step.step_key}
                  </span>
                  <span className="text-sm text-slate-600">{meta.label}</span>
                  <StatusBadge status={step.status} />
                  {step.attempt > 1 ? (
                    <Badge tone="amber">
                      <RefreshCw className="size-3" aria-hidden /> {step.attempt} attempts
                    </Badge>
                  ) : null}
                </div>
                {step.error ? <p className="mt-2 text-sm text-red-700">{step.error}</p> : null}
                <div className="mt-3 grid gap-4 md:grid-cols-2">
                  <div>
                    <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Input
                    </div>
                    <KeyValue data={step.input_json} />
                  </div>
                  <div>
                    <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                      Output
                    </div>
                    <KeyValue data={step.output_json} />
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      </Card>
      {run.approvals.length ? (
        <Card className="mt-6">
          <CardHeader title="Approvals in this run" />
          <ul className="divide-y divide-slate-100">
            {run.approvals.map((a) => (
              <li key={a.id}>
                <Link
                  href={`/approvals/${a.id}`}
                  className="flex flex-wrap items-center gap-3 px-5 py-3 hover:bg-slate-50"
                >
                  <Badge tone={APPROVAL_KIND[a.kind]?.tone ?? "gray"}>
                    {APPROVAL_KIND[a.kind]?.label ?? a.kind}
                  </Badge>
                  <span className="flex-1 text-sm font-medium text-slate-900">{a.title}</span>
                  <StatusBadge status={a.status} />
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </>
  );
}
