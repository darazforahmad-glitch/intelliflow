"use client";

import { ArrowLeft, Map as MapIcon, PencilLine } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { ChatPanel } from "@/components/chat";
import { OpportunityPanel } from "@/components/opportunities";
import { MapLegend, ProcessMapFlow } from "@/components/process-map";
import { StatusBadge } from "@/components/status";
import { StepEditor } from "@/components/step-editor";
import { useToast } from "@/components/toast";
import { Alert, Card, EmptyState, PageHeader, Segmented, Skeleton, Spinner } from "@/components/ui";
import { ApiError, errorMessage } from "@/lib/api";
import { formatDateTime, minutesLabel } from "@/lib/format";
import { useAnswer, useCompleteInterview, useInterview, useProcessMap } from "@/lib/queries";
import { useMembership } from "@/lib/session";

export default function InterviewPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const interview = useInterview(sessionId);
  const answer = useAnswer(sessionId);
  const complete = useCompleteInterview(sessionId);
  const membership = useMembership();
  const toast = useToast();
  const [selectedMapId, setSelectedMapId] = useState<string | null>(null);
  const [view, setView] = useState<"map" | "edit">("map");
  const [clarify, setClarify] = useState<string[] | null>(null);
  const mapId = selectedMapId ?? interview.data?.latest_map_id ?? null;
  const map = useProcessMap(mapId);
  const canEdit = membership?.role === "owner";

  if (interview.isLoading) return <Spinner />;
  if (interview.error || !interview.data) return <Alert tone="error">{errorMessage(interview.error)}</Alert>;
  const session = interview.data;

  async function send(text: string): Promise<boolean> {
    try {
      await answer.mutateAsync(text);
      return true;
    } catch (error) {
      toast(errorMessage(error), "error");
      return false;
    }
  }

  async function done() {
    setClarify(null);
    try {
      const created = await complete.mutateAsync();
      setSelectedMapId(created.id);
      toast("Your process map is ready.");
    } catch (error) {
      if (error instanceof ApiError && error.code === "map_needs_clarification") {
        setClarify((error.details as string[]) ?? []);
        await interview.refetch();
      } else toast(errorMessage(error), "error");
    }
  }

  return (
    <>
      <Link
        href="/flow-mapper"
        className="mb-3 inline-flex min-h-9 items-center gap-1 text-sm font-medium text-slate-600 hover:text-slate-900"
      >
        <ArrowLeft className="size-4" aria-hidden /> All processes
      </Link>
      <PageHeader
        title={session.process_name}
        description={
          map.data
            ? `Map version ${map.data.version} · ${map.data.steps.length} steps · ${minutesLabel(map.data.manual_weekly_minutes)} of manual work per week`
            : "Answer the questions, then press Done to draw the map."
        }
        actions={<StatusBadge status={session.status} />}
      />
      {clarify ? (
        <Alert tone="warning" className="mb-4" title="The AI needs a little more detail">
          Please answer the new question in the chat, then press Done again.
        </Alert>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[minmax(20rem,26rem)_1fr]">
        <ChatPanel
          session={session}
          onSend={send}
          sending={answer.isPending}
          onDone={done}
          completing={complete.isPending}
          canEdit={canEdit}
        />

        <div className="min-w-0 space-y-3">
          {mapId ? (
            <>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <Segmented
                  label="View"
                  value={view}
                  onChange={setView}
                  options={[
                    { value: "map", label: "Flowchart" },
                    ...(canEdit ? [{ value: "edit" as const, label: "Edit steps" }] : []),
                  ]}
                />
                {map.data && map.data.versions.length > 1 ? (
                  <label className="flex items-center gap-2 text-sm text-slate-700">
                    Version
                    <select
                      className="min-h-9 rounded-lg border border-slate-300 px-2"
                      value={map.data.id}
                      onChange={(e) => setSelectedMapId(e.target.value)}
                    >
                      {map.data.versions.map((v) => (
                        <option key={v.id} value={v.id}>
                          v{v.version} · {formatDateTime(v.created_at)}
                          {v.change_note ? ` · ${v.change_note}` : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : null}
              </div>
              {!map.data ? (
                <Skeleton className="h-[560px]" />
              ) : view === "edit" ? (
                <StepEditor
                  key={map.data.id}
                  map={map.data}
                  onSaved={(id) => {
                    setSelectedMapId(id);
                    setView("map");
                  }}
                />
              ) : (
                <>
                  <ProcessMapFlow map={map.data} />
                  <MapLegend />
                  {!map.data.is_latest ? (
                    <Alert tone="info">
                      You are looking at an older version. Edits always start a new version.
                    </Alert>
                  ) : null}
                </>
              )}
            </>
          ) : (
            <Card className="grid h-full min-h-[32rem] place-items-center">
              <EmptyState
                icon={<MapIcon className="size-6" />}
                title="Your process map appears here"
                description="Answer a few questions in the chat. When the AI has enough detail, press “Done — draw my map”."
              />
            </Card>
          )}
          {canEdit && map.data && view === "map" ? (
            <button
              type="button"
              onClick={() => setView("edit")}
              className="inline-flex min-h-9 items-center gap-1.5 text-sm font-medium text-brand-700 hover:underline"
            >
              <PencilLine className="size-4" aria-hidden /> Something wrong? Edit the steps
            </button>
          ) : null}
        </div>
      </div>

      {map.data ? (
        <div className="mt-8">
          <OpportunityPanel map={map.data} canEdit={canEdit && map.data.is_latest} />
        </div>
      ) : null}
    </>
  );
}
