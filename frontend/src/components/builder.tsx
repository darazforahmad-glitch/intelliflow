"use client";

import clsx from "clsx";
import {
  CircleAlert,
  CircleCheck,
  Filter,
  Play,
  Plus,
  Radio,
  ShieldCheck,
  Sparkles,
  Trash2,
  Zap,
} from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";

import { TRIGGER_LABELS } from "@/lib/format";
import { useConnectorCatalog } from "@/lib/queries";
import type { Block, ExtractField, Trigger, ValidationIssue, WorkflowDefinition } from "@/lib/types";

import { Badge, Button, Input, KeyValue, Select, Textarea } from "./ui";

export const BLOCK_META: Record<Block["type"], { label: string; icon: ReactNode; tone: string }> = {
  "ai.classify": {
    label: "AI: sort message",
    icon: <Sparkles className="size-4" />,
    tone: "bg-violet-50 text-violet-700",
  },
  "ai.extract": {
    label: "AI: read details",
    icon: <Sparkles className="size-4" />,
    tone: "bg-violet-50 text-violet-700",
  },
  "ai.draft_reply": {
    label: "AI: draft reply",
    icon: <Sparkles className="size-4" />,
    tone: "bg-violet-50 text-violet-700",
  },
  "ai.summarize": {
    label: "AI: summarise",
    icon: <Sparkles className="size-4" />,
    tone: "bg-violet-50 text-violet-700",
  },
  condition: { label: "Check", icon: <Filter className="size-4" />, tone: "bg-sky-50 text-sky-700" },
  approval: {
    label: "Approval",
    icon: <ShieldCheck className="size-4" />,
    tone: "bg-amber-50 text-amber-700",
  },
  action: { label: "Action", icon: <Zap className="size-4" />, tone: "bg-emerald-50 text-emerald-700" },
};

export function issuesForBlock(issues: ValidationIssue[], key: string) {
  return issues.filter((i) => i.block === key);
}

/* ------------------------------------------------------------------ step list */
export function BlockList({
  definition,
  selected,
  onSelect,
  issues,
}: {
  definition: WorkflowDefinition;
  selected: string;
  onSelect: (key: string) => void;
  issues: ValidationIssue[];
}) {
  const triggerIssues = issues.filter((i) => i.path[0] === "trigger");
  return (
    <ol className="space-y-2" aria-label="Automation steps">
      <li>
        <button
          type="button"
          onClick={() => onSelect("__trigger")}
          aria-current={selected === "__trigger" ? "step" : undefined}
          className={clsx(
            "flex min-h-14 w-full items-center gap-3 rounded-xl border px-3 text-left",
            selected === "__trigger"
              ? "border-brand-500 bg-brand-50"
              : "border-slate-200 bg-white hover:border-slate-300",
          )}
        >
          <span className="grid size-8 place-items-center rounded-lg bg-slate-900 text-white">
            <Radio className="size-4" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block text-xs font-semibold uppercase tracking-wide text-slate-500">When</span>
            <span className="block truncate text-sm font-medium text-slate-900">
              {TRIGGER_LABELS[definition.trigger.type] ?? definition.trigger.type}
            </span>
          </span>
          {triggerIssues.length ? (
            <CircleAlert className="size-4 text-red-600" aria-label="Has problems" />
          ) : null}
        </button>
      </li>
      {definition.blocks.map((block, index) => {
        const meta = BLOCK_META[block.type] ?? BLOCK_META.action;
        const problems = issuesForBlock(issues, block.key);
        return (
          <li key={`${block.key}-${index}`}>
            <button
              type="button"
              onClick={() => onSelect(block.key)}
              aria-current={selected === block.key ? "step" : undefined}
              className={clsx(
                "flex min-h-14 w-full items-center gap-3 rounded-xl border px-3 text-left",
                selected === block.key
                  ? "border-brand-500 bg-brand-50"
                  : "border-slate-200 bg-white hover:border-slate-300",
              )}
            >
              <span className={clsx("grid size-8 shrink-0 place-items-center rounded-lg", meta.tone)}>
                {meta.icon}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-xs font-semibold uppercase tracking-wide text-slate-500">
                  {index + 1}. {meta.label}
                  {block.type === "approval" && block.kind ? ` · ${block.kind.replace("_", " ")}` : ""}
                </span>
                <span className="block truncate text-sm font-medium text-slate-900">
                  {block.title || block.key}
                </span>
              </span>
              {problems.length ? (
                <CircleAlert className="size-4 shrink-0 text-red-600" aria-label="Has problems" />
              ) : null}
            </button>
          </li>
        );
      })}
    </ol>
  );
}

/* ------------------------------------------------------------------ JSON helper */
function JsonField({
  label,
  value,
  onChange,
  hint,
}: {
  label: string;
  value: unknown;
  onChange: (v: Record<string, unknown>) => void;
  hint?: string;
}) {
  const [text, setText] = useState(() => JSON.stringify(value ?? {}, null, 2));
  const [error, setError] = useState<string | undefined>();
  return (
    <Textarea
      label={label}
      hint={hint}
      error={error}
      rows={Math.min(14, text.split("\n").length + 1)}
      className="font-mono text-xs"
      value={text}
      spellCheck={false}
      onChange={(e) => {
        setText(e.target.value);
        try {
          const parsed = JSON.parse(e.target.value) as unknown;
          if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed))
            throw new Error("not an object");
          setError(undefined);
          onChange(parsed as Record<string, unknown>);
        } catch {
          setError('This must be valid JSON, e.g. {"sheet": "Orders"}.');
        }
      }}
    />
  );
}

/* ------------------------------------------------------------------ editors */
function FieldsEditor({
  fields,
  onChange,
}: {
  fields: ExtractField[];
  onChange: (f: ExtractField[]) => void;
}) {
  const update = (i: number, patch: Partial<ExtractField>) =>
    onChange(fields.map((f, j) => (j === i ? { ...f, ...patch } : f)));
  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-medium text-slate-800">Details to read</legend>
      {fields.map((field, i) => (
        <div key={i} className="grid grid-cols-[minmax(0,1fr)_6.5rem_auto_auto] items-center gap-2">
          <input
            aria-label="Field name"
            className="min-h-11 w-full min-w-0 rounded-lg border border-slate-300 px-2 text-sm"
            value={field.name}
            onChange={(e) => update(i, { name: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_") })}
          />
          <select
            aria-label="Field type"
            className="min-h-11 w-full min-w-0 rounded-lg border border-slate-300 px-2 text-sm"
            value={field.type}
            onChange={(e) => update(i, { type: e.target.value as ExtractField["type"] })}
          >
            <option value="string">Text</option>
            <option value="number">Number</option>
            <option value="integer">Whole number</option>
            <option value="boolean">Yes/no</option>
          </select>
          <label className="flex items-center gap-1 text-xs text-slate-700">
            <input
              type="checkbox"
              checked={Boolean(field.required)}
              onChange={(e) => update(i, { required: e.target.checked })}
            />{" "}
            Required
          </label>
          <button
            type="button"
            className="grid size-9 place-items-center rounded-lg text-red-600 hover:bg-red-50"
            aria-label={`Remove ${field.name}`}
            onClick={() => onChange(fields.filter((_, j) => j !== i))}
          >
            <Trash2 className="size-4" />
          </button>
        </div>
      ))}
      <Button
        variant="ghost"
        size="sm"
        icon={<Plus className="size-4" />}
        onClick={() => onChange([...fields, { name: "new_field", type: "string" }])}
      >
        Add detail
      </Button>
    </fieldset>
  );
}

function ActionFields({
  connector,
  operation,
  params,
  onChange,
  customerOnly,
}: {
  connector?: string;
  operation?: string;
  params?: Record<string, unknown>;
  onChange: (patch: { connector?: string; operation?: string; params?: Record<string, unknown> }) => void;
  customerOnly?: boolean;
}) {
  const catalog = useConnectorCatalog();
  const providers = (catalog.data ?? []).filter((c) => c.operations.length);
  const ops = providers.find((c) => c.provider === connector)?.operations ?? [];
  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Select label="App" value={connector ?? ""} onChange={(e) => onChange({ connector: e.target.value })}>
          {providers.map((c) => (
            <option key={c.provider} value={c.provider}>
              {c.label}
            </option>
          ))}
        </Select>
        <Select
          label="Do this"
          value={operation ?? ""}
          onChange={(e) => onChange({ operation: e.target.value })}
        >
          {ops.map((op) => (
            <option key={op.name} value={op.name} disabled={customerOnly === false && op.customer_message}>
              {op.label}
              {op.customer_message ? " (to customer)" : ""}
            </option>
          ))}
        </Select>
      </div>
      <JsonField
        key={`${connector}-${operation}`}
        label="Settings"
        value={params}
        onChange={(p) => onChange({ params: p })}
        hint="Use {{step_key.field}} to insert values from earlier steps, e.g. {{details.customer_name}}."
      />
    </div>
  );
}

export function TriggerEditor({ trigger, onChange }: { trigger: Trigger; onChange: (t: Trigger) => void }) {
  return (
    <div className="space-y-4">
      <Select
        label="Start this automation when…"
        value={trigger.type}
        onChange={(e) => onChange({ type: e.target.value })}
      >
        {Object.entries(TRIGGER_LABELS)
          .filter(([type]) => type !== "manual")
          .map(([type, label]) => (
            <option key={type} value={type}>
              {label}
            </option>
          ))}
      </Select>
      {trigger.type === "schedule.daily" ? (
        <Input
          label="Time of day (workspace timezone)"
          type="time"
          value={trigger.at ?? "21:00"}
          onChange={(e) => onChange({ ...trigger, at: e.target.value })}
        />
      ) : null}
      {trigger.type === "schedule.interval" ? (
        <Input
          label="Every how many minutes?"
          type="number"
          min={5}
          max={1440}
          value={trigger.every_minutes ?? 60}
          onChange={(e) => onChange({ ...trigger, every_minutes: Number(e.target.value) })}
        />
      ) : null}
      {trigger.type === "gmail.message_received" ? (
        <Input
          label="Only e-mails whose subject contains (optional)"
          value={String((trigger.filters?.subject_contains as string) ?? "")}
          onChange={(e) =>
            onChange({
              ...trigger,
              filters: e.target.value ? { ...trigger.filters, subject_contains: e.target.value } : {},
            })
          }
        />
      ) : null}
    </div>
  );
}

export function BlockEditor({
  block,
  onChange,
  issues,
}: {
  block: Block;
  onChange: (b: Block) => void;
  issues: ValidationIssue[];
}) {
  const set = (patch: Partial<Block>) => onChange({ ...block, ...patch });
  return (
    <div className="space-y-4">
      {issues.length ? (
        <ul className="space-y-1 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {issues.map((issue) => (
            <li key={issue.message} className="flex gap-2">
              <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
              {issue.message}
            </li>
          ))}
        </ul>
      ) : null}
      <Input label="Step name" value={block.title ?? ""} onChange={(e) => set({ title: e.target.value })} />
      {block.type === "ai.classify" ? (
        <>
          <Textarea
            label="Message to sort"
            rows={2}
            value={block.input ?? ""}
            onChange={(e) => set({ input: e.target.value })}
            hint="Usually {{trigger.text}}."
          />
          <Input
            label="Categories (comma separated)"
            value={(block.labels ?? []).join(", ")}
            onChange={(e) =>
              set({
                labels: e.target.value
                  .split(",")
                  .map((l) => l.trim().toLowerCase().replace(/\s+/g, "_"))
                  .filter(Boolean),
              })
            }
          />
          <Textarea
            label="Extra instructions for the AI"
            rows={2}
            value={block.instructions ?? ""}
            onChange={(e) => set({ instructions: e.target.value })}
          />
        </>
      ) : null}
      {block.type === "ai.extract" ? (
        <>
          <Textarea
            label="Read from"
            rows={2}
            value={block.input ?? ""}
            onChange={(e) => set({ input: e.target.value })}
          />
          <FieldsEditor fields={block.fields ?? []} onChange={(fields) => set({ fields })} />
          <p className="text-xs text-slate-600">
            If a required detail is missing, the run waits for a person to fill it in (SAF-6).
          </p>
        </>
      ) : null}
      {block.type === "ai.draft_reply" ? (
        <>
          <Textarea
            label="How should the reply sound?"
            rows={3}
            value={block.instructions ?? ""}
            onChange={(e) => set({ instructions: e.target.value })}
          />
          <Select
            label="Reply language"
            value={block.language ?? "auto"}
            onChange={(e) => set({ language: e.target.value })}
          >
            <option value="auto">Same as the customer</option>
            <option value="roman-ur">Roman Urdu</option>
            <option value="ur">اردو</option>
            <option value="en">English</option>
          </Select>
          <JsonField
            label="Facts the reply may use"
            value={block.facts}
            onChange={(facts) => set({ facts: facts as Record<string, string> })}
          />
        </>
      ) : null}
      {block.type === "ai.summarize" ? (
        <>
          <Textarea
            label="What to summarise"
            rows={2}
            value={block.input ?? ""}
            onChange={(e) => set({ input: e.target.value })}
          />
          <Textarea
            label="Instructions"
            rows={3}
            value={block.instructions ?? ""}
            onChange={(e) => set({ instructions: e.target.value })}
          />
        </>
      ) : null}
      {block.type === "condition" ? (
        <>
          <Input
            label="Continue only if"
            value={block.if ?? ""}
            onChange={(e) => set({ if: e.target.value })}
            hint={"Example: is_order.label == 'order'  or  details.amount > 10000"}
            className="font-mono"
          />
          <Select
            label="Otherwise"
            value={block.else ?? "stop"}
            onChange={(e) => set({ else: e.target.value as "stop" | "continue" })}
          >
            <option value="stop">Stop (nothing more to do)</option>
            <option value="continue">Continue anyway</option>
          </Select>
        </>
      ) : null}
      {block.type === "approval" ? (
        <>
          <Select
            label="What needs approval"
            value={block.kind ?? "review"}
            onChange={(e) => set({ kind: e.target.value as Block["kind"] })}
          >
            <option value="customer_message">A message to a customer</option>
            <option value="money">A money decision</option>
            <option value="review">A general check</option>
          </Select>
          <Input
            label="Only ask when (optional)"
            value={block.when ?? ""}
            onChange={(e) => set({ when: e.target.value || undefined })}
            hint="Leave empty to always ask. Example: details.amount > 10000"
            className="font-mono"
          />
          <Textarea
            label="Note shown to the approver"
            rows={2}
            value={block.message ?? ""}
            onChange={(e) => set({ message: e.target.value || undefined })}
          />
          {block.proposed_action ? (
            <ActionFields
              connector={block.proposed_action.connector}
              operation={block.proposed_action.operation}
              params={block.proposed_action.params}
              onChange={(patch) =>
                set({ proposed_action: { ...block.proposed_action!, ...patch } as Block["proposed_action"] })
              }
            />
          ) : null}
        </>
      ) : null}
      {block.type === "action" ? (
        <ActionFields
          connector={block.connector}
          operation={block.operation}
          params={block.params}
          customerOnly={false}
          onChange={(patch) => set(patch)}
        />
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ test panel helpers */
export function TraceList({
  steps,
}: {
  steps: {
    key: string;
    type: string;
    title: string;
    status: string;
    input: Record<string, unknown>;
    output: Record<string, unknown>;
  }[];
}) {
  return (
    <ol className="space-y-3">
      {steps.map((step, index) => {
        const meta = BLOCK_META[step.type as Block["type"]] ?? BLOCK_META.action;
        return (
          <li key={step.key} className="rounded-xl border border-slate-200 bg-white">
            <div className="flex items-center gap-3 border-b border-slate-100 px-4 py-2.5">
              <span className={clsx("grid size-7 place-items-center rounded-lg", meta.tone)}>
                {meta.icon}
              </span>
              <span className="flex-1 text-sm font-semibold text-slate-900">
                {index + 1}. {step.title}
              </span>
              <Badge
                tone={
                  step.status === "succeeded"
                    ? "green"
                    : step.status === "skipped"
                      ? "gray"
                      : step.status === "stop"
                        ? "amber"
                        : "red"
                }
              >
                {step.status === "stop" ? "stopped here" : step.status}
              </Badge>
            </div>
            <div className="grid gap-4 px-4 py-3 2xl:grid-cols-2">
              <div className="min-w-0">
                <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Input</div>
                <KeyValue data={step.input} />
              </div>
              <div className="min-w-0">
                <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Output
                </div>
                <KeyValue data={step.output} />
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export function GateChecklist({ items }: { items: { label: string; ok: boolean }[] }) {
  return (
    <ul className="space-y-1.5 text-sm">
      {items.map((item) => (
        <li
          key={item.label}
          className={clsx("flex items-center gap-2", item.ok ? "text-saved-700" : "text-slate-600")}
        >
          {item.ok ? (
            <CircleCheck className="size-4" aria-hidden />
          ) : (
            <Play className="size-4 rotate-90 text-slate-400" aria-hidden />
          )}
          {item.label}
        </li>
      ))}
    </ul>
  );
}

export function useSampleFor(triggerType: string) {
  return useMemo(() => {
    if (triggerType === "gmail.message_received")
      return {
        from: "customer@example.com",
        subject: "TCS booking confirmation",
        body: "Your booking is confirmed. Tracking number: TCS123456789. Customer phone 03001234567.",
      };
    if (triggerType === "webform.submitted")
      return {
        fields: {
          name: "Bilal Ahmed",
          phone: "03211112233",
          email: "bilal@example.com",
          message: "Please send the price list.",
        },
      };
    if (triggerType.startsWith("schedule")) return {};
    return {
      name: "Ayesha",
      text: "Assalam o alaikum, mujhe 2 kurtay chahiye medium size black colour. Address: House 12, Street 5, Gulberg Lahore. Total Rs 4500",
    };
  }, [triggerType]);
}
