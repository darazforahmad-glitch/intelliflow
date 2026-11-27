"use client";

import clsx from "clsx";
import {
  Bell,
  Bot,
  ChevronDown,
  LayoutDashboard,
  LogOut,
  MessagesSquare,
  Plug,
  Settings,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { signOut } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { useLiveUpdates } from "@/lib/live";
import { useApprovals, useMarkAllRead, useNotifications } from "@/lib/queries";
import { selectWorkspace, useHydrated, useMe, useSession, useWorkspaceId } from "@/lib/session";

import { Logo, Wordmark } from "./logo";
import { Spinner } from "./ui";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/flow-mapper", label: "Flow Mapper", icon: Workflow },
  { href: "/automations", label: "Automations", icon: Bot },
  { href: "/approvals", label: "Approvals", icon: MessagesSquare },
  { href: "/integrations", label: "Integrations", icon: Plug },
  { href: "/settings", label: "Settings", icon: Settings },
];
const MOBILE_NAV = ["/dashboard", "/flow-mapper", "/approvals", "/automations", "/settings"];

function useActive() {
  const pathname = usePathname();
  return (href: string) => pathname === href || pathname.startsWith(`${href}/`);
}

function PendingBadge({ className }: { className?: string }) {
  const { data } = useApprovals("open");
  const count = data?.length ?? 0;
  if (!count) return null;
  return (
    <span
      className={clsx("rounded-full bg-amber-500 px-1.5 text-xs font-bold leading-5 text-white", className)}
      aria-label={`${count} waiting`}
    >
      {count}
    </span>
  );
}

function LiveDot() {
  const state = useLiveUpdates();
  return (
    <span className="flex items-center gap-1.5 text-xs text-slate-600" title="Dashboard updates arrive live">
      <span
        className={clsx(
          "size-2 rounded-full",
          state === "live" ? "bg-saved-500" : state === "connecting" ? "bg-amber-400" : "bg-slate-400",
        )}
      />
      {state === "live" ? "Live" : state === "connecting" ? "Connecting" : "Offline"}
    </span>
  );
}

function Notifications() {
  const { data } = useNotifications();
  const markAll = useMarkAllRead();
  const [open, setOpen] = useState(false);
  const unread = data?.unread ?? 0;
  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="relative grid size-11 place-items-center rounded-xl text-slate-600 hover:bg-slate-100"
        aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}
        aria-expanded={open}
      >
        <Bell className="size-5" />
        {unread ? (
          <span className="absolute right-2 top-2 size-2.5 rounded-full bg-red-500 ring-2 ring-white" />
        ) : null}
      </button>
      {open ? (
        <div className="absolute right-0 z-40 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-2xl border border-slate-200 bg-white shadow-xl">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
            <span className="font-semibold">Notifications</span>
            {unread ? (
              <button
                type="button"
                className="text-sm font-medium text-brand-700"
                onClick={() => markAll.mutate()}
              >
                Mark all read
              </button>
            ) : null}
          </div>
          <ul className="max-h-96 overflow-y-auto">
            {(data?.items ?? []).slice(0, 12).map((n) => (
              <li
                key={n.id}
                className={clsx("border-b border-slate-50 px-4 py-3 text-sm", !n.read && "bg-brand-50/50")}
              >
                <Link href={n.url ?? "/dashboard"} onClick={() => setOpen(false)} className="block">
                  <div className="font-medium text-slate-900">{n.title}</div>
                  <div className="line-clamp-2 text-slate-600">{n.body}</div>
                  <div className="mt-1 text-xs text-slate-500">{timeAgo(n.created_at)}</div>
                </Link>
              </li>
            ))}
            {!data?.items.length ? (
              <li className="px-4 py-6 text-center text-sm text-slate-500">You are all caught up.</li>
            ) : null}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function WorkspaceSwitcher() {
  const { data: me } = useMe();
  const workspaceId = useWorkspaceId();
  const memberships = me?.memberships.filter((m) => m.status === "active") ?? [];
  const current = memberships.find((m) => m.workspace_id === workspaceId);
  if (memberships.length <= 1) {
    return (
      <div className="min-w-0">
        <div className="truncate font-semibold text-slate-900">{current?.workspace_name ?? "—"}</div>
        <div className="text-xs capitalize text-slate-600">{current?.role}</div>
      </div>
    );
  }
  return (
    <label className="relative block min-w-0">
      <span className="sr-only">Workspace</span>
      <select
        value={workspaceId ?? ""}
        onChange={(e) => selectWorkspace(e.target.value)}
        className="w-full appearance-none truncate rounded-lg bg-transparent py-1 pr-6 font-semibold text-slate-900 focus:outline-none"
      >
        {memberships.map((m) => (
          <option key={m.workspace_id} value={m.workspace_id}>
            {m.workspace_name}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-0 top-2 size-4 text-slate-500" />
    </label>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const hydrated = useHydrated();
  const session = useSession();
  const me = useMe();
  const router = useRouter();
  const pathname = usePathname();
  const isActive = useActive();
  const activeMemberships = me.data?.memberships.filter((m) => m.status === "active") ?? [];
  const needsOnboarding = me.data && !activeMemberships.length && !me.data.is_platform_admin;

  useEffect(() => {
    if (hydrated && !session) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [hydrated, session, router, pathname]);
  useEffect(() => {
    if (needsOnboarding) router.replace("/onboarding");
  }, [needsOnboarding, router]);

  if (!hydrated || !session || me.isLoading || needsOnboarding) {
    return (
      <div className="grid min-h-dvh place-items-center">
        <Spinner label="Loading your workspace" />
      </div>
    );
  }

  const nav = me.data?.is_platform_admin
    ? [...NAV, { href: "/admin", label: "Platform admin", icon: ShieldCheck }]
    : NAV;

  return (
    <div className="min-h-dvh md:pl-64">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-white focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 hidden w-64 flex-col border-r border-slate-200 bg-white md:flex">
        <div className="px-5 py-5">
          <Link href="/dashboard" aria-label="IntelliFlow home">
            <Wordmark />
          </Link>
        </div>
        <div className="mx-3 rounded-xl border border-slate-200 px-3 py-2">
          <WorkspaceSwitcher />
        </div>
        <nav className="mt-4 flex-1 space-y-1 px-3" aria-label="Main">
          {nav.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              aria-current={isActive(href) ? "page" : undefined}
              className={clsx(
                "flex min-h-11 items-center gap-3 rounded-xl px-3 text-sm font-medium",
                isActive(href) ? "bg-brand-50 text-brand-700" : "text-slate-700 hover:bg-slate-50",
              )}
            >
              <Icon className="size-5" aria-hidden />
              <span className="flex-1">{label}</span>
              {href === "/approvals" ? <PendingBadge /> : null}
            </Link>
          ))}
        </nav>
        <div className="border-t border-slate-100 px-4 py-4">
          <div className="truncate text-sm font-medium text-slate-900">{me.data?.full_name}</div>
          <div className="truncate text-xs text-slate-600">{me.data?.email}</div>
          <button
            type="button"
            onClick={() => {
              signOut();
              router.replace("/login");
            }}
            className="mt-3 flex min-h-11 w-full items-center gap-2 rounded-xl px-3 text-sm font-medium text-slate-700 hover:bg-slate-100"
          >
            <LogOut className="size-4" aria-hidden /> Sign out
          </button>
        </div>
      </aside>

      {/* Top bar */}
      <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-slate-200 bg-white/90 px-4 backdrop-blur md:px-8">
        <Link href="/dashboard" className="md:hidden" aria-label="IntelliFlow home">
          <Logo />
        </Link>
        <div className="min-w-0 flex-1 md:hidden">
          <WorkspaceSwitcher />
        </div>
        <div className="hidden flex-1 md:block" />
        <LiveDot />
        <Notifications />
      </header>

      <main id="main" className="mx-auto max-w-7xl px-4 pb-28 pt-6 md:px-8 md:pb-12">
        {children}
      </main>

      {/* Phone bottom tab bar */}
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-slate-200 bg-white pb-[env(safe-area-inset-bottom)] md:hidden"
      >
        {MOBILE_NAV.map((href) => {
          const item = NAV.find((n) => n.href === href)!;
          const Icon = item.icon;
          return (
            <Link
              key={href}
              href={href}
              aria-current={isActive(href) ? "page" : undefined}
              className={clsx(
                "relative flex min-h-14 flex-col items-center justify-center gap-0.5 text-[11px] font-medium",
                isActive(href) ? "text-brand-700" : "text-slate-600",
              )}
            >
              <Icon className="size-5" aria-hidden />
              {item.label.replace("Flow Mapper", "Mapper")}
              {href === "/approvals" ? <PendingBadge className="absolute right-[18%] top-1.5" /> : null}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
