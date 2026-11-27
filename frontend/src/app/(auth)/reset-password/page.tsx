"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { Alert, Button, Input } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { fieldErrors, resetSchema, type FieldErrors } from "@/lib/schemas";

function ResetForm() {
  const token = useSearchParams().get("token") ?? "";
  const router = useRouter();
  const [errors, setErrors] = useState<FieldErrors>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = Object.fromEntries(new FormData(event.currentTarget)) as Record<string, string>;
    const parsed = resetSchema.safeParse(form);
    if (!parsed.success) return setErrors(fieldErrors(parsed.error));
    setErrors({});
    setLoading(true);
    try {
      await api.public("/auth/reset-password", { token, new_password: parsed.data.password });
      router.replace("/login?reset=1");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <h1 className="text-2xl font-bold text-slate-900">Choose a new password</h1>
      <form onSubmit={onSubmit} className="mt-6 space-y-4" noValidate>
        {!token ? <Alert tone="error">This reset link is incomplete.</Alert> : null}
        {error ? <Alert tone="error">{error}</Alert> : null}
        <Input
          label="New password"
          name="password"
          type="password"
          autoComplete="new-password"
          error={errors.password}
          hint="At least 8 characters with a letter and a number."
        />
        <Input
          label="Repeat new password"
          name="confirm"
          type="password"
          autoComplete="new-password"
          error={errors.confirm}
        />
        <Button type="submit" className="w-full" loading={loading} disabled={!token}>
          Save new password
        </Button>
      </form>
    </>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense>
      <ResetForm />
    </Suspense>
  );
}
