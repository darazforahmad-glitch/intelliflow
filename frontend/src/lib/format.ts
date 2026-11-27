/** Formatting for Pakistan: DD/MM/YYYY dates, Asia/Karachi default, amounts in rupees. */

export function formatDate(value: string | Date | null | undefined, timeZone = "Asia/Karachi"): string {
  if (!value) return "—";
  const date = typeof value === "string" ? new Date(value) : value;
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone,
  }).format(date);
}

export function formatDateTime(value: string | Date | null | undefined, timeZone = "Asia/Karachi"): string {
  if (!value) return "—";
  const date = typeof value === "string" ? new Date(value) : value;
  const time = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", timeZone }).format(
    date,
  );
  return `${formatDate(date, timeZone)} ${time}`;
}

export function timeAgo(value: string | null | undefined): string {
  if (!value) return "never";
  const seconds = Math.round((Date.now() - new Date(value).getTime()) / 1000);
  if (seconds < 45) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return days === 1 ? "yesterday" : `${days} days ago`;
}

export function rupees(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const amount = typeof value === "string" ? Number(value.replace(/,/g, "")) : value;
  if (Number.isNaN(amount)) return String(value);
  return `Rs ${new Intl.NumberFormat("en-PK", { maximumFractionDigits: 0 }).format(amount)}`;
}

export function minutesLabel(minutes: number | string | null | undefined): string {
  const value = Number(minutes ?? 0);
  if (value >= 60) {
    const hours = value / 60;
    return `${hours.toFixed(hours >= 10 ? 0 : 1)} h`;
  }
  return `${Number.isInteger(value) ? value : value.toFixed(1)} min`;
}

export function humanize(value: string | null | undefined): string {
  if (!value) return "";
  return value.replace(/[._]/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

export const TRIGGER_LABELS: Record<string, string> = {
  "whatsapp.message_received": "New WhatsApp message",
  "gmail.message_received": "New e-mail in Gmail",
  "webform.submitted": "Website form submitted",
  "schedule.daily": "Every day at a set time",
  "schedule.interval": "Every few minutes",
  manual: "Started manually",
};

export const APP_LABELS: Record<string, string> = {
  whatsapp: "WhatsApp",
  excel: "Excel",
  google_sheets: "Google Sheets",
  gmail: "Gmail",
  paper: "Paper register",
  phone: "Phone",
  webform: "Web form",
  website: "Website",
  bank: "Bank / wallet",
  courier: "Courier",
  pos: "POS",
  other: "Other",
  none: "—",
};
