"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Alert, Button, Input } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const email = String(new FormData(event.currentTarget).get("email") ?? "");
    setLoading(true);
    try {
      await api.public("/auth/forgot-password", { email });
      setDone(true);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <h1 className="text-2xl font-bold text-slate-900">Reset your password</h1>
      <p className="mt-1 text-slate-600">We will e-mail you a link that works for 30 minutes.</p>
      {done ? (
        <Alert tone="success" className="mt-6">
          If an account exists for that e-mail, a reset link is on its way.
        </Alert>
      ) : (
        <form onSubmit={onSubmit} className="mt-6 space-y-4">
          {error ? <Alert tone="error">{error}</Alert> : null}
          <Input label="E-mail" name="email" type="email" autoComplete="email" required />
          <Button type="submit" className="w-full" loading={loading}>
            Send reset link
          </Button>
        </form>
      )}
      <p className="mt-6 text-center text-sm">
        <Link href="/login" className="font-semibold text-brand-700 hover:underline">
          Back to sign in
        </Link>
      </p>
    </>
  );
}
