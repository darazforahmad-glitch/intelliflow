/** Zod schemas for forms (Section 5.5: input validated with Pydantic and Zod). */
import { z } from "zod";

const password = z
  .string()
  .min(8, "Use at least 8 characters.")
  .max(128)
  .regex(/[A-Za-z]/, "Add at least one letter.")
  .regex(/\d/, "Add at least one number.");

export const registerSchema = z.object({
  full_name: z.string().trim().min(2, "Please enter your full name.").max(100),
  email: z.email("Please enter a valid e-mail address."),
  phone: z
    .string()
    .trim()
    .regex(/^(\+?[0-9][0-9\s-]{6,19})?$/, "Use a phone number like 0300 1234567.")
    .optional(),
  password,
});

export const loginSchema = z.object({
  email: z.email("Please enter a valid e-mail address."),
  password: z.string().min(1, "Please enter your password."),
});

export const resetSchema = z
  .object({ password, confirm: z.string() })
  .refine((v) => v.password === v.confirm, { message: "The passwords do not match.", path: ["confirm"] });

export const workspaceSchema = z.object({
  name: z.string().trim().min(2, "Please enter your business name.").max(120),
  business_type: z.string().trim().max(60).optional(),
  language_pref: z.enum(["en", "ur", "roman-ur"]),
  timezone: z.string().min(3),
});

export const stepSchema = z.object({
  title: z.string().trim().min(2, "Give the step a short name.").max(150),
  actor: z.string().trim().min(1).max(80),
  step_type: z.enum(["start", "manual", "automated", "human_only", "end"]),
  app: z.string(),
  minutes_per_run: z.coerce.number().min(0).max(600),
  runs_per_week: z.coerce.number().int().min(0).max(10000),
});

export const whatsappConnectSchema = z.object({
  phone_number_id: z.string().regex(/^\d{5,40}$/, "Digits only, from Meta's WhatsApp Manager."),
  waba_id: z.string().regex(/^\d{5,40}$/, "Digits only."),
  access_token: z.string().min(20, "Paste the full access token."),
  display_phone_number: z.string().max(30).optional(),
});

export type FieldErrors = Record<string, string>;

/** Flatten a Zod error into {field: message} for inline form errors. */
export function fieldErrors(error: z.ZodError): FieldErrors {
  const out: FieldErrors = {};
  for (const issue of error.issues) {
    const key = issue.path.join(".") || "form";
    out[key] ??= issue.message;
  }
  return out;
}
