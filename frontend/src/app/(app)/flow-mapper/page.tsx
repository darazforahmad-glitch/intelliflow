"use client";

import { ChevronRight, Sparkles, Workflow } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { StatusBadge } from "@/components/status";
import { Alert, Button, Card, CardHeader, EmptyState, Input, PageHeader, Spinner } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { formatDate, minutesLabel } from "@/lib/format";
import { useInterviews, useProcessMaps, useStartInterview } from "@/lib/queries";
import { useMembership } from "@/lib/session";

const SUGGESTIONS = ["Order process", "Payment collection", "Customer questions", "Delivery and courier"];

function NewInterview() {
  const router = useRouter();
  const autoFocus = useSearchParams().get("new") === "1";
  const start = useStartInterview();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event?: FormEvent) {
    event?.preventDefault();
    if (name.trim().length < 2) return setError("Give the process a short name, e.g. “Order process”.");
    setError(null);
    try {
      const session = await start.mutateAsync({ process_name: name.trim() });
      router.push(`/flow-mapper/${session.id}`);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Card className="p-5 sm:p-6">
      <div className="flex items-start gap-4">
        <div className="hidden rounded-2xl bg-brand-50 p-3 text-brand-600 sm:block">
          <Sparkles className="size-6" aria-hidden />
        </div>
        <form onSubmit={onSubmit} className="flex-1 space-y-3">
          <h2 className="text-lg font-semibold text-slate-900">Map a new process</h2>
          <p className="text-sm text-slate-600">
            Name one process. The AI will ask a few short questions — answer in English, Urdu or Roman Urdu,
            by text or voice.
          </p>
          {error ? <Alert tone="error">{error}</Alert> : null}
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="flex-1">
              <Input
                label="Process name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Order process"
                autoFocus={autoFocus}
                maxLength={120}
              />
            </div>
            <Button type="submit" loading={start.isPending}>
              Start interview
            </Button>
          </div>
          <div className="flex flex-wrap gap-2">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setName(s)}
                className="min-h-9 rounded-full border border-slate-300 px-3 text-sm text-slate-700 hover:border-brand-400 hover:text-brand-700"
              >
                {s}
              </button>
            ))}
          </div>
        </form>
      </div>
    </Card>
  );
}

export default function FlowMapperPage() {
  const interviews = useInterviews();
  const maps = useProcessMaps();
  const membership = useMembership();
  const mapBySession = new Map((maps.data ?? []).map((m) => [m.session_id, m]));

  return (
    <>
      <PageHeader
        title="Flow Mapper"
        description="Interview → process map → ranked automation opportunities."
      />
      {membership?.role === "owner" ? (
        <Suspense>
          <NewInterview />
        </Suspense>
      ) : null}
      <Card className="mt-6">
        <CardHeader title="Your processes" />
        {interviews.isLoading ? (
          <Spinner />
        ) : !interviews.data?.length ? (
          <EmptyState
            icon={<Workflow className="size-6" />}
            title="No processes mapped yet"
            description="Start with the process that takes most of your day, such as taking orders."
          />
        ) : (
          <ul className="divide-y divide-slate-100">
            {interviews.data.map((interview) => {
              const map = mapBySession.get(interview.id);
              return (
                <li key={interview.id}>
                  <Link
                    href={`/flow-mapper/${interview.id}`}
                    className="flex items-center gap-4 px-5 py-4 hover:bg-slate-50"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium text-slate-900">{interview.process_name}</span>
                        <StatusBadge status={interview.status} />
                        {interview.latest_version ? (
                          <span className="text-xs text-slate-600">map v{interview.latest_version}</span>
                        ) : null}
                      </div>
                      <div className="mt-0.5 text-sm text-slate-600">
                        Started {formatDate(interview.started_at)}
                        {map
                          ? ` · ${map.step_count} steps · ${minutesLabel(map.manual_weekly_minutes)} of manual work a week`
                          : ""}
                        {map?.top_opportunity ? ` · top opportunity: ${map.top_opportunity}` : ""}
                      </div>
                    </div>
                    <ChevronRight className="size-5 text-slate-400" aria-hidden />
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </>
  );
}
