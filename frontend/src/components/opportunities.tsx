"use client";

import clsx from "clsx";
import { Banknote, MessageCircle, Sparkles, Undo2, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { ApiError, errorMessage } from "@/lib/api";
import { minutesLabel } from "@/lib/format";
import { useDismissOpportunity, useGenerateAutomation, useRestoreOpportunity } from "@/lib/queries";
import type { Opportunity, ProcessMap } from "@/lib/types";

import { StatusBadge } from "./status";
import { useToast } from "./toast";
import { Alert, Badge, Button, ButtonLink, Card } from "./ui";

const PROVIDER_LABEL: Record<string, string> = {
  whatsapp: "WhatsApp",
  gmail: "Gmail",
  google_sheets: "Google Sheets",
  webform: "Web form",
};

function OpportunityCard({ opportunity, canEdit }: { opportunity: Opportunity; canEdit: boolean }) {
  const router = useRouter();
  const toast = useToast();
  const generate = useGenerateAutomation();
  const dismiss = useDismissOpportunity();
  const [missing, setMissing] = useState<string[] | null>(null);
  const risky = Number(opportunity.risk) > 0;

  async function automate() {
    setMissing(null);
    try {
      const automation = await generate.mutateAsync(opportunity.id);
      toast(
        automation.status === "validated"
          ? "Automation drafted and validated."
          : "Draft created — a few things need fixing.",
      );
      router.push(`/automations/${automation.id}`);
    } catch (error) {
      if (error instanceof ApiError && error.code === "connections_required") {
        setMissing(
          ((error.details as { missing?: string[] })?.missing ?? []).map((p) => PROVIDER_LABEL[p] ?? p),
        );
      } else toast(errorMessage(error), "error");
    }
  }

  return (
    <Card className="relative p-5">
      <div className="flex items-start gap-3">
        <div
          className={clsx(
            "grid size-10 shrink-0 place-items-center rounded-xl text-lg font-bold",
            opportunity.rank === 1 ? "bg-brand-600 text-white" : "bg-brand-50 text-brand-700",
          )}
        >
          {opportunity.rank}
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold leading-snug text-slate-900">{opportunity.step_title}</h3>
          <p className="mt-0.5 text-sm text-slate-600">
            with <span className="font-medium text-slate-800">{opportunity.template?.name}</span>
            {Number(opportunity.fit) < 1 ? " (partial fit)" : ""}
          </p>
        </div>
        {opportunity.status !== "suggested" ? <StatusBadge status={opportunity.status} /> : null}
      </div>
      <div className="mt-4 grid grid-cols-2 gap-3">
        <div className="rounded-xl bg-saved-50 px-3 py-2">
          <div className="text-xs font-medium text-saved-700">Saves per day</div>
          <div className="text-lg font-bold text-saved-700">
            {minutesLabel(opportunity.minutes_saved_per_day)}
          </div>
        </div>
        <div className="rounded-xl bg-saved-50 px-3 py-2">
          <div className="text-xs font-medium text-saved-700">Saves per week</div>
          <div className="text-lg font-bold text-saved-700">
            {minutesLabel(opportunity.minutes_saved_per_week)}
          </div>
        </div>
      </div>
      <p className="mt-3 text-sm text-slate-700">{opportunity.reason}</p>
      {risky ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {opportunity.reason.includes("customers") ? (
            <Badge tone="blue">
              <MessageCircle className="size-3" aria-hidden /> Approval before messaging
            </Badge>
          ) : null}
          {opportunity.reason.includes("Rs") ? (
            <Badge tone="amber">
              <Banknote className="size-3" aria-hidden /> Approval above amount
            </Badge>
          ) : null}
        </div>
      ) : null}
      {missing ? (
        <Alert tone="warning" className="mt-3" title={`Connect ${missing.join(" and ")} first`}>
          <Link href="/integrations" className="font-semibold underline">
            Open Integrations
          </Link>{" "}
          — sandbox connections are fine for trying it out.
        </Alert>
      ) : null}
      {canEdit ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {opportunity.automation_id ? (
            <ButtonLink href={`/automations/${opportunity.automation_id}`} size="md">
              Open automation
            </ButtonLink>
          ) : (
            <Button icon={<Sparkles className="size-4" />} onClick={automate} loading={generate.isPending}>
              Automate this
            </Button>
          )}
          {opportunity.status === "suggested" ? (
            <Button
              variant="ghost"
              icon={<X className="size-4" />}
              onClick={() => dismiss.mutate(opportunity.id)}
              loading={dismiss.isPending}
            >
              Dismiss
            </Button>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}

export function OpportunityPanel({ map, canEdit }: { map: ProcessMap; canEdit: boolean }) {
  const restore = useRestoreOpportunity();
  const unsupported = map.steps.filter((s) => map.unsupported_steps.includes(s.key));
  return (
    <section aria-labelledby="opps-heading" className="space-y-4">
      <div>
        <h2 id="opps-heading" className="text-lg font-semibold text-slate-900">
          Top automation opportunities
        </h2>
        <p className="text-sm text-slate-600">
          Ranked by weekly time × template fit × safety. Manual work in this process:{" "}
          {minutesLabel(map.manual_weekly_minutes)} a week.
        </p>
      </div>
      {map.opportunities.length ? (
        <div className="grid gap-4 xl:grid-cols-3">
          {map.opportunities.map((o) => (
            <OpportunityCard key={o.id} opportunity={o} canEdit={canEdit} />
          ))}
        </div>
      ) : (
        <Alert tone="info">
          No step matches a template yet. Try describing the repetitive steps in more detail.
        </Alert>
      )}
      {map.other_opportunities.length ? (
        <details className="rounded-2xl border border-slate-200 bg-white p-4">
          <summary className="cursor-pointer text-sm font-semibold text-slate-800">
            More candidates ({map.other_opportunities.length})
          </summary>
          <div className="mt-3 grid gap-4 xl:grid-cols-3">
            {map.other_opportunities.map((o) => (
              <OpportunityCard key={o.id} opportunity={o} canEdit={canEdit} />
            ))}
          </div>
        </details>
      ) : null}
      {unsupported.length ? (
        <p className="text-sm text-slate-600">
          <span className="font-medium text-slate-800">Not yet supported:</span>{" "}
          {unsupported.map((s) => s.title).join(", ")}.
        </p>
      ) : null}
      {map.dismissed_opportunities.length ? (
        <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <span className="font-medium text-slate-800">Dismissed:</span>
          {map.dismissed_opportunities.map((o) => (
            <button
              key={o.id}
              type="button"
              onClick={() => restore.mutate(o.id)}
              className="inline-flex min-h-9 items-center gap-1 rounded-lg px-2 hover:bg-slate-100"
              disabled={!canEdit}
            >
              <Undo2 className="size-3.5" aria-hidden /> {o.step_title}
            </button>
          ))}
        </div>
      ) : null}
    </section>
  );
}
