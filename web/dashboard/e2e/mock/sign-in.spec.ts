import { expect, test, type Page } from "@playwright/test";

async function signInAs(page: Page, name: string) {
  await page.goto("/login");
  await page.getByRole("button", { name: new RegExp(name) }).click();
}

const roles = [
  { name: "Sana Sysadmin", home: "/system/dashboard", nav: ["Organisations", "Devices", "Security Events"], foreign: "/doctor/alerts" },
  { name: "Omar Admin", home: "/org/dashboard", nav: ["Accounts", "Patients", "Devices"], foreign: "/system/devices" },
  { name: "Sarah Ahmed", home: "/doctor/dashboard", nav: ["Patients", "Alerts"], foreign: "/org/accounts" },
  { name: "Ali Khan", home: "/patient/dashboard", nav: ["Alerts", "ECG Recordings"], foreign: "/doctor/patients" },
];

test("the sign-in page says it shows sample data", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByText(/sample data/i)).toBeVisible();
  await expect(page.getByText(/demo|simulated|POC/i)).toHaveCount(0);
});

for (const role of roles) {
  test(`${role.name} lands in their own area and is kept out of others`, async ({ page, isMobile }) => {
    await signInAs(page, role.name);
    await expect(page).toHaveURL(new RegExp(`${role.home}$`));
    await expect(page.getByText("Sample data", { exact: true })).toBeVisible();
    if (isMobile) await page.getByRole("button", { name: "Open navigation" }).click();
    const nav = page.getByRole("navigation", { name: "Main navigation" });
    for (const item of role.nav) await expect(nav.getByRole("link", { name: item })).toBeVisible();

    await page.goto(role.foreign);
    await expect(page).toHaveURL(new RegExp(`${role.home}$`));
    await expect(page.getByRole("status")).toContainText("another role");
  });
}

test("a signed-in user who opens sign-in goes to their dashboard, and signing out returns to sign-in", async ({ page }) => {
  await signInAs(page, "Sarah Ahmed");
  await expect(page).toHaveURL(/\/doctor\/dashboard$/);
  await page.goto("/login");
  await expect(page).toHaveURL(/\/doctor\/dashboard$/);
  await page.locator("summary", { hasText: "Open account menu" }).click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/doctor/dashboard");
  await expect(page).toHaveURL(/\/login$/);
});

for (const area of ["system", "org", "doctor", "patient"]) {
  test(`the ${area} area sends a signed-out visitor to sign in`, async ({ page }) => {
    await page.goto(`/${area}/dashboard`);
    await expect(page).toHaveURL(/\/login$/);
  });
}

test("pages have no horizontal scroll", async ({ page }) => {
  for (const path of ["/login", "/invite"]) {
    await page.goto(path);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
  }
  await signInAs(page, "Omar Admin");
  await expect(page).toHaveURL(/\/org\/dashboard$/);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
});
