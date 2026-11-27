"use client";

import { api } from "./api";

export async function registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return null;
  try {
    return await navigator.serviceWorker.register("/sw.js", { scope: "/" });
  } catch {
    return null;
  }
}

function urlBase64ToUint8Array(base64: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + padding).replace(/-/g, "+").replace(/_/g, "/"));
  const output = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i += 1) output[i] = raw.charCodeAt(i);
  return output;
}

export type PushState = "unsupported" | "disabled-on-server" | "denied" | "off" | "on";

export async function pushState(): Promise<PushState> {
  if (typeof window === "undefined" || !("PushManager" in window) || !("serviceWorker" in navigator))
    return "unsupported";
  const config = await api.get<{ enabled: boolean }>("/push/config");
  if (!config.enabled) return "disabled-on-server";
  if (Notification.permission === "denied") return "denied";
  const registration = await navigator.serviceWorker.getRegistration();
  const subscription = await registration?.pushManager.getSubscription();
  return subscription ? "on" : "off";
}

/** Ask permission and register this device for approval alerts (REQ-AP-2). */
export async function enablePush(): Promise<PushState> {
  const config = await api.get<{ enabled: boolean; vapid_public_key: string | null }>("/push/config");
  if (!config.enabled || !config.vapid_public_key) return "disabled-on-server";
  const permission = await Notification.requestPermission();
  if (permission !== "granted") return "denied";
  const registration = (await registerServiceWorker()) ?? (await navigator.serviceWorker.ready);
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(config.vapid_public_key),
  });
  const json = subscription.toJSON();
  await api.post("/push/subscriptions", { endpoint: json.endpoint, keys: json.keys });
  return "on";
}

export async function disablePush(): Promise<PushState> {
  const registration = await navigator.serviceWorker.getRegistration();
  const subscription = await registration?.pushManager.getSubscription();
  if (subscription) {
    await api.del("/push/subscriptions", { endpoint: subscription.endpoint });
    await subscription.unsubscribe();
  }
  return "off";
}
