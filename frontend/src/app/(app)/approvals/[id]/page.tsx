"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { ApprovalCard } from "@/components/approval-card";
import { Alert, Spinner } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { useApproval } from "@/lib/queries";

export default function ApprovalPage() {
  const { id } = useParams<{ id: string }>();
  const { data, isLoading, error } = useApproval(id);
  return (
    <div className="mx-auto max-w-2xl">
      <Link
        href="/approvals"
        className="mb-3 inline-flex min-h-9 items-center gap-1 text-sm font-medium text-slate-600 hover:text-slate-900"
      >
        <ArrowLeft className="size-4" aria-hidden /> All approvals
      </Link>
      {isLoading ? (
        <Spinner />
      ) : error ? (
        <Alert tone="error">{errorMessage(error)}</Alert>
      ) : data ? (
        <ApprovalCard approval={data} />
      ) : null}
      {data ? (
        <p className="mt-3 text-sm text-slate-600">
          <Link href={`/runs/${data.run_id}`} className="font-medium text-brand-700 hover:underline">
            See the full run
          </Link>
        </p>
      ) : null}
    </div>
  );
}
