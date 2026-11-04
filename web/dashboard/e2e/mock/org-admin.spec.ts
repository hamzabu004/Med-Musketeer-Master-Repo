import { expect, test } from "@playwright/test";
import { expectFitsViewport, signInAs } from "./helpers";

test.beforeEach(async ({ page }) => {
  await signInAs(page, "Omar Admin");
  await expect(page).toHaveURL(/\/org\/dashboard$/);
});

test("creates a patient with a one-time invite code, then assigns a doctor, issues a wearable, records a disorder and exports", async ({ page }) => {
  await page.goto("/org/accounts");
  await page.getByLabel("Role").first().selectOption("patient");
  await page.getByLabel("Given name").fill("Hina");
  await page.getByLabel("Family name").fill("Butt");
  await page.getByLabel("E-mail").fill("hina@dev-hospital.example");
  await page.getByLabel("Pseudonym").fill("P-1004");
  await page.getByRole("button", { name: "Create" }).click();
  const code = page.locator("code");
  await expect(code).toHaveText(/^[A-Z2-9]{6}$/);
  await page.getByRole("button", { name: "I have passed it on" }).click();
  await expect(code).toHaveCount(0); // gone for good: the API cannot return it again

  await page.getByRole("link", { name: "P-1004" }).click();
  await expect(page.getByRole("heading", { name: "P-1004" })).toBeVisible();
  await expect(page.getByText("No doctor: no one sees")).toBeVisible();

  await page.getByLabel("Assign a doctor").selectOption({ label: "Bilal Raza" });
  await page.getByRole("button", { name: "Assign" }).click();
  await expect(page.getByText("Cared for by")).toContainText("Bilal Raza");

  await page.getByLabel("Issue a wearable").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Issue" }).click();
  await expect(page.getByRole("button", { name: "Return wearable" })).toBeVisible();

  await page.getByLabel("Record a disorder").fill("Sinus bradycardia");
  await page.getByRole("button", { name: "Record" }).click();
  await expect(page.getByRole("cell", { name: "Sinus bradycardia", exact: true })).toBeVisible();

  await page.getByLabel("Destination").fill("City Referral Hospital");
  await page.getByRole("button", { name: "Export" }).click();
  const exported = page.getByRole("region", { name: "Export" });
  await expect(exported).toContainText("City Referral Hospital");
  const download = page.waitForEvent("download");
  await exported.getByRole("button", { name: "Download JSON" }).click();
  expect((await download).suggestedFilename()).toMatch(/^P-1004-export-\d{4}-\d{2}-\d{2}\.json$/);

  // Every step is in the patient's history, by "You".
  const history = page.getByRole("table", { name: "Audit log" });
  for (const action of ["Account created", "Doctor assigned", "Wearable issued", "Disorder recorded", "Patient exported"]) {
    await expect(history.getByRole("cell", { name: action, exact: true })).toBeVisible();
  }
});

test("disabling a doctor names the patients who lose their doctor", async ({ page }) => {
  await page.goto("/org/accounts");
  const row = page.getByRole("row", { name: /Sarah Ahmed/ });
  await row.getByRole("button", { name: "Disable" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("2 patients (P-1001, P-1002) lose their doctor");
  await dialog.getByRole("button", { name: "Disable" }).click();
  await expect(row).toContainText("Disabled");
  await expect(row.getByRole("button", { name: "Disable" })).toHaveCount(0);

  await page.goto("/org/patients");
  await page.getByLabel("Show").selectOption("no_doctor");
  await expect(page.getByRole("table", { name: "Patients" }).getByRole("row")).toHaveCount(3); // header + P-1001, P-1002
  // Administrators cannot be disabled here (the system administrator manages them).
  await page.goto("/org/accounts");
  await expect(page.getByRole("row", { name: /Omar Admin/ }).getByRole("button")).toHaveCount(0);
});

test("returning a wearable frees it, and every organisation page fits the screen", async ({ page }) => {
  await page.goto("/org/patients");
  await page.getByRole("link", { name: "P-1001" }).click();
  await page.getByRole("button", { name: "Return wearable" }).click();
  await expect(page.getByRole("dialog")).toContainText("Monitoring ends");
  await page.getByRole("dialog").getByRole("button", { name: "Return wearable" }).click();
  await expect(page.getByLabel("Issue a wearable")).toBeVisible();

  await page.goto("/org/devices");
  await page.getByLabel("Type").selectOption("wearable");
  await expect(page.getByRole("table", { name: "Devices" }).getByRole("cell", { name: "Free" })).toHaveCount(3);

  for (const path of ["/org/dashboard", "/org/accounts", "/org/patients", "/org/devices", "/org/audit", "/org/account"]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 2 }).first()).toBeVisible();
    await expectFitsViewport(page);
  }
  await page.goto("/org/patients");
  await page.getByRole("link", { name: "P-1002" }).click();
  await expect(page.getByRole("heading", { name: "P-1002" })).toBeVisible();
  await expectFitsViewport(page);
});

test("the dashboard counts the organisation and lists who needs attention", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Dev Hospital" })).toBeVisible();
  await expect(page.getByText("Wearables issued")).toBeVisible();
  await expect(page.getByText("Patients without a wearable (1)")).toBeVisible(); // P-1003
  await page.getByRole("listitem").getByRole("link", { name: "P-1003" }).click();
  await expect(page.getByRole("heading", { name: "P-1003" })).toBeVisible();
});

test("the gateways page shows each gateway's uptime, wearables, alert times and connectivity log", async ({ page }) => {
  await page.goto("/org/gateways");
  await expect(page.getByRole("heading", { name: "Gateways" })).toBeVisible();
  const row = page.getByRole("table", { name: "Gateways" }).getByRole("row").nth(1);
  await expect(row.getByText("Online")).toBeVisible();
  await expect(row.getByText(/^Up 3 h 2\d min$/)).toBeVisible();
  await expectFitsViewport(page);

  await row.getByRole("link").click();
  await expect(page.getByRole("heading", { name: /^Fixed gateway / })).toBeVisible();
  await expect(page.getByRole("table", { name: "Connected wearables" }).getByRole("link", { name: "P-1001" })).toBeVisible();
  const alerts = page.getByRole("table", { name: "Alerts through this gateway" });
  await expect(alerts.getByRole("row")).toHaveCount(4); // header and P-1001's three
  await expect(alerts.getByText(/Ventricular|Confidence/)).toHaveCount(0); // times only (D9)
  const log = page.getByRole("table", { name: "Connectivity log" });
  await expect(log.getByText("Disconnected from the cloud")).toBeVisible();
  await page.getByLabel("Show").selectOption("wearable");
  await expect(log.getByText("Disconnected from the cloud")).toHaveCount(0);
  await expect(log.getByText("Mode switch")).toBeVisible();
  await expectFitsViewport(page);
});
