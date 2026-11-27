"use client";

import { BellOff, BellRing, OctagonX, UserPlus, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { StatusBadge } from "@/components/status";
import { useToast } from "@/components/toast";
import {
  Alert,
  Badge,
  Button,
  Card,
  CardHeader,
  ConfirmButton,
  Input,
  PageHeader,
  Select,
  Spinner,
} from "@/components/ui";
import { api, errorMessage, signOut } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { disablePush, enablePush, pushState, type PushState } from "@/lib/push";
import {
  useInvitations,
  useInvite,
  useKillSwitch,
  useMembers,
  useRemoveMember,
  useRevokeInvitation,
  useUpdateWorkspace,
  useWorkspace,
} from "@/lib/queries";
import { useMe, useMembership } from "@/lib/session";

function WorkspaceForm({ isOwner }: { isOwner: boolean }) {
  const { data: workspace } = useWorkspace();
  const update = useUpdateWorkspace();
  const toast = useToast();
  if (!workspace) return <Spinner />;
  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = Object.fromEntries(new FormData(event.currentTarget)) as Record<string, string>;
    try {
      await update.mutateAsync({ ...form, approval_threshold: form.approval_threshold });
      toast("Workspace settings saved.");
    } catch (error) {
      toast(errorMessage(error), "error");
    }
  }
  return (
    <form onSubmit={onSubmit} className="grid gap-4 p-5 sm:grid-cols-2">
      <Input label="Business name" name="name" defaultValue={workspace.name} disabled={!isOwner} />
      <Input
        label="Type of business"
        name="business_type"
        defaultValue={workspace.business_type ?? ""}
        disabled={!isOwner}
      />
      <Select
        label="Preferred language"
        name="language_pref"
        defaultValue={workspace.language_pref}
        disabled={!isOwner}
      >
        <option value="roman-ur">Roman Urdu</option>
        <option value="ur">اردو (Urdu)</option>
        <option value="en">English</option>
      </Select>
      <Select label="Timezone" name="timezone" defaultValue={workspace.timezone} disabled={!isOwner}>
        <option value="Asia/Karachi">Pakistan (Asia/Karachi)</option>
        <option value="Asia/Dubai">UAE (Asia/Dubai)</option>
        <option value="Europe/London">UK (Europe/London)</option>
        <option value="UTC">UTC</option>
      </Select>
      <Input
        label="Orders above this amount need approval (Rs)"
        name="approval_threshold"
        type="number"
        min={0}
        step={500}
        defaultValue={Number(workspace.approval_threshold)}
        disabled={!isOwner}
        hint="Used by money approvals in new automations."
      />
      {isOwner ? (
        <div className="flex items-end">
          <Button type="submit" loading={update.isPending}>
            Save settings
          </Button>
        </div>
      ) : null}
    </form>
  );
}

function Team({ isOwner }: { isOwner: boolean }) {
  const members = useMembers();
  const invitations = useInvitations(isOwner);
  const invite = useInvite();
  const revoke = useRevokeInvitation();
  const remove = useRemoveMember();
  const toast = useToast();
  const [email, setEmail] = useState("");

  async function onInvite(event: FormEvent) {
    event.preventDefault();
    try {
      await invite.mutateAsync({ email });
      toast(`Invitation sent to ${email}.`);
      setEmail("");
    } catch (error) {
      toast(errorMessage(error), "error");
    }
  }

  const pending = (invitations.data ?? []).filter((i) => !i.accepted_at && !i.revoked_at);
  return (
    <>
      <ul className="divide-y divide-slate-100">
        {(members.data ?? []).map((m) => (
          <li key={m.membership_id} className="flex flex-wrap items-center gap-3 px-5 py-3">
            <div className="min-w-0 flex-1">
              <div className="font-medium text-slate-900">{m.full_name}</div>
              <div className="truncate text-sm text-slate-600">
                {m.email} · joined {formatDate(m.joined_at)}
              </div>
            </div>
            <Badge tone={m.role === "owner" ? "brand" : "gray"}>{m.role}</Badge>
            {m.status !== "active" ? <StatusBadge status={m.status} /> : null}
            {isOwner && m.role !== "owner" ? (
              <ConfirmButton
                size="sm"
                title={`Remove ${m.full_name}?`}
                message="They will lose access to this workspace immediately."
                confirmLabel="Remove"
                onConfirm={() => remove.mutateAsync(m.membership_id).then(() => toast("Member removed."))}
              >
                Remove
              </ConfirmButton>
            ) : null}
          </li>
        ))}
      </ul>
      {isOwner ? (
        <div className="border-t border-slate-100 px-5 py-4">
          <form onSubmit={onInvite} className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="flex-1">
              <Input
                label="Invite a staff member"
                type="email"
                placeholder="name@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                hint="Staff can review approvals and see the dashboard, but cannot change automations."
              />
            </div>
            <Button
              type="submit"
              icon={<UserPlus className="size-4" />}
              loading={invite.isPending}
              disabled={!email}
            >
              Send invite
            </Button>
          </form>
          {pending.length ? (
            <ul className="mt-4 space-y-2">
              {pending.map((i) => (
                <li key={i.id} className="flex items-center gap-2 text-sm text-slate-700">
                  <Badge tone="amber">invited</Badge>
                  <span className="flex-1 truncate">{i.email}</span>
                  <span className="text-xs text-slate-500">expires {formatDate(i.expires_at)}</span>
                  <button
                    type="button"
                    className="grid size-9 place-items-center rounded-lg hover:bg-slate-100"
                    aria-label={`Revoke invitation for ${i.email}`}
                    onClick={() => revoke.mutate(i.id)}
                  >
                    <X className="size-4" />
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </>
  );
}

function PushSettings() {
  const [state, setState] = useState<PushState | null>(null);
  const [busy, setBusy] = useState(false);
  const toast = useToast();
  useEffect(() => {
    pushState()
      .then(setState)
      .catch(() => setState("unsupported"));
  }, []);
  const messages: Record<PushState, string> = {
    unsupported:
      "This browser cannot receive push notifications. Install the app on your phone's home screen to get them.",
    "disabled-on-server":
      "Push notifications are not configured on this server yet (VAPID keys). E-mail notifications still work.",
    denied: "Notifications are blocked in your browser settings for this site.",
    off: "Get a notification on this device when an approval is waiting.",
    on: "This device receives approval alerts.",
  };
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 p-5">
      <p className="text-sm text-slate-700">{state ? messages[state] : "Checking…"}</p>
      {state === "off" || state === "on" ? (
        <Button
          variant={state === "on" ? "secondary" : "primary"}
          icon={state === "on" ? <BellOff className="size-4" /> : <BellRing className="size-4" />}
          loading={busy}
          onClick={async () => {
            setBusy(true);
            try {
              setState(state === "on" ? await disablePush() : await enablePush());
            } catch (error) {
              toast(errorMessage(error), "error");
            } finally {
              setBusy(false);
            }
          }}
        >
          {state === "on" ? "Turn off on this device" : "Turn on alerts"}
        </Button>
      ) : null}
    </div>
  );
}

export default function SettingsPage() {
  const membership = useMembership();
  const isOwner = membership?.role === "owner";
  const killSwitch = useKillSwitch();
  const { data: me } = useMe();
  const toast = useToast();
  const router = useRouter();

  return (
    <>
      <PageHeader title="Settings" description="Your business, your team and how IntelliFlow reaches you." />
      <div className="space-y-6">
        <Card>
          <CardHeader
            title="Workspace"
            description={isOwner ? undefined : "Only the owner can change these settings."}
          />
          <WorkspaceForm isOwner={isOwner} />
        </Card>
        <Card>
          <CardHeader
            title="Team"
            description="Owners connect apps and change automations. Staff approve and watch the dashboard."
          />
          <Team isOwner={isOwner} />
        </Card>
        <Card>
          <CardHeader
            title="Notifications"
            description="E-mail notifications are always on for approvals and problems."
          />
          <PushSettings />
        </Card>
        <Card>
          <CardHeader title="Your account" />
          <div className="flex flex-wrap items-center justify-between gap-3 p-5">
            <div className="text-sm text-slate-700">
              {me?.full_name} · {me?.email}
            </div>
            <ConfirmButton
              variant="primary"
              title="Sign out on every device?"
              message="All your sessions will end, including on your phone."
              confirmLabel="Sign out everywhere"
              onConfirm={async () => {
                await api.post("/auth/logout-all");
                signOut();
                router.replace("/login");
              }}
            >
              Sign out everywhere
            </ConfirmButton>
          </div>
        </Card>
        {isOwner ? (
          <Card className="border-red-200">
            <CardHeader
              title="Emergency stop"
              description="Pause every automation in this workspace immediately."
            />
            <div className="flex flex-wrap items-center justify-between gap-3 p-5">
              <Alert tone="warning" className="flex-1">
                Running steps stop at the next checkpoint. Nothing is deleted; you can switch automations back
                on one by one.
              </Alert>
              <ConfirmButton
                icon={<OctagonX className="size-4" />}
                title="Pause all automations?"
                message="Every active automation in this workspace will be paused right now."
                confirmLabel="Pause everything"
                loading={killSwitch.isPending}
                onConfirm={async () => {
                  const result = await killSwitch.mutateAsync();
                  toast(`${result.paused_automations} automation(s) paused.`);
                }}
              >
                Pause all automations
              </ConfirmButton>
            </div>
          </Card>
        ) : null}
      </div>
    </>
  );
}
