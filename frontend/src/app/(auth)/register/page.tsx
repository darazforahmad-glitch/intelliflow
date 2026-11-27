"use client";

import { MailCheck } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Alert, Button, ButtonLink, Input } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fieldErrors, registerSchema, type FieldErrors } from "@/lib/schemas";

interface OutboxMessage {
  subject: string;
  body: string;
}

/** In development the console e-mail backend keeps an outbox instead of sending mail. */
async function devVerificationLink(email: string): Promise<string | null> {
  try {
    const messages = await api.public<OutboxMessage[]>(`/dev/outbox?to=${encodeURIComponent(email)}`);
    const body = messages.find((m) => m.subject.includes("Verify"))?.body ?? "";
    const match = body.match(/https?:\/\/\S+verify-email\?token=\S+/);
    return match ? match[0].replace(/^https?:\/\/[^/]+/, "") : null;
  } catch {
    return null; // not available outside development
  }
}

export default function RegisterPage() {
  const [errors, setErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [devLink, setDevLink] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = Object.fromEntries(new FormData(event.currentTarget)) as Record<string, string>;
    const parsed = registerSchema.safeParse({ ...form, phone: form.phone || undefined });
    if (!parsed.success) return setErrors(fieldErrors(parsed.error));
    setErrors({});
    setError(null);
    setLoading(true);
    try {
      await api.public("/auth/register", parsed.data);
      setSentTo(parsed.data.email);
      setDevLink(await devVerificationLink(parsed.data.email));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  if (sentTo) {
    return (
      <div className="text-center">
        <div className="mx-auto mb-4 grid size-14 place-items-center rounded-2xl bg-saved-50 text-saved-600">
          <MailCheck className="size-7" aria-hidden />
        </div>
        <h1 className="text-2xl font-bold text-slate-900">Check your e-mail</h1>
        <p className="mt-2 text-slate-600">
          We sent a verification link to <strong className="text-slate-900">{sentTo}</strong>. Open it to
          activate your account.
        </p>
        {devLink ? (
          <Alert tone="info" className="mt-6 text-left" title="Development mode">
            E-mails are kept in the outbox instead of being sent.
            <ButtonLink href={devLink} className="mt-3 w-full">
              Open the verification link
            </ButtonLink>
          </Alert>
        ) : null}
        <p className="mt-6 text-sm text-slate-600">
          Already verified?{" "}
          <Link href="/login" className="font-semibold text-brand-700 hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    );
  }

  return (
    <>
      <h1 className="text-2xl font-bold text-slate-900">Create your account</h1>
      <p className="mt-1 text-slate-600">Free while we pilot with small businesses.</p>
      <form onSubmit={onSubmit} className="mt-6 space-y-4" noValidate>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <Input label="Full name" name="full_name" autoComplete="name" required error={errors.full_name} />
        <Input label="E-mail" name="email" type="email" autoComplete="email" required error={errors.email} />
        <Input
          label="Mobile number (optional)"
          name="phone"
          type="tel"
          autoComplete="tel"
          placeholder="0300 1234567"
          error={errors.phone}
        />
        <Input
          label="Password"
          name="password"
          type="password"
          autoComplete="new-password"
          required
          hint="At least 8 characters with a letter and a number."
          error={errors.password}
        />
        <Button type="submit" className="w-full" loading={loading}>
          Create account
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-slate-600">
        Already have an account?{" "}
        <Link href="/login" className="font-semibold text-brand-700 hover:underline">
          Sign in
        </Link>
      </p>
    </>
  );
}
