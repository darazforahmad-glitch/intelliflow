import { expect, test } from "@playwright/test";

import { ANSWERS, expectToast, shot } from "./helpers";

/**
 * UC-01 → UC-03 → UC-05 → UC-06 → UC-07 → UC-09 → UC-10 → UC-11:
 * a new owner goes from sign-up to an approved WhatsApp order on the dashboard.
 */
test("owner journey: interview, map, automate, test, activate, approve", async ({ page }) => {
  const email = `owner-${Date.now()}@example.com`;

  // UC-01 Register, verify, sign in
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Ayesha Khan");
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Password").fill("Secret123");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Check your e-mail" })).toBeVisible();
  await page.getByRole("link", { name: "Open the verification link" }).click();
  await expect(page.getByRole("heading", { name: "E-mail verified" })).toBeVisible();
  await page.getByRole("link", { name: "Continue to sign in" }).click();
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Password").fill("Secret123");
  await page.getByRole("button", { name: "Sign in" }).click();

  // REQ-AC-3 Create the workspace
  await expect(page.getByRole("heading", { name: "Set up your business" })).toBeVisible();
  await page.getByLabel("Business name").fill("Ayesha Boutique");
  await page.getByLabel("Type of business").fill("Online clothing seller");
  await page.getByRole("button", { name: "Create workspace" }).click();
  await page.getByRole("link", { name: "Start my first interview" }).click();

  // UC-03 Conduct the process interview (Roman Urdu)
  await page.getByLabel("Process name").fill("Order process");
  await page.getByRole("button", { name: "Start interview" }).click();
  await expect(page.getByText(/step by step batayein/)).toBeVisible();
  for (const answer of ANSWERS) {
    await page.getByRole("textbox", { name: "Your answer" }).fill(answer);
    await page.getByRole("button", { name: "Send answer" }).click();
    await expect(page.getByRole("textbox", { name: "Your answer" })).toHaveValue("");
  }
  await expect(page.getByText("I have enough detail")).toBeVisible();
  await shot(page, "01-interview");
  await page.getByRole("button", { name: "Done — draw my map" }).click();
  await expect(page.getByRole("heading", { name: "Top automation opportunities" })).toBeVisible();
  await expect(page.getByText("Copy order details into Excel").first()).toBeVisible();
  await expect(page.getByLabel("Process map of Order process")).toBeVisible();
  await shot(page, "02-process-map");

  // UC-05 → UC-07 Automate the order-entry opportunity; connections are required first
  const card = page.locator("div.relative.p-5", { hasText: "Order entry from WhatsApp" }).first();
  await card.getByRole("button", { name: "Automate this" }).click();
  await expect(
    card.getByText(/Connect (Google Sheets and WhatsApp|WhatsApp and Google Sheets) first/),
  ).toBeVisible();

  // UC-06 Connect sandbox apps
  await page.goto("/integrations");
  for (const title of ["WhatsApp Business", "Google Sheets"]) {
    const provider = page.locator("div.flex.flex-col.p-5", {
      has: page.getByRole("heading", { name: title }),
    });
    await provider.getByRole("button", { name: "Use sandbox" }).click();
    await expect(provider.getByText("sandbox", { exact: true })).toBeVisible();
  }

  await page.goto("/flow-mapper");
  await page.getByRole("link", { name: /Order process/ }).click();
  await page
    .locator("div.relative.p-5", { hasText: "Order entry from WhatsApp" })
    .first()
    .getByRole("button", { name: "Automate this" })
    .click();

  // Builder: validated draft, test, activate (BR-3)
  await expect(page.getByRole("heading", { name: "Order entry from WhatsApp" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Activate" })).toBeDisabled();
  await shot(page, "03-builder");
  await page.getByRole("radio", { name: "Test" }).click();
  await page.getByRole("button", { name: "Run test" }).click();
  await expect(page.getByText("Test passed", { exact: true })).toBeVisible();
  await shot(page, "04-test-run");
  await page.getByRole("button", { name: "Activate" }).click();
  await expectToast(page, "Automation is live.");

  // UC-10 A customer message arrives through the signed webhook gateway (worker processes it)
  await page.goto("/integrations");
  const whatsapp = page.locator("div.flex.flex-col.p-5", {
    has: page.getByRole("heading", { name: "WhatsApp Business" }),
  });
  await whatsapp.getByRole("button", { name: "Simulate a customer message" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Send" }).click();
  await expectToast(page, /webhook gateway/);

  // UC-11 Approve the drafted confirmation
  await page.goto("/approvals");
  await expect(page.getByText("Send this confirmation?").first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Customer wrote")).toBeVisible();
  await shot(page, "05-approvals");
  await page.getByRole("button", { name: "Approve", exact: true }).first().click();
  await expectToast(page, /Approved/);

  // UC-12 The dashboard shows the handled task
  await page.goto("/dashboard");
  await expect(page.getByText("Tasks handled")).toBeVisible();
  await expect(async () => {
    await page.reload();
    await expect(page.locator("text=Tasks handled").locator("..").locator("..")).toContainText("1");
  }).toPass({ timeout: 30_000 });
  await shot(page, "06-dashboard");
});
