import { expect, test } from "@playwright/test";
import { expectFitsViewport, signInAs } from "./helpers";

test.describe("doctor", () => {
  test.beforeEach(async ({ page }) => {
    await signInAs(page, "Sarah Ahmed");
    await expect(page).toHaveURL(/\/doctor\/dashboard$/);
  });

  test("opens an alert's ECG, acknowledges it, and it leaves the inbox", async ({ page }) => {
    await page.goto("/doctor/alerts");
    const inbox = page.getByRole("table", { name: "Alerts" });
    await expect(inbox.getByRole("row")).toHaveCount(4); // header + 3 unacknowledged (V, S, F)
    await inbox.getByRole("row", { name: /Ventricular ectopic/ }).getByRole("link").first().click();

    await expect(page.getByRole("heading", { name: "Ventricular ectopic (V)" })).toBeVisible();
    await expect(page.getByRole("img", { name: /Alert segment.*10\.0 s at 360 Hz, 25 mm\/s and 10 mm\/mV/ })).toBeVisible();
    await expect(page.getByRole("table", { name: "Classifications" }).getByRole("row")).toHaveCount(3); // wearable screen + gateway class
    await page.getByRole("button", { name: "Acknowledge" }).click();
    await expect(page.getByText("Acknowledged by You")).toBeVisible();

    await page.goto("/doctor/alerts");
    await expect(inbox.getByRole("row")).toHaveCount(3);
    await page.getByLabel("Show").selectOption("all");
    await expect(inbox.getByText("You, just now")).toBeVisible();
  });

  test("records the dashboard-render checkpoint for each alert drawn", async ({ page }) => {
    await expect(page.getByRole("table", { name: "Alerts" })).toBeVisible();
    const marks = await page.evaluate(() => performance.getEntriesByName("mm:dashboard-render").map((m) => (m as PerformanceMark).detail.alert_id));
    expect(marks).toHaveLength(3);
    expect(new Set(marks).size).toBe(3);
  });

  test("requests an on-demand recording and views it once recorded", async ({ page }) => {
    await page.goto("/doctor/patients");
    await page.getByRole("link", { name: "P-1002" }).click();
    await page.getByLabel("Length").selectOption("10");
    await page.getByRole("button", { name: "Request recording" }).click();
    await expect(page.getByText("Sent to the wearable").or(page.getByText("Recording", { exact: true }))).toBeVisible();
    await expect(page.getByRole("button", { name: "Recording in progress" })).toBeDisabled();
    await expect(page.getByText("Recorded", { exact: true })).toBeVisible({ timeout: 25_000 });
    await page.getByRole("link", { name: "View ECG" }).first().click();
    await expect(page.getByRole("heading", { name: "On-demand recording" })).toBeVisible();
    await expect(page.getByRole("img", { name: /10\.0 s at 360 Hz/ })).toBeVisible();
  });

  test("sees only their own patients, and every doctor page fits the screen", async ({ page }) => {
    await page.goto("/doctor/patients");
    await expect(page.getByRole("table", { name: "Patients" }).getByRole("row")).toHaveCount(3); // P-1001, P-1002
    await page.goto(`/doctor/patients/${"0001daa8-0003-4000-8000-000000000003"}`); // P-1003 is Bilal Raza's patient
    await expect(page.getByText("Not found, or not available to you.")).toBeVisible();

    for (const path of ["/doctor/dashboard", "/doctor/alerts", "/doctor/patients", "/doctor/account"]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 2 }).first()).toBeVisible();
      await expectFitsViewport(page);
    }
    await page.goto("/doctor/patients");
    await page.getByRole("link", { name: "P-1001" }).click();
    await expect(page.getByRole("heading", { name: "P-1001" })).toBeVisible();
    await expectFitsViewport(page);
    await page.getByRole("table", { name: "ECG segments" }).getByRole("link").first().click();
    await expect(page.getByRole("figure")).toBeVisible();
    await expectFitsViewport(page);
  });
});

test.describe("patient", () => {
  test.beforeEach(async ({ page }) => {
    await signInAs(page, "Ali Khan");
    await expect(page).toHaveURL(/\/patient\/dashboard$/);
  });

  test("sees their doctor, their own alerts read-only, and their ECG", async ({ page }) => {
    await expect(page.getByText("Sarah Ahmed", { exact: true })).toBeVisible(); // their doctor, from the directory
    await expect(page.getByText("not a medical device")).toBeVisible();
    await page.goto("/patient/alerts");
    const alerts = page.getByRole("table", { name: "Alerts" });
    await expect(alerts.getByRole("row")).toHaveCount(4); // their 3 alerts
    await expect(page.getByRole("button", { name: "Acknowledge" })).toHaveCount(0);
    await expect(alerts.getByText(/Sarah Ahmed, /).first()).toBeVisible(); // acknowledged by their doctor

    await page.goto("/patient/ecg");
    await expect(page.getByRole("table", { name: "ECG segments" }).getByRole("row")).toHaveCount(5); // 3 alert segments + 1 recording
    await page.getByRole("row", { name: /On-demand recording/ }).getByRole("link").click();
    await expect(page.getByRole("img", { name: /30\.0 s at 360 Hz/ })).toBeVisible();

    for (const path of ["/patient/dashboard", "/patient/alerts", "/patient/ecg", "/patient/account"]) {
      await page.goto(path);
      await expect(page.getByRole("heading", { level: 2 }).first()).toBeVisible();
      await expectFitsViewport(page);
    }
  });
});
