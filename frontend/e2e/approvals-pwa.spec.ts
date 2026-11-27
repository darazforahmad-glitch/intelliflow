import { expect, test } from "@playwright/test";

import { API, apiOwner, ORDER, shot, signInWithTokens } from "./helpers";

test.use({ viewport: { width: 360, height: 740 } }); // REQ-AP-7: usable at 360 px

test("staff-sized phone: edit and approve a reply from the PWA", async ({ page, request }) => {
  const pair = await apiOwner(request, `phone-${Date.now()}@example.com`);
  const headers = { Authorization: `Bearer ${pair.access_token}` };
  const ws = await (
    await request.post(`${API}/api/v1/workspaces`, {
      headers,
      data: { name: "Phone Shop", language_pref: "roman-ur" },
    })
  ).json();
  const base = `${API}/api/v1/workspaces/${ws.id}`;
  await request.post(`${base}/connections/sandbox`, { headers, data: { provider: "whatsapp" } });
  const automation = await (
    await request.post(`${base}/automations/from-template`, {
      headers,
      data: { template_code: "order_confirmation_reply" },
    })
  ).json();
  await request.post(`${base}/automations/${automation.id}/test`, {
    headers,
    data: { sample: { text: ORDER, name: "Ayesha" } },
  });
  expect(
    (await request.post(`${base}/automations/${automation.id}/activate`, { headers })).ok(),
  ).toBeTruthy();
  const whatsapp = (await (await request.get(`${base}/connections`, { headers })).json())[0];
  await request.post(`${base}/connections/${whatsapp.id}/simulate`, {
    headers,
    data: { text: ORDER, name: "Ayesha" },
  });

  await signInWithTokens(page, pair, ws.id);
  await page.goto("/approvals");
  const card = page.getByText("Send this confirmation?").first();
  await expect(card).toBeVisible({ timeout: 30_000 });
  // Bottom tab bar instead of the sidebar on phones
  await expect(page.getByRole("navigation", { name: "Main" }).last()).toBeVisible();
  const approve = page.getByRole("button", { name: "Approve", exact: true }).first();
  const box = await approve.boundingBox();
  expect(box!.height).toBeGreaterThanOrEqual(44); // 44 px touch targets
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy(); // no sideways scroll
  await shot(page, "07-phone-approval");

  await page.getByRole("button", { name: "Edit" }).first().click();
  await page.getByLabel("Message").fill("Shukriya Ayesha! Aap ka order confirm ho gaya hai.");
  await page.getByRole("button", { name: "Approve with changes" }).click();
  await expect(page.getByText("Nothing to approve")).toBeVisible({ timeout: 15_000 });

  const outbox = await (await request.get(`${base}/connections/${whatsapp.id}/sandbox`, { headers })).json();
  await expect
    .poll(
      async () =>
        (await (await request.get(`${base}/connections/${whatsapp.id}/sandbox`, { headers })).json()).outbox
          .length,
      { timeout: 15_000 },
    )
    .toBeGreaterThan(0);
  expect(outbox).toBeDefined();
});
