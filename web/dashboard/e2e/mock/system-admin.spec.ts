import { expect, test } from "@playwright/test";
import { expectFitsViewport, signInAs } from "./helpers";

test.beforeEach(async ({ page }) => {
  await signInAs(page, "Sana Sysadmin");
  await expect(page).toHaveURL(/\/system\/dashboard$/);
});

test("creates an organisation and its administrator, showing the invite code once", async ({ page }) => {
  await page.goto("/system/organisations");
  await page.getByLabel("Name").fill("Lakeside Clinic");
  await page.getByRole("button", { name: "Create" }).click();
  await expect(page.getByRole("status")).toContainText('Organisation "Lakeside Clinic" created.');
  await page.getByRole("link", { name: "Lakeside Clinic" }).click();

  await page.getByLabel("Given name").fill("Zara");
  await page.getByLabel("Family name").fill("Hussain");
  await page.getByLabel("E-mail").fill("zara@lakeside.example");
  await page.getByRole("button", { name: "Create" }).click();
  const code = page.locator("code");
  await expect(code).toHaveText(/^[A-Z2-9]{6}$/);
  await expect(page.getByText("shown only now", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "I have passed it on" }).click();
  await expect(code).toHaveCount(0); // gone for good: the API cannot return it again
  await expect(page.getByRole("table", { name: "Administrators created" }).getByRole("row")).toHaveCount(2);
});

test("registers a device, adds its certificate, activates it and grants it", async ({ page }) => {
  const deviceId = "7c9e6679-7425-40de-944b-e07fc1f90ae7";
  await page.goto("/system/devices");
  await page.getByLabel("Device id").fill(deviceId);
  await page.getByRole("button", { name: "Register" }).click();
  await expect(page.getByRole("status")).toContainText("Device registered");
  await page.getByRole("link", { name: deviceId }).click();

  await expect(page.getByRole("button", { name: "Activate" })).toBeDisabled(); // no credential yet
  await page.getByLabel("SHA-256 fingerprint").fill("not a fingerprint");
  await expect(page.getByText("A SHA-256 fingerprint has 64 hex digits.")).toBeVisible();
  await page.getByLabel("SHA-256 fingerprint").fill(Array.from({ length: 32 }, () => "ab").join(":"));
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByRole("cell", { name: "AB".repeat(32) })).toBeVisible();

  await page.getByRole("button", { name: "Activate" }).click();
  await expect(page.getByText("Device activated")).toBeVisible();
  await page.getByLabel("Grant to").selectOption({ label: "Northside Clinic" });
  await page.getByRole("button", { name: "Grant" }).click();
  await expect(page.getByText("Granted to")).toContainText("Northside Clinic");

  // Revoking the device (the lifecycle button, before the credentials' ones) asks first and says what follows.
  await page.getByRole("button", { name: "Revoke", exact: true }).first().click();
  await expect(page.getByRole("dialog")).toContainText("cannot be undone");
  await page.getByRole("dialog").getByRole("button", { name: "Cancel" }).click();
});

test("an attack test runs against a testbed device and its window is compared with the IDS events", async ({ page }) => {
  await page.goto("/system/attack-tests");
  const target = page.getByLabel("Target");
  await expect(target.locator("option")).not.toHaveCount(1); // testbed devices are offered
  await expect(target.locator("option", { hasText: /^Fixed gateway|^Wearable/ }).first()).toBeAttached();
  await target.selectOption({ index: 1 });
  await page.getByRole("button", { name: "Start" }).click();
  await expect(page.getByRole("table", { name: "Running attack tests" })).toBeVisible();
  await page.getByRole("button", { name: "Stop" }).click();
  await expect(page.getByText("No attack test running")).toBeVisible();
  await expect(page.getByRole("table", { name: "Attack test results" }).getByRole("row")).toHaveCount(3);
});

test("security events open a detail, and every system page fits the screen", async ({ page }) => {
  await page.goto("/system/security-events");
  await page.getByLabel("Mode").selectOption("ips");
  await expect(page.getByRole("table", { name: "Security events" }).getByRole("row")).toHaveCount(2);
  await page.getByRole("table", { name: "Security events" }).getByRole("button").first().click();
  await expect(page.getByRole("region", { name: "Security event detail" })).toContainText("IPS (prevention");

  for (const path of ["/system/dashboard", "/system/organisations", "/system/devices", "/system/security-events", "/system/audit", "/system/attack-tests", "/system/account"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 2 }).first()).toBeVisible();
    await expectFitsViewport(page);
  }
});

test("flags gateways behind the wearable revocation list, and a suspension raises its version", async ({ page }) => {
  await page.goto("/system/dashboard");
  await expect(page.getByText("Gateways behind the revocation list")).toBeVisible();
  await expect(page.getByText("List v2, published", { exact: false })).toBeVisible();

  await page.goto("/system/devices");
  const table = page.getByRole("table", { name: "Devices" });
  await expect(table.getByText("Current (v2)")).toHaveCount(1);
  await expect(table.getByText("Behind: v1 of v2")).toHaveCount(1);

  await table.getByRole("row").filter({ hasText: "Wearable" }).filter({ hasText: "Active" }).first().getByRole("link").click();
  await page.getByRole("button", { name: "Suspend" }).click();
  await expect(page.getByRole("dialog")).toContainText("revocation list");
  await page.getByRole("dialog").getByRole("button", { name: "Suspend" }).click();
  await expect(page.getByText("Device suspended.")).toBeVisible();

  await page.goto("/system/devices");
  await expect(table.getByText("Behind: v2 of v3")).toHaveCount(1); // the sample gateways never report
  await expect(table.getByText("Behind: v1 of v3")).toHaveCount(1);
});

