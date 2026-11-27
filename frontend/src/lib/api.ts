/**
 * REST client for /api/v1: bearer tokens, single-flight token refresh, and errors
 * carrying the backend's plain-language message and hint.
 */
import type { TokenPair } from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

const SESSION_KEY = "intelliflow.session";
const WORKSPACE_KEY = "intelliflow.workspace";

export interface Session {
  accessToken: string;
  refreshToken: string;
  expiresAt: number;
  userId: string;
}

/* ------------------------------------------------------------------ tiny external stores */
type Listener = () => void;

function createStore<T>(key: string, parse: (raw: string) => T | null) {
  let value: T | null = null;
  let loaded = false;
  const listeners = new Set<Listener>();
  const emit = () => listeners.forEach((l) => l());

  function load(): T | null {
    if (loaded || typeof window === "undefined") return value;
    loaded = true;
    try {
      const raw = window.localStorage.getItem(key);
      value = raw ? parse(raw) : null;
    } catch {
      value = null;
    }
    // Keep tabs in sync: signing out in one tab signs out the others.
    window.addEventListener("storage", (event) => {
      if (event.key !== key) return;
      try {
        value = event.newValue ? parse(event.newValue) : null;
      } catch {
        value = null;
      }
      emit();
    });
    return value;
  }

  return {
    subscribe(listener: Listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    getSnapshot: (): T | null => load(),
    getServerSnapshot: (): T | null => null,
    set(next: T | null) {
      load();
      value = next;
      try {
        if (next === null) window.localStorage.removeItem(key);
        else window.localStorage.setItem(key, typeof next === "string" ? next : JSON.stringify(next));
      } catch {
        /* private mode: keep the in-memory value */
      }
      emit();
    },
  };
}

export const sessionStore = createStore<Session>(SESSION_KEY, (raw) => JSON.parse(raw) as Session);
export const workspaceStore = createStore<string>(WORKSPACE_KEY, (raw) => raw);

export function storeTokens(pair: TokenPair): void {
  sessionStore.set({
    accessToken: pair.access_token,
    refreshToken: pair.refresh_token,
    expiresAt: Date.now() + pair.expires_in * 1000,
    userId: pair.user.id,
  });
}

/* ------------------------------------------------------------------ errors */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly code?: string,
    public readonly hint?: string,
    public readonly details?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface ErrorBody {
  error?: { code?: string; message?: string; hint?: string; details?: unknown };
}

async function toApiError(response: Response): Promise<ApiError> {
  let body: ErrorBody = {};
  try {
    body = (await response.json()) as ErrorBody;
  } catch {
    /* not JSON */
  }
  const error = body.error ?? {};
  const fallback =
    response.status >= 500
      ? "Something went wrong on our side. Please try again."
      : "The request could not be completed.";
  return new ApiError(response.status, error.message ?? fallback, error.code, error.hint, error.details);
}

/* ------------------------------------------------------------------ refresh */
let refreshing: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  const current = sessionStore.getSnapshot();
  if (!current?.refreshToken) return false;
  if (!refreshing) {
    refreshing = (async () => {
      try {
        const response = await fetch(`${API_URL}/api/v1/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: current.refreshToken }),
        });
        if (!response.ok) {
          sessionStore.set(null);
          return false;
        }
        storeTokens((await response.json()) as TokenPair);
        return true;
      } catch {
        return false;
      } finally {
        queueMicrotask(() => {
          refreshing = null;
        });
      }
    })();
  }
  return refreshing;
}

/* ------------------------------------------------------------------ fetch */
export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  auth?: boolean;
  signal?: AbortSignal;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}, retried = false): Promise<T> {
  const auth = options.auth !== false;
  let session = auth ? sessionStore.getSnapshot() : null;
  if (session && session.expiresAt - Date.now() < 60_000 && !retried) {
    await refreshSession();
    session = sessionStore.getSnapshot();
  }
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (session) headers.Authorization = `Bearer ${session.accessToken}`;

  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/v1${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError(
      0,
      "Cannot reach IntelliFlow. Please check your internet connection.",
      "network_error",
    );
  }
  if (response.status === 401 && session && !retried && (await refreshSession())) {
    return apiFetch<T>(path, options, true);
  }
  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
  const type = response.headers.get("content-type") ?? "";
  return (type.includes("application/json") ? response.json() : response.text()) as Promise<T>;
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => apiFetch<T>(path, { signal }),
  post: <T>(path: string, body?: unknown) => apiFetch<T>(path, { method: "POST", body: body ?? {} }),
  put: <T>(path: string, body: unknown) => apiFetch<T>(path, { method: "PUT", body }),
  patch: <T>(path: string, body: unknown) => apiFetch<T>(path, { method: "PATCH", body }),
  del: <T>(path: string, body?: unknown) => apiFetch<T>(path, { method: "DELETE", body }),
  public: <T>(path: string, body?: unknown) =>
    apiFetch<T>(path, { method: body === undefined ? "GET" : "POST", body, auth: false }),
};

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.hint ? `${error.message} ${error.hint}` : error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

export function signOut(): void {
  sessionStore.set(null);
  if (typeof navigator !== "undefined" && navigator.serviceWorker?.controller) {
    navigator.serviceWorker.controller.postMessage({ type: "CLEAR_API_CACHE" });
  }
}
