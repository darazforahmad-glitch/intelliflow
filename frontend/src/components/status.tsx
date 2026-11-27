import type { ReactNode } from "react";

import { Badge } from "./ui";

type Tone = "gray" | "brand" | "green" | "amber" | "red" | "purple" | "blue";

const STATUS: Record<string, { tone: Tone; label: string }> = {
  // automations (Figure 4.9)
  draft: { tone: "gray", label: "Draft" },
  validated: { tone: "blue", label: "Validated" },
  tested: { tone: "purple", label: "Tested" },
  active: { tone: "green", label: "Active" },
  paused: { tone: "amber", label: "Paused" },
  error: { tone: "red", label: "Error" },
  archived: { tone: "gray", label: "Archived" },
  // runs
  queued: { tone: "gray", label: "Queued" },
  running: { tone: "blue", label: "Running" },
  waiting_approval: { tone: "amber", label: "Waiting for approval" },
  succeeded: { tone: "green", label: "Succeeded" },
  failed: { tone: "red", label: "Failed" },
  cancelled: { tone: "gray", label: "Cancelled" },
  skipped: { tone: "gray", label: "Skipped" },
  waiting: { tone: "amber", label: "Waiting" },
  // approvals (Figure 4.10)
  pending: { tone: "amber", label: "Pending" },
  reminded: { tone: "amber", label: "Reminded" },
  approved: { tone: "green", label: "Approved" },
  edited: { tone: "green", label: "Edited & approved" },
  rejected: { tone: "red", label: "Rejected" },
  expired: { tone: "gray", label: "Expired" },
  // connections
  connected: { tone: "green", label: "Connected" },
  needs_attention: { tone: "red", label: "Needs attention" },
  disconnected: { tone: "gray", label: "Disconnected" },
  // interviews / opportunities
  in_progress: { tone: "blue", label: "In progress" },
  completed: { tone: "green", label: "Completed" },
  abandoned: { tone: "gray", label: "Abandoned" },
  suggested: { tone: "brand", label: "Suggested" },
  selected: { tone: "purple", label: "Being automated" },
  dismissed: { tone: "gray", label: "Dismissed" },
  automated: { tone: "green", label: "Automated" },
};

export function StatusBadge({ status, children }: { status: string; children?: ReactNode }) {
  const config = STATUS[status] ?? { tone: "gray" as Tone, label: status };
  return <Badge tone={config.tone}>{children ?? config.label}</Badge>;
}

export const APPROVAL_KIND: Record<string, { label: string; tone: Tone }> = {
  customer_message: { label: "Message to customer", tone: "blue" },
  money: { label: "Money", tone: "amber" },
  review: { label: "Check details", tone: "purple" },
  window_closed: { label: "WhatsApp window closed", tone: "red" },
};
