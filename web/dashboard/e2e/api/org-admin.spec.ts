import { expect, test } from "@playwright/test";
import { redeemInvite, signIn, signOut } from "./zitadel";

/** The org admin's screens against the real cloud: names come from ZITADEL through /directory, every
 * change is a real API call, and the new patient redeems their invite code in ZITADEL's login. */
test("a patient from account to export, a doctor disabled, and the patient's first sign-in", async ({ page }) => {
  const stamp = Date.now();
  const pseudonym = `E2E-${stamp}`;
  const patientEmail = `patient${stamp}@e2e.example`;

  await signIn(page, "orgadmin@medmusketeer.example");
  await expect(page).toHaveURL(/\/org\/dashboard$/);
  await expect(page.getByRole("heading", { name: "Dev Hospital" })).toBeVisible();

  await page.goto("/org/accounts");
  await expect(page.getByRole("row", { name: /Sarah Ahmed/ })).toBeVisible(); // names from ZITADEL
  await page.getByLabel("Role").first().selectOption("patient");
  await page.getByLabel("Given name").fill("Erum");
  await page.getByLabel("Family name").fill("Patient");
  await page.getByLabel("E-mail").fill(patientEmail);
  await page.getByLabel("Pseudonym").fill(pseudonym);
  await page.getByRole("button", { name: "Create" }).click();
  const code = (await page.locator("code").textContent())!.trim();
  expect(code).toMatch(/^[A-Z0-9]{6,}$/);
  await page.getByRole("button", { name: "I have passed it on" }).click();

  // A doctor created and disabled in the same run, so the seeded doctors stay as they are.
  await page.getByLabel("Role").first().selectOption("doctor");
  await page.getByLabel("Given name").fill("Temp");
  await page.getByLabel("Family name").fill(`Doctor${stamp}`);
  await page.getByLabel("E-mail").fill(`doctor${stamp}@e2e.example`);
  await page.getByRole("button", { name: "Create" }).click();
  await page.getByRole("button", { name: "I have passed it on" }).click();
  const doctorRow = page.getByRole("row", { name: new RegExp(`Doctor${stamp}`) });
  await doctorRow.getByRole("button", { name: "Disable" }).click();
  await expect(page.getByRole("dialog")).toContainText("no patients at the moment");
  await page.getByRole("dialog").getByRole("button", { name: "Disable" }).click();
  await expect(doctorRow).toContainText("Disabled");

  await page.getByRole("link", { name: pseudonym }).click();
  await page.getByLabel("Assign a doctor").selectOption({ label: "Sarah Ahmed" });
  await page.getByRole("button", { name: "Assign" }).click();
  await expect(page.getByText("Cared for by")).toContainText("Sarah Ahmed");
  await page.getByLabel("Issue a wearable").selectOption({ index: 1 });
  await page.getByRole("button", { name: "Issue" }).click();
  await expect(page.getByRole("button", { name: "Return wearable" })).toBeVisible();
  await page.getByLabel("Record a disorder").fill("Sinus bradycardia");
  await page.getByRole("button", { name: "Record" }).click();
  await expect(page.getByRole("cell", { name: "Sinus bradycardia", exact: true })).toBeVisible();
  await page.getByLabel("Destination").fill("City Referral Hospital");
  await page.getByRole("button", { name: "Export" }).click();
  await expect(page.getByRole("region", { name: "Export" })).toContainText("1 disorder, 1 care assignment, 1 wearable assignment");

  const history = page.getByRole("table", { name: "Audit log" });
  for (const action of ["Account created", "Doctor assigned", "Wearable issued", "Disorder recorded", "Patient exported"]) {
    await expect(history.getByRole("cell", { name: action, exact: true })).toBeVisible();
  }

  await signOut(page);
  await redeemInvite(page, patientEmail, code, `Redeemed-${stamp}aA1!`);
  await expect(page).toHaveURL(/\/patient\/dashboard$/, { timeout: 20_000 });
});
