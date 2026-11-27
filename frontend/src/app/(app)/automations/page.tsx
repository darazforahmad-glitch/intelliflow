"use client";

import { Bot, Plug } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { StatusBadge } from "@/components/status";
import { useToast } from "@/components/toast";
import { Alert, Badge, Button, Card, CardHeader, EmptyState, PageHeader, Spinner } from "@/components/ui";
import { ApiError, errorMessage } from "@/lib/api";
import { minutesLabel, timeAgo, TRIGGER_LABELS } from "@/lib/format";
import { useAutomations, useCreateFromTemplate, useTemplates } from "@/lib/queries";
import { useMembership } from "@/lib/session";

const PROVIDER_LABEL: Record<string, string> = {
  whatsapp: "WhatsApp",
  gmail: "Gmail",
  google_sheets: "Google Sheets",
  webform: "Web form",
};

export default function AutomationsPage() {
  const automations = useAutomations();
  const templates = useTemplates();
  const create = useCreateFromTemplate();
  const membership = useMembership();
  const router = useRouter();
  const toast = useToast();
  const [missing, setMissing] = useState<{ code: string; providers: string[] } | null>(null);
  const isOwner = membership?.role === "owner";

  async function applyTemplate(code: string) {
    setMissing(null);
    try {
      const automation = await create.mutateAsync(code);
      router.push(`/automations/${automation.id}`);
    } catch (error) {
      if (error instanceof ApiError && error.code === "connections_required") {
        setMissing({
          code,
          providers: ((error.details as { missing?: string[] })?.missing ?? []).map(
            (p) => PROVIDER_LABEL[p] ?? p,
          ),
        });
      } else toast(errorMessage(error), "error");
    }
  }

  return (
    <>
      <PageHeader
        title="Automations"
        description="Each automation is built only from tested blocks, validated, and tested before it can run."
      />
      <Card>
        <CardHeader title="Your automations" />
        {automations.isLoading ? (
          <Spinner />
        ) : !automations.data?.length ? (
          <EmptyState
            icon={<Bot className="size-6" />}
            title="No automations yet"
            description="Create one from an opportunity in the Flow Mapper, or start from a template below."
          />
        ) : (
          <ul className="divide-y divide-slate-100">
            {automations.data.map((a) => (
              <li key={a.id}>
                <Link
                  href={`/automations/${a.id}`}
                  className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-4 hover:bg-slate-50"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium text-slate-900">{a.name}</span>
                      <StatusBadge status={a.status} />
                      {a.auto_send ? <Badge tone="purple">Auto-send</Badge> : null}
                    </div>
                    <div className="mt-0.5 text-sm text-slate-600">
                      {TRIGGER_LABELS[a.trigger_type ?? ""] ?? "Not set"} · v{a.version_no} ·{" "}
                      {a.template_name ?? "Custom"}
                    </div>
                    {a.status_reason && (a.status === "paused" || a.status === "error") ? (
                      <div className="mt-1 text-sm text-red-700">{a.status_reason}</div>
                    ) : null}
                  </div>
                  <div className="grid grid-cols-3 gap-6 text-right text-sm">
                    <div>
                      <div className="font-semibold tabular-nums text-slate-900">{a.stats.runs_total}</div>
                      <div className="text-xs text-slate-600">runs</div>
                    </div>
                    <div>
                      <div className="font-semibold tabular-nums text-saved-700">
                        {minutesLabel(a.stats.minutes_saved)}
                      </div>
                      <div className="text-xs text-slate-600">saved</div>
                    </div>
                    <div>
                      <div className="font-semibold text-slate-900">{timeAgo(a.stats.last_run_at)}</div>
                      <div className="text-xs text-slate-600">last run</div>
                    </div>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <section className="mt-8" aria-labelledby="templates-heading">
        <h2 id="templates-heading" className="text-lg font-semibold text-slate-900">
          Start from a template
        </h2>
        <p className="text-sm text-slate-600">
          No interview needed. Every template is a tested workflow you can adjust.
        </p>
        {missing ? (
          <Alert tone="warning" className="mt-4" title={`Connect ${missing.providers.join(" and ")} first`}>
            <Link href="/integrations" className="font-semibold underline">
              Open Integrations
            </Link>{" "}
            — sandbox connections let you try templates safely.
          </Alert>
        ) : null}
        <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {(templates.data ?? []).map((t) => (
            <Card key={t.code} className="flex flex-col p-5">
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-semibold text-slate-900">{t.name}</h3>
                {t.category ? <Badge>{t.category}</Badge> : null}
              </div>
              <p className="mt-1 flex-1 text-sm text-slate-600">{t.description}</p>
              <div className="mt-3 text-xs text-slate-600">
                <span className="font-medium text-slate-800">When:</span>{" "}
                {TRIGGER_LABELS[t.trigger_type] ?? t.trigger_type}
              </div>
              <ol className="mt-2 flex flex-wrap gap-1 text-xs text-slate-700">
                {t.steps.map((step, i) => (
                  <li key={`${t.code}-${i}`} className="rounded-md bg-slate-100 px-1.5 py-0.5">
                    {step}
                  </li>
                ))}
              </ol>
              <div className="mt-3 flex flex-wrap items-center gap-1.5">
                <Plug className="size-3.5 text-slate-500" aria-hidden />
                {t.required_connections.map((p) => (
                  <Badge key={p} tone="blue">
                    {PROVIDER_LABEL[p] ?? p}
                  </Badge>
                ))}
              </div>
              {isOwner ? (
                <Button
                  className="mt-4"
                  variant="secondary"
                  onClick={() => applyTemplate(t.code)}
                  loading={create.isPending && create.variables === t.code}
                >
                  Use this template
                </Button>
              ) : null}
            </Card>
          ))}
        </div>
      </section>
    </>
  );
}
