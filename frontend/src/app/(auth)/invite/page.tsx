"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Users } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Alert, Button, ButtonLink, Spinner } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { useHydrated, useSession } from "@/lib/session";

interface Preview {
  workspace_name: string;
  email: string;
  role: string;
  valid: boolean;
}

function Invite() {
  const token = useSearchParams().get("token") ?? "";
  const hydrated = useHydrated();
  const session = useSession();
  const router = useRouter();
  const client = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const preview = useQuery({
    queryKey: ["invitation", token],
    queryFn: () => api.public<Preview>(`/invitations/${encodeURIComponent(token)}`),
    enabled: Boolean(token),
    retry: false,
  });

  if (!token) return <Alert tone="error">This invitation link is incomplete.</Alert>;
  if (preview.isLoading || !hydrated) return <Spinner />;
  if (preview.error) return <Alert tone="error">{errorMessage(preview.error)}</Alert>;
  const invite = preview.data!;
  const next = encodeURIComponent(`/invite?token=${token}`);

  async function accept() {
    setLoading(true);
    try {
      await api.post("/invitations/accept", { token });
      await client.invalidateQueries({ queryKey: ["me"] });
      router.replace("/approvals");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-5 text-center">
      <div className="mx-auto grid size-14 place-items-center rounded-2xl bg-brand-50 text-brand-600">
        <Users className="size-7" aria-hidden />
      </div>
      <h1 className="text-2xl font-bold text-slate-900">Join {invite.workspace_name}</h1>
      <p className="text-slate-600">
        You were invited as <strong>{invite.role}</strong> ({invite.email}). Staff can review approvals and
        see the dashboard.
      </p>
      {!invite.valid ? <Alert tone="error">This invitation has expired or was already used.</Alert> : null}
      {error ? <Alert tone="error">{error}</Alert> : null}
      {invite.valid && session ? (
        <Button className="w-full" onClick={accept} loading={loading}>
          Accept invitation
        </Button>
      ) : null}
      {invite.valid && !session ? (
        <div className="grid gap-2">
          <ButtonLink href={`/login?next=${next}`}>Sign in to accept</ButtonLink>
          <ButtonLink href={`/register?next=${next}`} variant="secondary">
            Create an account with {invite.email}
          </ButtonLink>
        </div>
      ) : null}
    </div>
  );
}

export default function InvitePage() {
  return (
    <Suspense fallback={<Spinner />}>
      <Invite />
    </Suspense>
  );
}
