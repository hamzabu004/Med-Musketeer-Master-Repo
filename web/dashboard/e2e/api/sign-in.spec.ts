import { expect, test } from "@playwright/test";
import { signIn } from "./zitadel";

/** Against a cloud stack seeded with seed-dev (scripts/api-e2e.sh): each role signs in through
 * ZITADEL's login (authorization code + PKCE), lands in its own area by the role /me reports, and
 * signs out of ZITADEL too. */
const roles = [
  { email: "sysadmin@medmusketeer.example", home: "/system/dashboard", foreign: "/org/accounts" },
  { email: "orgadmin@medmusketeer.example", home: "/org/dashboard", foreign: "/doctor/alerts" },
  { email: "doctor1@medmusketeer.example", home: "/doctor/dashboard", foreign: "/system/devices" },
  { email: "patient1@medmusketeer.example", home: "/patient/dashboard", foreign: "/doctor/patients" },
];

for (const role of roles) {
  test(`${role.email} signs in through ZITADEL and lands in their own area`, async ({ page }) => {
    const me = page.waitForResponse((response) => response.url().endsWith("/me") && response.request().method() === "GET");
    await signIn(page, role.email);
    await expect(page).toHaveURL(new RegExp(`${role.home}$`));
    expect((await me).status()).toBe(200);
    await expect(page.getByText("Sample data", { exact: true })).toHaveCount(0);

    // Tokens stay in sessionStorage, never localStorage.
    const stored = await page.evaluate(() => ({ local: JSON.stringify(localStorage), session: JSON.stringify(sessionStorage) }));
    expect(stored.local).not.toContain("access_token");
    expect(stored.session).toContain("access_token");

    await page.goto(role.foreign);
    await expect(page).toHaveURL(new RegExp(`${role.home}$`));
  });
}

test("the API answers the signed-in doctor with their own data, and refuses what D9 forbids", async ({ page }) => {
  await signIn(page, "doctor1@medmusketeer.example");
  await expect(page).toHaveURL(/\/doctor\/dashboard$/);
  const answers = await page.evaluate(async (api) => {
    const key = Object.keys(sessionStorage).find((k) => k.startsWith("oidc.user:"))!;
    const token = JSON.parse(sessionStorage.getItem(key)!).access_token as string;
    const get = (path: string) => fetch(`${api}${path}`, { headers: { Authorization: `Bearer ${token}` } });
    const alerts = await get("/alerts");
    return { alerts: (await alerts.json()).length, accounts: (await get("/accounts")).status, directory: (await get("/directory")).status };
  }, process.env.E2E_API_URL);
  expect(answers).toEqual({ alerts: 5, accounts: 403, directory: 200 }); // CORS lets the dashboard origin read the answers
});

test("signing out ends the ZITADEL session as well", async ({ page }) => {
  await signIn(page, "orgadmin@medmusketeer.example");
  await expect(page).toHaveURL(/\/org\/dashboard$/);
  await page.locator("summary", { hasText: "Open account menu" }).click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);

  // ZITADEL's login still lists the account it saw, but choosing it asks for the password again:
  // the session was ended, not just the dashboard's tokens dropped.
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("button", { name: /orgadmin@medmusketeer\.example/ }).click();
  await expect(page.getByTestId("password-text-input")).toBeVisible();
});
