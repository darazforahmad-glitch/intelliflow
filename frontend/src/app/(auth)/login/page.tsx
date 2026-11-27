"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { Alert, Button, Input } from "@/components/ui";
import { api, ApiError, errorMessage, storeTokens } from "@/lib/api";
import { fieldErrors, loginSchema, type FieldErrors } from "@/lib/schemas";
import type { TokenPair } from "@/lib/types";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [errors, setErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<ApiError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [email, setEmail] = useState("");

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = Object.fromEntries(new FormData(event.currentTarget)) as Record<string, string>;
    const parsed = loginSchema.safeParse(form);
    if (!parsed.success) return setErrors(fieldErrors(parsed.error));
    setErrors({});
    setError(null);
    setLoading(true);
    try {
      const pair = await api.public<TokenPair>("/auth/login", parsed.data);
      storeTokens(pair);
      const next = params.get("next");
      router.replace(next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(0, errorMessage(err)));
    } finally {
      setLoading(false);
    }
  }

  async function resend() {
    await api.public("/auth/resend-verification", { email });
    setNotice("We sent a new verification link. Please check your inbox.");
  }

  return (
    <>
      <h1 className="text-2xl font-bold text-slate-900">Sign in</h1>
      <p className="mt-1 text-slate-600">Welcome back. Pick up where you left off.</p>
      <form onSubmit={onSubmit} className="mt-6 space-y-4" noValidate>
        {params.get("verified") ? (
          <Alert tone="success">Your e-mail is verified. Please sign in.</Alert>
        ) : null}
        {params.get("reset") ? (
          <Alert tone="success">Your password was changed. Please sign in.</Alert>
        ) : null}
        {notice ? <Alert tone="success">{notice}</Alert> : null}
        {error ? (
          <Alert tone="error" title={error.message}>
            {error.hint}
            {error.code === "email_not_verified" ? (
              <button type="button" onClick={resend} className="mt-1 block font-semibold underline">
                Send me a new verification link
              </button>
            ) : null}
          </Alert>
        ) : null}
        <Input
          label="E-mail"
          name="email"
          type="email"
          autoComplete="email"
          required
          error={errors.email}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <Input
          label="Password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          error={errors.password}
        />
        <div className="flex justify-end">
          <Link href="/forgot-password" className="text-sm font-medium text-brand-700 hover:underline">
            Forgot password?
          </Link>
        </div>
        <Button type="submit" className="w-full" loading={loading}>
          Sign in
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-slate-600">
        New to IntelliFlow?{" "}
        <Link
          href={`/register${params.get("next") ? `?next=${encodeURIComponent(params.get("next")!)}` : ""}`}
          className="font-semibold text-brand-700 hover:underline"
        >
          Create an account
        </Link>
      </p>
    </>
  );
}

export default function LoginPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
