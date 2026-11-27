import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const API = process.env.E2E_API_URL ?? "http://localhost:8000";
export const SHOTS = process.env.E2E_SCREENSHOTS; // optional folder for README screenshots

export const ANSWERS = [
  "Customer WhatsApp pe order bhejta hai. Phir main order details Excel register mein copy karta hoon. Uske baad payment screenshot check karta hoon. Phir customer ko confirmation message bhejta hoon. Phir staff order pack karta hai aur main TCS courier book karke tracking number customer ko bhejta hoon. Aakhir mein order deliver ho jata hai.",
  "Hafte mein taqreeban 40 orders aate hain.",
  "Excel mein copy karne mein 3 minute lagte hain, payment check mein 2 minute, confirmation bhejne mein 1 minute, packing 10 minute aur courier booking 5 minute.",
];

export const ORDER =
  "Assalam o alaikum, mujhe 2 kurtay chahiye medium size black colour. Address: House 12, Street 5, Gulberg Lahore. Total Rs 4500";

export async function shot(page: Page, name: string) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: false });
}

/** Register + verify through the dev outbox + sign in, all over the API. */
export async function apiOwner(request: APIRequestContext, email: string, password = "Secret123") {
  await request.post(`${API}/api/v1/auth/register`, { data: { full_name: "Ayesha Khan", email, password } });
  const outbox = await (await request.get(`${API}/api/v1/dev/outbox?to=${encodeURIComponent(email)}`)).json();
  const token = /token=([^\s]+)/.exec(outbox[0].body)![1];
  await request.post(`${API}/api/v1/auth/verify-email`, { data: { token } });
  const pair = await (await request.post(`${API}/api/v1/auth/login`, { data: { email, password } })).json();
  return pair as { access_token: string; refresh_token: string; expires_in: number; user: { id: string } };
}

export async function signInWithTokens(
  page: Page,
  pair: Awaited<ReturnType<typeof apiOwner>>,
  workspaceId: string,
) {
  await page.goto("/login");
  await page.evaluate(
    ([p, ws]) => {
      const pair = p as {
        access_token: string;
        refresh_token: string;
        expires_in: number;
        user: { id: string };
      };
      localStorage.setItem(
        "intelliflow.session",
        JSON.stringify({
          accessToken: pair.access_token,
          refreshToken: pair.refresh_token,
          expiresAt: Date.now() + pair.expires_in * 1000,
          userId: pair.user.id,
        }),
      );
      localStorage.setItem("intelliflow.workspace", ws as string);
    },
    [pair, workspaceId] as const,
  );
}

export async function expectToast(page: Page, text: RegExp | string) {
  await expect(page.getByRole("status").filter({ hasText: text }).first()).toBeVisible();
}
