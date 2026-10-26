import { expect, test } from "@playwright/test";
import { signIn, signOut } from "./zitadel";

/** The doctor's and patient's screens against the real cloud: alerts and ECG from seed-dev, decoded
 * from the API's int16le-base64 chunks; an acknowledgement that persists; on-demand recording said
 * to be unavailable rather than faked. */
test("the doctor reads an alert's real ECG and acknowledges it; the patient then sees who did", async ({ page }) => {
  await signIn(page, "doctor1@medmusketeer.example");
  await expect(page).toHaveURL(/\/doctor\/dashboard$/);
  const performanceMarks = () => page.evaluate(() => performance.getEntriesByName("mm:dashboard-render").length);
  await expect(page.getByRole("table", { name: "Alerts" }).getByRole("row")).toHaveCount(4); // 3 unacknowledged
  expect(await performanceMarks()).toBe(3);

  await page.goto("/doctor/alerts");
  await page.getByRole("table", { name: "Alerts" }).getByRole("row", { name: /Ventricular ectopic/ }).getByRole("link").first().click();
  await expect(page.getByRole("img", { name: /10\.0 s at 360 Hz/ })).toBeVisible();
  await expect(page.getByRole("table", { name: "Classifications" }).getByRole("row")).toHaveCount(3);
  await page.getByRole("button", { name: "Acknowledge" }).click();
  await expect(page.getByText("Acknowledged by You")).toBeVisible();
  await page.reload();
  await expect(page.getByText("Acknowledged by You")).toBeVisible(); // stored by the API, not the page

  await page.getByRole("link", { name: /P-1001's page/ }).click();
  await expect(page.getByText("Fixed path, through a gateway")).toBeVisible();
  await expect(page.getByText("On-demand recording is not available yet")).toBeVisible();
  await expect(page.getByRole("table", { name: "ECG segments" }).getByRole("row")).toHaveCount(4);

  await signOut(page);
  await signIn(page, "patient1@medmusketeer.example");
  await expect(page).toHaveURL(/\/patient\/dashboard$/);
  await expect(page.getByText("Sarah Ahmed", { exact: true })).toBeVisible();
  await page.goto("/patient/alerts");
  const alerts = page.getByRole("table", { name: "Alerts" });
  await expect(alerts.getByRole("row")).toHaveCount(4);
  await expect(alerts.getByText(/^Sarah Ahmed, /)).toHaveCount(3); // all three: two seeded acknowledgements and the one above
  await expect(page.getByRole("button", { name: "Acknowledge" })).toHaveCount(0);
  await page.goto("/patient/ecg");
  await page.getByRole("table", { name: "ECG segments" }).getByRole("link").first().click();
  await expect(page.getByRole("img", { name: /10\.0 s at 360 Hz/ })).toBeVisible();
});
