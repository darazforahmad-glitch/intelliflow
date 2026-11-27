"use client";

import { Copy, FileSpreadsheet, FormInput, Mail, MessageCircle, Send, Unplug } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent, type ReactNode } from "react";

import { StatusBadge } from "@/components/status";
import { useToast } from "@/components/toast";
import {
  Alert,
  Badge,
  Button,
  Card,
  ConfirmButton,
  Input,
  Modal,
  PageHeader,
  Spinner,
  Textarea,
} from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import {
  useConnections,
  useConnectWhatsApp,
  useCreateSandbox,
  useCreateWebform,
  useDisconnect,
  useSandboxRecords,
  useSimulate,
} from "@/lib/queries";
import { fieldErrors, whatsappConnectSchema, type FieldErrors } from "@/lib/schemas";
import { useMembership, useWorkspaceId } from "@/lib/session";
import type { Connection } from "@/lib/types";

const PROVIDERS: { provider: Connection["provider"]; title: string; icon: ReactNode; text: string }[] = [
  {
    provider: "whatsapp",
    title: "WhatsApp Business",
    icon: <MessageCircle className="size-6" />,
    text: "Receive customer messages and send replies you approve (WhatsApp Cloud API).",
  },
  {
    provider: "google_sheets",
    title: "Google Sheets",
    icon: <FileSpreadsheet className="size-6" />,
    text: "Read, add and update rows — your orders register in the cloud.",
  },
  {
    provider: "gmail",
    title: "Gmail",
    icon: <Mail className="size-6" />,
    text: "Read new e-mails (e.g. courier bookings) and send replies.",
  },
  {
    provider: "webform",
    title: "Website forms",
    icon: <FormInput className="size-6" />,
    text: "A secret URL for each form on your website or Google Form.",
  },
];

function SandboxData({ connection }: { connection: Connection }) {
  const [open, setOpen] = useState(false);
  const { data, isLoading } = useSandboxRecords(connection.id, open);
  return (
    <details
      className="mt-3 rounded-xl border border-slate-200 bg-slate-50"
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
    >
      <summary className="cursor-pointer px-3 py-2 text-sm font-medium text-slate-800">Sandbox data</summary>
      <div className="space-y-3 px-3 pb-3">
        {isLoading ? <Spinner /> : null}
        {data
          ? Object.entries(data.sheets).map(([sheet, rows]) => {
              const columns = Array.from(new Set(rows.flatMap((r) => Object.keys(r)))).filter(
                (c) => c !== "row_number",
              );
              return (
                <div key={sheet} className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
                  <div className="border-b border-slate-100 px-3 py-2 text-xs font-semibold text-slate-700">
                    Sheet “{sheet}” · {rows.length} row(s)
                  </div>
                  <table className="w-full min-w-[36rem] text-xs">
                    <thead className="text-left text-slate-600">
                      <tr>
                        <th className="px-2 py-1">#</th>
                        {columns.map((c) => (
                          <th key={c} className="px-2 py-1">
                            {c}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row) => (
                        <tr key={String(row.row_number)} className="border-t border-slate-100">
                          <td className="px-2 py-1 text-slate-500">{String(row.row_number)}</td>
                          {columns.map((c) => (
                            <td key={c} className="max-w-48 truncate px-2 py-1">
                              {String(row[c] ?? "")}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              );
            })
          : null}
        {data?.outbox.length ? (
          <ul className="space-y-2">
            {data.outbox.slice(0, 20).map((m, i) => (
              <li key={i} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm">
                <div className="text-xs text-slate-500">
                  {String(m.operation ?? "").replace("_", " ")} → {String(m.to ?? "")} ·{" "}
                  {formatDateTime(String(m.created_at))}
                </div>
                <div className="mt-0.5 whitespace-pre-wrap text-slate-900">
                  {String(m.text ?? m.body ?? m.template ?? "")}
                </div>
              </li>
            ))}
          </ul>
        ) : null}
        {data && !data.outbox.length && !Object.keys(data.sheets).length ? (
          <p className="text-sm text-slate-600">Nothing recorded yet.</p>
        ) : null}
      </div>
    </details>
  );
}

function Simulator({ connection }: { connection: Connection }) {
  const simulate = useSimulate();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState(
    "Assalam o alaikum, mujhe 2 kurtay chahiye medium size black colour. Address: House 12, Street 5, Gulberg Lahore. Total Rs 4500",
  );
  const [name, setName] = useState("Ayesha");
  const [subject, setSubject] = useState("TCS booking confirmation");
  const isGmail = connection.provider === "gmail";
  const isForm = connection.provider === "webform";

  async function send(event: FormEvent) {
    event.preventDefault();
    try {
      const body = isForm
        ? { fields: { name, phone: "03001234567", message: text } }
        : isGmail
          ? { subject, body: text, sender: "bookings@courier.example" }
          : { text, name };
      await simulate.mutateAsync({ id: connection.id, body });
      toast("Sent through the webhook gateway. Check Approvals and the dashboard.");
      setOpen(false);
    } catch (error) {
      toast(errorMessage(error), "error");
    }
  }

  return (
    <>
      <Button variant="secondary" size="sm" icon={<Send className="size-4" />} onClick={() => setOpen(true)}>
        {isForm ? "Send a test submission" : isGmail ? "Simulate an e-mail" : "Simulate a customer message"}
      </Button>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={
          isForm
            ? "Test form submission"
            : isGmail
              ? "Simulate incoming e-mail"
              : "Simulate a WhatsApp message"
        }
      >
        <form onSubmit={send} className="space-y-3">
          <p className="text-sm text-slate-600">
            This goes through the same signed-webhook path as a real{" "}
            {isForm ? "form" : isGmail ? "e-mail" : "WhatsApp message"}.
          </p>
          {!isGmail ? (
            <Input
              label={isForm ? "Name field" : "Customer name"}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          ) : (
            <Input label="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
          )}
          <Textarea
            label={isForm ? "Message field" : isGmail ? "E-mail body" : "Message"}
            rows={5}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <Button type="submit" className="w-full" loading={simulate.isPending}>
            Send
          </Button>
        </form>
      </Modal>
    </>
  );
}

function WhatsAppLiveForm({ onDone }: { onDone: () => void }) {
  const connect = useConnectWhatsApp();
  const toast = useToast();
  const [errors, setErrors] = useState<FieldErrors>({});
  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = Object.fromEntries(new FormData(event.currentTarget)) as Record<string, string>;
    const parsed = whatsappConnectSchema.safeParse(form);
    if (!parsed.success) return setErrors(fieldErrors(parsed.error));
    try {
      await connect.mutateAsync(
        Object.fromEntries(Object.entries(parsed.data).filter(([, v]) => v)) as Record<string, string>,
      );
      toast("WhatsApp connected.");
      onDone();
    } catch (error) {
      toast(errorMessage(error), "error");
    }
  }
  return (
    <form onSubmit={onSubmit} className="space-y-3" noValidate>
      <Alert tone="info">
        In production this happens through Meta Embedded Signup. During development, use Meta&apos;s test
        number from WhatsApp Manager → API setup.
      </Alert>
      <Input
        label="Phone number ID"
        name="phone_number_id"
        inputMode="numeric"
        error={errors.phone_number_id}
      />
      <Input label="WhatsApp Business Account ID" name="waba_id" inputMode="numeric" error={errors.waba_id} />
      <Input
        label="Access token"
        name="access_token"
        type="password"
        autoComplete="off"
        error={errors.access_token}
        hint="Stored encrypted. It is never shown again."
      />
      <Input label="Display number (optional)" name="display_phone_number" placeholder="+92 300 1234567" />
      <Button type="submit" className="w-full" loading={connect.isPending}>
        Connect WhatsApp
      </Button>
    </form>
  );
}

function ProviderCard({
  provider,
  title,
  icon,
  text,
  connections,
  isOwner,
}: (typeof PROVIDERS)[number] & { connections: Connection[]; isOwner: boolean }) {
  const createSandbox = useCreateSandbox();
  const createWebform = useCreateWebform();
  const disconnect = useDisconnect();
  const toast = useToast();
  const workspaceId = useWorkspaceId();
  const [liveOpen, setLiveOpen] = useState(false);
  const [formName, setFormName] = useState("Website contact form");

  async function connectGoogle() {
    try {
      const { authorization_url } = await api.get<{ authorization_url: string }>(
        `/workspaces/${workspaceId}/connections/google/authorize?provider=${provider}`,
      );
      window.location.assign(authorization_url);
    } catch (error) {
      toast(errorMessage(error), "error");
    }
  }

  return (
    <Card className="flex flex-col p-5">
      <div className="flex items-start gap-3">
        <div className="rounded-xl bg-brand-50 p-2.5 text-brand-600">{icon}</div>
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold text-slate-900">{title}</h2>
          <p className="text-sm text-slate-600">{text}</p>
        </div>
      </div>
      <div className="mt-4 flex-1 space-y-3">
        {connections.map((c) => (
          <div key={c.id} className="rounded-xl border border-slate-200 p-3">
            <div className="flex flex-wrap items-center gap-2">
              <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-900">
                {c.display_name}
              </span>
              <Badge tone={c.mode === "sandbox" ? "amber" : "green"}>{c.mode}</Badge>
              <StatusBadge status={c.status} />
            </div>
            {c.last_error ? <p className="mt-1 text-sm text-red-700">{c.last_error}</p> : null}
            {c.provider === "whatsapp" ? (
              <p className="mt-1 text-xs text-slate-600">
                Phone number ID: {String(c.config.phone_number_id ?? "")}
              </p>
            ) : null}
            {c.webhook_url ? (
              <div className="mt-2 flex items-center gap-2">
                <code className="min-w-0 flex-1 truncate rounded-lg bg-slate-100 px-2 py-1.5 text-xs">
                  {c.webhook_url}
                </code>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label="Copy form URL"
                  icon={<Copy className="size-4" />}
                  onClick={async () => {
                    await navigator.clipboard.writeText(c.webhook_url!);
                    toast("Form URL copied.");
                  }}
                />
              </div>
            ) : null}
            {isOwner ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {c.provider !== "google_sheets" && (c.mode === "sandbox" || c.provider === "webform") ? (
                  <Simulator connection={c} />
                ) : null}
                <ConfirmButton
                  size="sm"
                  icon={<Unplug className="size-4" />}
                  title={`Disconnect ${title}?`}
                  message="Automations that use it will be paused. You can connect again at any time."
                  confirmLabel="Disconnect"
                  onConfirm={async () => {
                    const result = await disconnect.mutateAsync(c.id);
                    toast(result.message);
                  }}
                >
                  Disconnect
                </ConfirmButton>
              </div>
            ) : null}
            {c.mode === "sandbox" && c.provider !== "webform" ? <SandboxData connection={c} /> : null}
          </div>
        ))}
      </div>
      {isOwner && (provider === "webform" || !connections.length) ? (
        <div className="mt-4 space-y-2 border-t border-slate-100 pt-4">
          {provider === "webform" ? (
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
              <div className="flex-1">
                <Input label="New form name" value={formName} onChange={(e) => setFormName(e.target.value)} />
              </div>
              <Button
                onClick={async () => {
                  try {
                    await createWebform.mutateAsync(formName);
                    toast("Form URL created.");
                  } catch (error) {
                    toast(errorMessage(error), "error");
                  }
                }}
                loading={createWebform.isPending}
              >
                Create form URL
              </Button>
            </div>
          ) : (
            <div className="flex flex-wrap gap-2">
              <Button
                variant="secondary"
                onClick={async () => {
                  try {
                    await createSandbox.mutateAsync(provider);
                    toast(`${title} connected in sandbox mode.`);
                  } catch (error) {
                    toast(errorMessage(error), "error");
                  }
                }}
                loading={createSandbox.isPending && createSandbox.variables === provider}
              >
                Use sandbox
              </Button>
              <Button onClick={() => (provider === "whatsapp" ? setLiveOpen(true) : connectGoogle())}>
                Connect live
              </Button>
            </div>
          )}
        </div>
      ) : null}
      <Modal open={liveOpen} onClose={() => setLiveOpen(false)} title="Connect WhatsApp">
        <WhatsAppLiveForm onDone={() => setLiveOpen(false)} />
      </Modal>
    </Card>
  );
}

function OAuthResult() {
  const params = useSearchParams();
  const connected = params.get("connected");
  const error = params.get("error");
  if (connected)
    return (
      <Alert tone="success" className="mb-4">
        {connected === "gmail" ? "Gmail" : "Google Sheets"} is connected.
      </Alert>
    );
  if (error)
    return (
      <Alert tone="error" className="mb-4">
        Google did not connect ({error}). Please try again.
      </Alert>
    );
  return null;
}

export default function IntegrationsPage() {
  const { data, isLoading } = useConnections();
  const membership = useMembership();
  const isOwner = membership?.role === "owner";
  return (
    <>
      <PageHeader
        title="Integrations"
        description="Connect the apps your automations read from and write to. Tokens are encrypted and never shown again."
      />
      <Suspense>
        <OAuthResult />
      </Suspense>
      <Alert tone="info" className="mb-6" title="Sandbox mode">
        Sandbox connections behave like the real apps but record what they would do — perfect for trying
        IntelliFlow before connecting your real WhatsApp number. See what was “sent” under{" "}
        <em>Sandbox data</em>. Then try it from the{" "}
        <Link href="/approvals" className="font-semibold underline">
          Approvals
        </Link>{" "}
        page.
      </Alert>
      {isLoading ? (
        <Spinner />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {PROVIDERS.map((p) => (
            <ProviderCard
              key={p.provider}
              {...p}
              connections={(data ?? []).filter((c) => c.provider === p.provider)}
              isOwner={isOwner}
            />
          ))}
        </div>
      )}
    </>
  );
}
