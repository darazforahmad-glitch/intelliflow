"use client";

import { BellRing, Inbox } from "lucide-react";
import { useEffect, useState } from "react";

import { ApprovalCard } from "@/components/approval-card";
import { useToast } from "@/components/toast";
import { Alert, Button, EmptyState, PageHeader, Segmented, Skeleton } from "@/components/ui";
import { errorMessage } from "@/lib/api";
import { enablePush, pushState, type PushState } from "@/lib/push";
import { useApprovals } from "@/lib/queries";

function PushPrompt() {
  const [state, setState] = useState<PushState | null>(null);
  const toast = useToast();
  useEffect(() => {
    pushState()
      .then(setState)
      .catch(() => setState("unsupported"));
  }, []);
  if (state !== "off") return null;
  return (
    <Alert tone="info" className="mb-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span>Get a notification on this phone when something needs approval.</span>
        <Button
          size="sm"
          icon={<BellRing className="size-4" />}
          onClick={async () => {
            try {
              setState(await enablePush());
            } catch (error) {
              toast(errorMessage(error), "error");
            }
          }}
        >
          Turn on alerts
        </Button>
      </div>
    </Alert>
  );
}

export default function ApprovalsPage() {
  const [state, setState] = useState<"open" | "decided">("open");
  const { data, isLoading, error } = useApprovals(state);
  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader
        title="Approvals"
        description="Customer messages, big orders and anything the AI was unsure about wait here for you."
        actions={
          <Segmented
            label="Show"
            value={state}
            onChange={setState}
            options={[
              { value: "open", label: "Waiting" },
              { value: "decided", label: "Decided" },
            ]}
          />
        }
      />
      <PushPrompt />
      {error ? <Alert tone="error">{errorMessage(error)}</Alert> : null}
      {isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
        </div>
      ) : data?.length ? (
        <div className="space-y-4">
          {data.map((approval) => (
            <ApprovalCard key={approval.id} approval={approval} compact />
          ))}
        </div>
      ) : (
        <EmptyState
          icon={<Inbox className="size-6" />}
          title={state === "open" ? "Nothing to approve" : "No decisions yet"}
          description={
            state === "open" ? "When an automation needs you, it appears here and on your phone." : undefined
          }
        />
      )}
    </div>
  );
}
