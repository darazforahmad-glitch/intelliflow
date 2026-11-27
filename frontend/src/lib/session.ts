"use client";

import { useQuery } from "@tanstack/react-query";
import { useSyncExternalStore } from "react";

import { api, sessionStore, workspaceStore } from "./api";
import type { Me } from "./types";

const noop = () => () => {};

/** True after hydration; localStorage-backed state is only trusted from then on. */
export function useHydrated(): boolean {
  return useSyncExternalStore(
    noop,
    () => true,
    () => false,
  );
}

export function useSession() {
  return useSyncExternalStore(
    sessionStore.subscribe,
    sessionStore.getSnapshot,
    sessionStore.getServerSnapshot,
  );
}

export function useMe() {
  const session = useSession();
  return useQuery({
    queryKey: ["me", session?.userId],
    queryFn: () => api.get<Me>("/auth/me"),
    enabled: Boolean(session),
    staleTime: 60_000,
  });
}

/** The selected workspace: the stored choice if still valid, else the first active membership. */
export function useWorkspaceId(): string | null {
  const stored = useSyncExternalStore(
    workspaceStore.subscribe,
    workspaceStore.getSnapshot,
    workspaceStore.getServerSnapshot,
  );
  const { data: me } = useMe();
  const memberships = me?.memberships.filter((m) => m.status === "active") ?? [];
  if (stored && memberships.some((m) => m.workspace_id === stored)) return stored;
  return memberships[0]?.workspace_id ?? null;
}

export function useMembership() {
  const workspaceId = useWorkspaceId();
  const { data: me } = useMe();
  return me?.memberships.find((m) => m.workspace_id === workspaceId) ?? null;
}

export function selectWorkspace(id: string): void {
  workspaceStore.set(id);
}
