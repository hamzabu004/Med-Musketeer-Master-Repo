import { randomBytes, randomUUID } from "node:crypto";
import { expect, test } from "@playwright/test";
import { redeemInvite, signIn, signOut } from "./zitadel";

/** The system admin's screens against the real cloud: every step is a real API call, and the new
 * organisation admin redeems the invite code in ZITADEL's login. */
test("organisation, its administrator through the invite code, and a device from registration to grant", async ({ page }) => {
  const stamp = Date.now();
  const orgName = `E2E Clinic ${stamp}`;
  const adminEmail = `admin${stamp}@e2e.example`;
  const deviceId = randomUUID();
  const fingerprint = randomBytes(32).toString("hex").toUpperCase(); // unique across devices, as the API requires

  await signIn(page, "sysadmin@medmusketeer.example");
  await expect(page).toHaveURL(/\/system\/dashboard$/);

  await page.goto("/system/organisations");
  await page.getByLabel("Name").fill(orgName);
  await page.getByRole("button", { name: "Create" }).click();
  await page.getByRole("link", { name: orgName }).click();
  await page.getByLabel("Given name").fill("Erin");
  await page.getByLabel("Family name").fill("Admin");
  await page.getByLabel("E-mail").fill(adminEmail);
  await page.getByRole("button", { name: "Create" }).click();
  const code = (await page.locator("code").textContent())!.trim();
  expect(code).toMatch(/^[A-Z0-9]{6,}$/);
  await page.getByRole("button", { name: "I have passed it on" }).click();
  await expect(page.getByRole("table", { name: "Administrators created" }).getByRole("row")).toHaveCount(2);

  await page.goto("/system/devices");
  await page.getByLabel("Device id").fill(deviceId);
  await page.getByRole("button", { name: "Register" }).click();
  await page.getByRole("link", { name: deviceId }).click();
  await page.getByLabel("SHA-256 fingerprint").fill(fingerprint.match(/../g)!.join(":").toLowerCase());
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByRole("cell", { name: fingerprint })).toBeVisible();
  await page.getByRole("button", { name: "Activate" }).click();
  await expect(page.getByText("Device activated")).toBeVisible();
  await page.getByLabel("Grant to").selectOption({ label: orgName });
  await page.getByRole("button", { name: "Grant" }).click();
  await expect(page.getByText("Granted to")).toContainText(orgName);

  await page.goto("/system/audit");
  const audit = page.getByRole("table", { name: "Audit log" });
  for (const action of ["Organisation created", "Account created", "Device registered", "Credential added", "Device active", "Grant created"]) {
    await expect(audit.getByRole("cell", { name: action, exact: true }).first()).toBeVisible();
  }

  // Attack tests are not served by the cloud yet: said so, not faked.
  await page.goto("/system/attack-tests");
  await expect(page.getByText("Attack testing is not available yet")).toBeVisible();

  await signOut(page);
  await redeemInvite(page, adminEmail, code, `Redeemed-${stamp}aA1!`);
  // A first sign-in: ZITADEL finishes the new session, then the callback exchanges the code.
  await expect(page).toHaveURL(/\/org\/dashboard$/, { timeout: 20_000 });
});
