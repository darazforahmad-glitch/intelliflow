/// <reference lib="webworker" />
/**
 * IntelliFlow service worker (Workbox): installable offline shell, fast repeat loads
 * of the approvals PWA (PERF-6) and Web Push notifications for approvals (REQ-AP-2).
 * Built to public/sw.js by scripts/build-sw.mjs.
 */
import { ExpirationPlugin } from "workbox-expiration";
import { precacheAndRoute } from "workbox-precaching";
import { registerRoute, setCatchHandler } from "workbox-routing";
import { CacheFirst, NetworkFirst } from "workbox-strategies";

declare const self: ServiceWorkerGlobalScope;
declare const __API_URL__: string;
declare const __BUILD_ID__: string;

const API_CACHE = "api-approvals";

precacheAndRoute([
  { url: "/offline.html", revision: __BUILD_ID__ },
  { url: "/icons/icon-192.png", revision: __BUILD_ID__ },
]);

// Hashed, immutable Next.js assets.
registerRoute(
  ({ url }) => url.origin === self.location.origin && url.pathname.startsWith("/_next/static/"),
  new CacheFirst({
    cacheName: "next-static",
    plugins: [new ExpirationPlugin({ maxEntries: 250, maxAgeSeconds: 30 * 24 * 3600 })],
  }),
);

// Pages: network first, fall back to the last copy, then to the offline page.
registerRoute(
  ({ request }) => request.mode === "navigate",
  new NetworkFirst({
    cacheName: "pages",
    networkTimeoutSeconds: 4,
    plugins: [new ExpirationPlugin({ maxEntries: 40 })],
  }),
);

// The approvals list: show the last known list instantly on slow connections.
registerRoute(
  ({ url, request }) =>
    request.method === "GET" && url.href.startsWith(__API_URL__) && /\/approvals$/.test(url.pathname),
  new NetworkFirst({
    cacheName: API_CACHE,
    networkTimeoutSeconds: 3,
    plugins: [new ExpirationPlugin({ maxEntries: 20, maxAgeSeconds: 24 * 3600 })],
  }),
);

setCatchHandler(async ({ request }) => {
  if (request.destination === "document") {
    return (await caches.match("/offline.html")) ?? Response.error();
  }
  return Response.error();
});

self.addEventListener("install", () => void self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("message", (event) => {
  // Signing out wipes cached workspace data from this device.
  if (event.data?.type === "CLEAR_API_CACHE") event.waitUntil(caches.delete(API_CACHE));
});

interface PushPayload {
  title?: string;
  body?: string;
  url?: string;
  kind?: string;
}

self.addEventListener("push", (event) => {
  let data: PushPayload = {};
  try {
    data = (event.data?.json() as PushPayload) ?? {};
  } catch {
    data = { body: event.data?.text() };
  }
  event.waitUntil(
    self.registration.showNotification(data.title ?? "IntelliFlow", {
      body: data.body ?? "Something needs your attention.",
      icon: "/icons/icon-192.png",
      badge: "/icons/badge-72.png",
      tag: data.kind,
      data: { url: data.url ?? "/approvals" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url: string = event.notification.data?.url ?? "/approvals";
  event.waitUntil(
    (async () => {
      const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
      for (const client of windows) {
        if ("navigate" in client) {
          await (client as WindowClient).navigate(url);
          return (client as WindowClient).focus();
        }
      }
      return self.clients.openWindow(url);
    })(),
  );
});
