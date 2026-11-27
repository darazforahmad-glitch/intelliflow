"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";

import { Alert, ButtonLink, Spinner } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";

function Verify() {
  const token = useSearchParams().get("token");
  const [state, setState] = useState<"working" | "done" | "error">(token ? "working" : "error");
  const [message, setMessage] = useState(token ? "" : "This verification link is incomplete.");
  const sent = useRef(false);

  useEffect(() => {
    if (!token || sent.current) return;
    sent.current = true; // the token is single-use: never send it twice (React strict mode)
    api
      .public<{ message: string }>("/auth/verify-email", { token })
      .then(() => setState("done"))
      .catch((err) => {
        setState("error");
        setMessage(errorMessage(err));
      });
  }, [token]);

  if (state === "working") return <Spinner label="Verifying your e-mail" />;
  return (
    <div className="space-y-6 text-center">
      <h1 className="text-2xl font-bold text-slate-900">
        {state === "done" ? "E-mail verified" : "Verification failed"}
      </h1>
      {state === "done" ? (
        <Alert tone="success">Your account is ready.</Alert>
      ) : (
        <Alert tone="error">{message}</Alert>
      )}
      <ButtonLink href={state === "done" ? "/login?verified=1" : "/login"} className="w-full">
        Continue to sign in
      </ButtonLink>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <Verify />
    </Suspense>
  );
}
