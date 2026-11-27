"use client";

import clsx from "clsx";
import { Check, Clock, PencilLine, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { errorMessage } from "@/lib/api";
import { formatDateTime, rupees, timeAgo } from "@/lib/format";
import { useDecide } from "@/lib/queries";
import type { Approval } from "@/lib/types";

import { APPROVAL_KIND, StatusBadge } from "./status";
import { useToast } from "./toast";
import { Alert, Badge, Button, Card, KeyValue, Modal, Textarea } from "./ui";

const ARABIC = /[؀-ۿ]/;

function Quote({ text }: { text: string }) {
  const rtl = ARABIC.test(text);
  return (
    <blockquote
      dir={rtl ? "rtl" : undefined}
      className={clsx(
        "whitespace-pre-wrap rounded-2xl rounded-tl-md bg-slate-100 px-4 py-3 text-sm text-slate-900",
        rtl && "urdu",
      )}
    >
      {text}
    </blockquote>
  );
}

function ActionPreview({
  approval,
  editing,
  text,
  setText,
}: {
  approval: Approval;
  editing: boolean;
  text: string;
  setText: (v: string) => void;
}) {
  const action = approval.payload.proposed_action;
  if (!action) return null;
  const params = action.params as Record<string, unknown>;
  if (action.connector === "whatsapp" && action.operation === "send_text") {
    return (
      <div>
        <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Reply on WhatsApp to {String(params.to ?? "")}
        </div>
        {editing ? (
          <Textarea
            label="Message"
            rows={5}
            value={text}
            onChange={(e) => setText(e.target.value)}
            autoFocus
          />
        ) : (
          <div className="whitespace-pre-wrap rounded-2xl rounded-tr-md bg-emerald-50 px-4 py-3 text-sm text-slate-900 ring-1 ring-emerald-200">
            {String(params.text ?? "")}
          </div>
        )}
      </div>
    );
  }
  if (action.connector === "gmail" && action.operation === "send_email") {
    return (
      <div>
        <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
          E-mail to {String(params.to ?? "")}
        </div>
        <div className="text-sm font-medium text-slate-900">{String(params.subject ?? "")}</div>
        {editing ? (
          <Textarea label="Body" rows={6} value={text} onChange={(e) => setText(e.target.value)} />
        ) : (
          <div className="mt-1 whitespace-pre-wrap rounded-xl bg-slate-50 px-4 py-3 text-sm">
            {String(params.body ?? "")}
          </div>
        )}
      </div>
    );
  }
  return (
    <div>
      <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
        Then: {action.connector.replace("_", " ")} · {action.operation.replace("_", " ")}
      </div>
      <KeyValue data={params} />
    </div>
  );
}

export function ApprovalCard({ approval, compact = false }: { approval: Approval; compact?: boolean }) {
  const decide = useDecide();
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [note, setNote] = useState("");
  const params = (approval.payload.proposed_action?.params ?? {}) as Record<string, unknown>;
  const textKey = approval.payload.proposed_action?.connector === "gmail" ? "body" : "text";
  const [text, setText] = useState(String(params[textKey] ?? ""));
  const [fields, setFields] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      Object.entries(approval.payload.ai_output ?? {}).map(([k, v]) => [
        k,
        v === null || v === undefined ? "" : String(v),
      ]),
    ),
  );
  const open = approval.status === "pending" || approval.status === "reminded";
  const kind = APPROVAL_KIND[approval.kind] ?? { label: approval.kind, tone: "gray" as const };
  const isReview = approval.kind === "review";
  const amount =
    (approval.payload.show?.details as Record<string, unknown> | undefined)?.amount ??
    (approval.payload.ai_output as Record<string, unknown> | undefined)?.amount;

  async function submit(decision: "approve" | "edit" | "reject") {
    try {
      if (isReview && decision !== "reject") {
        const changed = Object.fromEntries(
          Object.entries(fields).filter(([k, v]) => String(approval.payload.ai_output?.[k] ?? "") !== v),
        );
        await decide.mutateAsync({
          id: approval.id,
          decision: Object.keys(changed).length ? "edit" : "approve",
          edited_fields: changed,
        });
      } else {
        await decide.mutateAsync({
          id: approval.id,
          decision,
          edited_params: decision === "edit" ? { [textKey]: text } : undefined,
          note: note || undefined,
        });
      }
      toast(
        decision === "reject" ? "Rejected. Nothing was sent." : "Approved. The automation is continuing.",
      );
      setEditing(false);
      setRejecting(false);
    } catch (error) {
      toast(errorMessage(error), "error");
    }
  }

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-100 px-4 py-3">
        <Badge tone={kind.tone}>{kind.label}</Badge>
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-700">
          {approval.automation_name}
        </span>
        <span className="flex items-center gap-1 text-xs text-slate-500">
          <Clock className="size-3.5" aria-hidden /> {timeAgo(approval.created_at)}
        </span>
      </div>
      <div className="space-y-4 px-4 py-4">
        <div>
          {compact ? (
            <Link
              href={`/approvals/${approval.id}`}
              className="font-semibold text-slate-900 hover:text-brand-700"
            >
              {approval.title}
            </Link>
          ) : (
            <h2 className="text-lg font-semibold text-slate-900">{approval.title}</h2>
          )}
          {approval.payload.message ? (
            <p className="mt-1 text-sm text-slate-700">{approval.payload.message}</p>
          ) : null}
        </div>
        {approval.kind === "money" && amount !== undefined ? (
          <div className="rounded-xl bg-amber-50 px-4 py-3 ring-1 ring-amber-200">
            <div className="text-xs font-semibold uppercase tracking-wide text-amber-800">Amount</div>
            <div className="text-2xl font-bold text-amber-900">{rupees(amount as string | number)}</div>
          </div>
        ) : null}
        {approval.payload.input ? (
          <div>
            <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Customer wrote
            </div>
            <Quote text={approval.payload.input} />
          </div>
        ) : null}
        {isReview ? (
          <div>
            <div className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">
              Details the AI read {approval.payload.missing?.length ? "— please fill in what is missing" : ""}
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {(approval.payload.fields ?? []).map((field) => (
                <label key={field.name} className="text-sm">
                  <span
                    className={clsx(
                      "font-medium",
                      approval.payload.missing?.includes(field.name) ? "text-red-700" : "text-slate-800",
                    )}
                  >
                    {field.name.replace(/_/g, " ")}
                    {field.required ? " *" : ""}
                  </span>
                  <input
                    className={clsx(
                      "mt-1 block min-h-11 w-full rounded-lg border px-3",
                      approval.payload.missing?.includes(field.name) && !fields[field.name]
                        ? "border-red-400"
                        : "border-slate-300",
                    )}
                    value={fields[field.name] ?? ""}
                    disabled={!open}
                    onChange={(e) => setFields({ ...fields, [field.name]: e.target.value })}
                  />
                </label>
              ))}
            </div>
          </div>
        ) : approval.payload.ai_output && Object.keys(approval.payload.ai_output).length ? (
          <details open={!compact}>
            <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-slate-500">
              What the AI found
            </summary>
            <div className="mt-2">
              {Object.entries(approval.payload.ai_output).map(([key, value]) =>
                value && typeof value === "object" ? (
                  <KeyValue key={key} data={value as Record<string, unknown>} />
                ) : null,
              )}
            </div>
          </details>
        ) : null}
        <ActionPreview approval={approval} editing={editing} text={text} setText={setText} />
        {approval.kind === "window_closed" ? (
          <Alert tone="warning">
            WhatsApp only allows approved templates more than 24 hours after the customer&apos;s last message.
          </Alert>
        ) : null}
      </div>
      {open ? (
        <div className="grid grid-cols-3 gap-2 border-t border-slate-100 bg-slate-50 px-4 py-3">
          {editing ? (
            <>
              <Button variant="secondary" onClick={() => setEditing(false)}>
                Cancel
              </Button>
              <Button
                variant="success"
                className="col-span-2"
                icon={<Check className="size-4" />}
                loading={decide.isPending}
                onClick={() => submit("edit")}
              >
                Approve with changes
              </Button>
            </>
          ) : (
            <>
              <Button variant="secondary" icon={<X className="size-4" />} onClick={() => setRejecting(true)}>
                Reject
              </Button>
              {approval.payload.editable?.includes(textKey) ? (
                <Button
                  variant="secondary"
                  icon={<PencilLine className="size-4" />}
                  onClick={() => setEditing(true)}
                >
                  Edit
                </Button>
              ) : (
                <span />
              )}
              <Button
                variant="success"
                icon={<Check className="size-4" />}
                loading={decide.isPending}
                onClick={() => submit("approve")}
              >
                Approve
              </Button>
            </>
          )}
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 bg-slate-50 px-4 py-3 text-sm text-slate-600">
          <StatusBadge status={approval.status} />
          {approval.decided_by_name ? `by ${approval.decided_by_name}` : ""}{" "}
          {approval.decided_at ? `on ${formatDateTime(approval.decided_at)}` : ""}
          {approval.decision_note ? (
            <span className="w-full text-slate-700">“{approval.decision_note}”</span>
          ) : null}
        </div>
      )}
      <Modal
        open={rejecting}
        onClose={() => setRejecting(false)}
        title="Reject this?"
        footer={
          <>
            <Button variant="secondary" onClick={() => setRejecting(false)}>
              Keep it
            </Button>
            <Button variant="danger" onClick={() => submit("reject")} loading={decide.isPending}>
              Reject
            </Button>
          </>
        }
      >
        <p className="mb-3 text-sm text-slate-700">
          The run stops here and nothing is sent. Your decision is recorded and cannot be changed later.
        </p>
        <Textarea label="Reason (optional)" rows={2} value={note} onChange={(e) => setNote(e.target.value)} />
      </Modal>
    </Card>
  );
}
