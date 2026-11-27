"use client";

import clsx from "clsx";
import { Archive, ArrowLeft, Braces, FlaskConical, Pause, Play, RotateCcw, Save, Wand2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";

import {
  BlockEditor,
  BlockList,
  GateChecklist,
  issuesForBlock,
  TraceList,
  TriggerEditor,
  useSampleFor,
} from "@/components/builder";
import { StatusBadge } from "@/components/status";
import { useToast } from "@/components/toast";
import {
  Alert,
  Badge,
  Button,
  Card,
  ConfirmButton,
  Input,
  PageHeader,
  Segmented,
  Spinner,
  Textarea,
} from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { formatDateTime, minutesLabel, timeAgo, TRIGGER_LABELS } from "@/lib/format";
import {
  useAutoSend,
  useAutomation,
  useAutomationAction,
  useRollback,
  useRuns,
  useSaveDefinition,
  useTestAutomation,
  useValidateDefinition,
} from "@/lib/queries";
import { useMembership } from "@/lib/session";
import type { TestResult, ValidationIssue, WorkflowDefinition } from "@/lib/types";

type Tab = "steps" | "test" | "runs" | "versions";

function TestPanel({
  automationId,
  triggerType,
  canRun,
}: {
  automationId: string;
  triggerType: string;
  canRun: boolean;
}) {
  const defaults = useSampleFor(triggerType);
  const test = useTestAutomation(automationId);
  const [sample, setSample] = useState<Record<string, unknown>>(defaults);
  const [fieldsText, setFieldsText] = useState(
    JSON.stringify((defaults as { fields?: unknown }).fields ?? {}, null, 2),
  );
  const [result, setResult] = useState<TestResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setError(null);
    try {
      const body =
        triggerType === "webform.submitted" ? { fields: JSON.parse(fieldsText) as unknown } : sample;
      setResult(await test.mutateAsync(body));
    } catch (err) {
      setError(err instanceof SyntaxError ? "The form fields must be valid JSON." : errorMessage(err));
    }
  }

  return (
    <div className="grid gap-6 2xl:grid-cols-[22rem_1fr]">
      <Card className="h-fit p-5">
        <h2 className="font-semibold text-slate-900">Test with a sample</h2>
        <p className="mt-1 text-sm text-slate-600">
          Runs every step in sandbox mode: approvals are auto-approved and nothing is sent to real customers.
        </p>
        <div className="mt-4 space-y-3">
          {triggerType === "whatsapp.message_received" ? (
            <>
              <Input
                label="Customer name"
                value={String(sample.name ?? "")}
                onChange={(e) => setSample({ ...sample, name: e.target.value })}
              />
              <Textarea
                label="WhatsApp message"
                rows={5}
                value={String(sample.text ?? "")}
                onChange={(e) => setSample({ ...sample, text: e.target.value })}
              />
            </>
          ) : null}
          {triggerType === "gmail.message_received" ? (
            <>
              <Input
                label="From"
                value={String(sample.from ?? "")}
                onChange={(e) => setSample({ ...sample, from: e.target.value })}
              />
              <Input
                label="Subject"
                value={String(sample.subject ?? "")}
                onChange={(e) => setSample({ ...sample, subject: e.target.value })}
              />
              <Textarea
                label="Body"
                rows={5}
                value={String(sample.body ?? "")}
                onChange={(e) => setSample({ ...sample, body: e.target.value })}
              />
            </>
          ) : null}
          {triggerType === "webform.submitted" ? (
            <Textarea
              label="Form fields (JSON)"
              rows={7}
              className="font-mono text-xs"
              value={fieldsText}
              onChange={(e) => setFieldsText(e.target.value)}
            />
          ) : null}
          {triggerType.startsWith("schedule") ? (
            <p className="text-sm text-slate-600">Scheduled automations need no sample.</p>
          ) : null}
          <Button
            className="w-full"
            icon={<FlaskConical className="size-4" />}
            onClick={run}
            loading={test.isPending}
            disabled={!canRun}
          >
            Run test
          </Button>
          {!canRun ? <p className="text-xs text-slate-600">Fix the problems in the steps first.</p> : null}
        </div>
      </Card>
      <div className="min-w-0 space-y-4">
        {error ? <Alert tone="error">{error}</Alert> : null}
        {result ? (
          <>
            <Alert
              tone={result.passed ? "success" : result.run.status === "succeeded" ? "warning" : "error"}
              title={result.passed ? "Test passed" : "Test did not pass"}
            >
              {result.message}
            </Alert>
            {result.sandbox_records.length ? (
              <Card className="p-4">
                <h3 className="text-sm font-semibold text-slate-900">What would have happened</h3>
                <ul className="mt-2 space-y-1.5 text-sm text-slate-700">
                  {result.sandbox_records.map((r) => (
                    <li key={r.ref}>
                      <Badge tone="blue">{r.provider.replace("_", " ")}</Badge>{" "}
                      {r.operation.replace("_", " ")}:{" "}
                      <span className="text-slate-600">
                        {String(
                          r.payload.text ?? r.payload.sheet ?? r.payload.subject ?? JSON.stringify(r.payload),
                        ).slice(0, 160)}
                      </span>
                    </li>
                  ))}
                </ul>
              </Card>
            ) : null}
            <TraceList steps={result.steps} />
          </>
        ) : (
          <Card className="grid min-h-64 place-items-center p-6 text-center text-sm text-slate-600">
            Run a test to see the input and output of every step.
          </Card>
        )}
      </div>
    </div>
  );
}

export default function AutomationBuilderPage() {
  const { id } = useParams<{ id: string }>();
  const { data: automation, isLoading, error } = useAutomation(id);
  const membership = useMembership();
  const isOwner = membership?.role === "owner";
  const toast = useToast();
  const save = useSaveDefinition(id);
  const validate = useValidateDefinition(id);
  const action = useAutomationAction(id);
  const rollback = useRollback(id);
  const autoSend = useAutoSend(id);
  const runs = useRuns({ automation_id: id });
  const [tab, setTab] = useState<Tab>("steps");
  const [draft, setDraft] = useState<WorkflowDefinition | null>(null);
  const [selected, setSelected] = useState("__trigger");
  const [checkIssues, setCheckIssues] = useState<ValidationIssue[] | null>(null);
  const [jsonMode, setJsonMode] = useState(false);
  const [jsonText, setJsonText] = useState("");
  const [draftVersionId, setDraftVersionId] = useState<string | null>(null);

  // Reset the editor whenever a new version is loaded (derived during render, not in an effect).
  if (automation?.current_version && automation.current_version.id !== draftVersionId) {
    setDraftVersionId(automation.current_version.id);
    setDraft(structuredClone(automation.current_version.definition_json));
    setCheckIssues(null);
  }

  const dirty = useMemo(
    () =>
      Boolean(
        draft &&
        automation?.current_version &&
        JSON.stringify(draft) !== JSON.stringify(automation.current_version.definition_json),
      ),
    [draft, automation],
  );
  if (isLoading || !draft) return error ? <Alert tone="error">{errorMessage(error)}</Alert> : <Spinner />;
  if (!automation?.current_version) return <Alert tone="error">This automation has no version.</Alert>;

  const version = automation.current_version;
  const issues = checkIssues ?? version.validation_errors;
  const block = draft.blocks.find((b) => b.key === selected);
  const allConnected = automation.connections.every((c) => c.connected);
  const canActivate =
    version.validated &&
    version.test_passed &&
    allConnected &&
    !dirty &&
    !["active", "archived"].includes(automation.status);

  async function onSave() {
    try {
      const updated = await save.mutateAsync(
        jsonMode ? (JSON.parse(jsonText) as WorkflowDefinition) : draft!,
      );
      const errors = updated.current_version?.validation_errors ?? [];
      toast(
        errors.length
          ? `Saved as version ${updated.current_version?.version_no} — ${errors.length} problem(s) to fix.`
          : `Saved as version ${updated.current_version?.version_no}. Run a test next.`,
        errors.length ? "info" : "success",
      );
      setJsonMode(false);
    } catch (err) {
      toast(err instanceof SyntaxError ? "The JSON is not valid." : errorMessage(err), "error");
    }
  }

  async function onCheck() {
    const result = await validate.mutateAsync(draft!);
    setCheckIssues(result.issues);
    toast(
      result.valid ? "No problems found." : `${result.issues.length} problem(s) found.`,
      result.valid ? "success" : "info",
    );
  }

  async function run(kind: "activate" | "pause" | "archive" | "repair", message: string) {
    try {
      await action.mutateAsync(kind);
      toast(message);
    } catch (err) {
      toast(errorMessage(err), "error");
    }
  }

  return (
    <>
      <Link
        href="/automations"
        className="mb-3 inline-flex min-h-9 items-center gap-1 text-sm font-medium text-slate-600 hover:text-slate-900"
      >
        <ArrowLeft className="size-4" aria-hidden /> Automations
      </Link>
      <PageHeader
        title={automation.name}
        description={`${TRIGGER_LABELS[draft.trigger.type] ?? draft.trigger.type} · version ${version.version_no} · saves about ${minutesLabel(automation.estimated_minutes_per_run)} per run`}
        actions={
          <>
            <StatusBadge status={automation.status} />
            {isOwner && (automation.status === "active" || automation.status === "error") ? (
              <Button
                variant="secondary"
                icon={<Pause className="size-4" />}
                onClick={() => run("pause", "Automation paused.")}
                loading={action.isPending}
              >
                Pause
              </Button>
            ) : null}
            {isOwner && automation.status !== "active" && automation.status !== "archived" ? (
              <Button
                variant="success"
                icon={<Play className="size-4" />}
                disabled={!canActivate}
                onClick={() => run("activate", "Automation is live.")}
                loading={action.isPending}
              >
                Activate
              </Button>
            ) : null}
          </>
        }
      />

      {automation.status_reason && ["paused", "error"].includes(automation.status) ? (
        <Alert
          tone={automation.status === "error" ? "error" : "warning"}
          className="mb-4"
          title={automation.status === "error" ? "Paused because of a problem" : "Paused"}
        >
          {automation.status_reason}
        </Alert>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="min-w-0">
          <Segmented
            label="Builder sections"
            value={tab}
            onChange={setTab}
            options={[
              { value: "steps", label: "Steps" },
              { value: "test", label: "Test" },
              { value: "runs", label: `Runs (${automation.stats.runs_total})` },
              { value: "versions", label: `Versions (${automation.versions.length})` },
            ]}
          />
          <div className="mt-4">
            {tab === "steps" ? (
              <>
                {issues.length ? (
                  <Alert
                    tone="error"
                    className="mb-4"
                    title={`${issues.length} problem(s) must be fixed before testing`}
                  >
                    <ul className="mt-1 list-disc space-y-0.5 pl-5">
                      {issues.map((issue) => (
                        <li key={issue.message}>{issue.message}</li>
                      ))}
                    </ul>
                    {isOwner && !version.validated && !dirty ? (
                      <Button
                        className="mt-3"
                        variant="secondary"
                        icon={<Wand2 className="size-4" />}
                        onClick={() => run("repair", "The AI fixed what it could.")}
                        loading={action.isPending}
                      >
                        Fix automatically
                      </Button>
                    ) : null}
                  </Alert>
                ) : null}
                {jsonMode ? (
                  <Card className="p-4">
                    <Textarea
                      label="Workflow definition (advanced)"
                      rows={24}
                      className="font-mono text-xs"
                      spellCheck={false}
                      value={jsonText}
                      onChange={(e) => setJsonText(e.target.value)}
                    />
                  </Card>
                ) : (
                  <div className="grid gap-4 lg:grid-cols-[16rem_minmax(0,1fr)]">
                    <BlockList
                      definition={draft}
                      selected={selected}
                      onSelect={setSelected}
                      issues={issues}
                    />
                    <Card className="min-w-0 p-5">
                      {selected === "__trigger" ? (
                        <TriggerEditor
                          trigger={draft.trigger}
                          onChange={(trigger) => setDraft({ ...draft, trigger })}
                        />
                      ) : block ? (
                        <BlockEditor
                          key={block.key}
                          block={block}
                          issues={issuesForBlock(issues, block.key)}
                          onChange={(next) =>
                            setDraft({
                              ...draft,
                              blocks: draft.blocks.map((b) => (b.key === block.key ? next : b)),
                            })
                          }
                        />
                      ) : (
                        <p className="text-sm text-slate-600">Select a step to edit it.</p>
                      )}
                    </Card>
                  </div>
                )}
                {isOwner ? (
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Button
                      icon={<Save className="size-4" />}
                      onClick={onSave}
                      loading={save.isPending}
                      disabled={!dirty && !jsonMode}
                    >
                      Save as version {automation.versions.length + 1}
                    </Button>
                    <Button variant="secondary" onClick={onCheck} loading={validate.isPending}>
                      Check for problems
                    </Button>
                    <Button
                      variant="ghost"
                      icon={<Braces className="size-4" />}
                      onClick={() => {
                        setJsonText(JSON.stringify(draft, null, 2));
                        setJsonMode((v) => !v);
                      }}
                    >
                      {jsonMode ? "Back to the editor" : "Edit as JSON"}
                    </Button>
                    {dirty ? (
                      <Button
                        variant="ghost"
                        onClick={() => setDraft(structuredClone(version.definition_json))}
                      >
                        Discard changes
                      </Button>
                    ) : null}
                  </div>
                ) : null}
              </>
            ) : null}
            {tab === "test" ? (
              <TestPanel
                automationId={id}
                triggerType={version.definition_json.trigger.type}
                canRun={version.validated && isOwner}
              />
            ) : null}
            {tab === "runs" ? (
              <Card>
                <ul className="divide-y divide-slate-100">
                  {(runs.data ?? []).map((r) => (
                    <li key={r.id}>
                      <Link
                        href={`/runs/${r.id}`}
                        className="flex flex-wrap items-center gap-3 px-5 py-3 hover:bg-slate-50"
                      >
                        <StatusBadge status={r.status} />
                        <span className="min-w-0 flex-1 truncate text-sm text-slate-700">
                          {r.error ?? r.summary ?? "—"}
                        </span>
                        <span className="text-sm text-saved-700">
                          {Number(r.minutes_saved) ? `+${minutesLabel(r.minutes_saved)}` : ""}
                        </span>
                        <span className="text-xs text-slate-500">{timeAgo(r.created_at)}</span>
                      </Link>
                    </li>
                  ))}
                  {runs.data && !runs.data.length ? (
                    <li className="px-5 py-8 text-center text-sm text-slate-600">No live runs yet.</li>
                  ) : null}
                </ul>
              </Card>
            ) : null}
            {tab === "versions" ? (
              <Card>
                <ul className="divide-y divide-slate-100">
                  {automation.versions.map((v) => (
                    <li key={v.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
                      <span className="font-semibold text-slate-900">v{v.version_no}</span>
                      <Badge>{v.source}</Badge>
                      {v.validated ? (
                        <Badge tone="blue">validated</Badge>
                      ) : (
                        <Badge tone="red">has problems</Badge>
                      )}
                      {v.test_passed ? <Badge tone="purple">tested</Badge> : null}
                      <span className="flex-1 text-sm text-slate-600">{formatDateTime(v.created_at)}</span>
                      {v.version_no === version.version_no ? (
                        <Badge tone="green">current</Badge>
                      ) : isOwner ? (
                        <ConfirmButton
                          variant="primary"
                          size="sm"
                          icon={<RotateCcw className="size-4" />}
                          title={`Roll back to version ${v.version_no}?`}
                          message="This creates a new version with the same steps. You will need to activate it again."
                          confirmLabel="Roll back"
                          onConfirm={async () => {
                            await rollback.mutateAsync(v.version_no);
                            toast(`Rolled back to version ${v.version_no}.`);
                          }}
                        >
                          Roll back
                        </ConfirmButton>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </Card>
            ) : null}
          </div>
        </div>

        <aside className="space-y-4">
          <Card className="p-5">
            <h2 className="font-semibold text-slate-900">Ready to go live?</h2>
            <div className="mt-3">
              <GateChecklist
                items={[
                  { label: "Steps are valid", ok: version.validated },
                  { label: "A test passed", ok: version.test_passed },
                  { label: "Apps are connected", ok: allConnected },
                  { label: "Changes are saved", ok: !dirty },
                ]}
              />
            </div>
            <ul className="mt-4 space-y-1.5 border-t border-slate-100 pt-3 text-sm">
              {automation.connections.map((c) => (
                <li key={c.provider} className="flex items-center justify-between">
                  <span className="text-slate-700">{c.label}</span>
                  {c.connected ? (
                    <Badge tone={c.mode === "sandbox" ? "amber" : "green"}>
                      {c.mode === "sandbox" ? "sandbox" : "live"}
                    </Badge>
                  ) : (
                    <Link href="/integrations" className="text-xs font-semibold text-red-700 underline">
                      connect
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          </Card>
          <Card className="p-5">
            <h2 className="font-semibold text-slate-900">Auto-send</h2>
            <p className="mt-1 text-sm text-slate-600">
              Messages to customers wait for approval. After {automation.auto_send_threshold} approvals in a
              row without edits you can let them send automatically.
            </p>
            <div
              className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100"
              role="progressbar"
              aria-valuenow={automation.clean_approvals}
              aria-valuemax={automation.auto_send_threshold}
              aria-label="Clean approvals"
            >
              <div
                className="h-full rounded-full bg-purple-500"
                style={{
                  width: `${Math.min(100, (automation.clean_approvals / automation.auto_send_threshold) * 100)}%`,
                }}
              />
            </div>
            <div className="mt-1 text-xs text-slate-600">
              {automation.clean_approvals} / {automation.auto_send_threshold} clean approvals
            </div>
            {isOwner ? (
              <Button
                className="mt-3 w-full"
                variant={automation.auto_send ? "secondary" : "primary"}
                disabled={
                  !automation.auto_send && automation.clean_approvals < automation.auto_send_threshold
                }
                onClick={async () => {
                  try {
                    await autoSend.mutateAsync(!automation.auto_send);
                  } catch (err) {
                    toast(errorMessage(err), "error");
                  }
                }}
              >
                {automation.auto_send ? "Turn auto-send off" : "Turn auto-send on"}
              </Button>
            ) : null}
          </Card>
          <Card className={clsx("p-5", !isOwner && "hidden")}>
            <h2 className="font-semibold text-slate-900">Archive</h2>
            <p className="mt-1 text-sm text-slate-600">
              Stops the automation for good. Runs and versions are kept.
            </p>
            <div className="mt-3">
              <ConfirmButton
                icon={<Archive className="size-4" />}
                title="Archive this automation?"
                message="It will stop running and cannot be activated again."
                confirmLabel="Archive"
                onConfirm={() => run("archive", "Automation archived.")}
              >
                Archive
              </ConfirmButton>
            </div>
          </Card>
        </aside>
      </div>
    </>
  );
}
