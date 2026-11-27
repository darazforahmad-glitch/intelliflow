"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Spinner } from "@/components/ui";
import { useHydrated, useSession } from "@/lib/session";

export default function Home() {
  const hydrated = useHydrated();
  const session = useSession();
  const router = useRouter();
  useEffect(() => {
    if (hydrated) router.replace(session ? "/dashboard" : "/login");
  }, [hydrated, session, router]);
  return (
    <div className="grid min-h-dvh place-items-center">
      <Spinner label="Opening IntelliFlow" />
    </div>
  );
}
