"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { API_URL } from "./api";
import { useSession, useWorkspaceId } from "./session";

const INVALIDATIONS: Record<string, string[]> = {
  "run.updated": ["runs", "dashboard", "automations"],
  "approval.created": ["approvals", "dashboard", "runs"],
  "approval.decided": ["approvals", "dashboard", "runs"],
  "automation.updated": ["automations", "dashboard"],
};

/** Live dashboard updates over Server-Sent Events (REQ-DR-6). Returns the connection state. */
export function useLiveUpdates(): "connecting" | "live" | "offline" {
  const workspaceId = useWorkspaceId();
  const session = useSession();
  const client = useQueryClient();
  const [state, setState] = useState<"connecting" | "live" | "offline">("connecting");
  const token = session?.accessToken;

  useEffect(() => {
    if (!workspaceId || !token || typeof EventSource === "undefined") return;
    const url = `${API_URL}/api/v1/workspaces/${workspaceId}/events?access_token=${encodeURIComponent(token)}`;
    const source = new EventSource(url);
    source.onopen = () => setState("live");
    source.onerror = () => setState(source.readyState === EventSource.CLOSED ? "offline" : "connecting");
    source.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data as string) as { type: string };
        for (const part of INVALIDATIONS[message.type] ?? []) {
          void client.invalidateQueries({ queryKey: ["ws", workspaceId, part] });
        }
        void client.invalidateQueries({ queryKey: ["notifications"] });
      } catch {
        /* ignore malformed events */
      }
    };
    return () => source.close();
  }, [workspaceId, token, client]);

  return state;
}
