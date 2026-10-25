import { expect, type Page } from "@playwright/test";

export const password = process.env.E2E_PASSWORD ?? "";

/** Fills a field of ZITADEL's login and submits. The login page is a React app: text typed before
 * it has hydrated is dropped and Continue stays disabled, so fill again until Continue enables. */
export async function fillAndContinue(page: Page, testId: string, value: string) {
  const submit = page.getByTestId("submit-button");
  await expect(async () => {
    await page.getByTestId(testId).fill(value);
    await expect(submit).toBeEnabled({ timeout: 1000 });
  }).toPass({ timeout: 20_000 });
  await submit.click();
}

export async function signIn(page: Page, email: string, secret = password) {
  await page.goto("/login");
  await page.getByRole("button", { name: "Sign in" }).click();
  await fillAndContinue(page, "username-text-input", email);
  await fillAndContinue(page, "password-text-input", secret);
}

/** Redeems an invite code in ZITADEL's login (checked against ZITADEL v4.20): e-mail, the code,
 * then "Password" and a new password. Ends back in the dashboard, signed in. */
export async function redeemInvite(page: Page, email: string, code: string, newPassword: string) {
  await page.goto("/login");
  await page.getByRole("button", { name: "Sign in" }).click();
  const another = page.getByRole("link", { name: "Add another account" });
  await expect(page.getByTestId("username-text-input").or(another)).toBeVisible();
  if (await another.isVisible()) await another.click();
  await fillAndContinue(page, "username-text-input", email);
  await fillAndContinue(page, "code-text-input", code);
  await page.getByRole("link", { name: /Password/ }).click();
  const submit = page.getByTestId("submit-button");
  await expect(async () => {
    await page.getByTestId("password-set-text-input").fill(newPassword);
    await page.getByTestId("password-set-confirm-text-input").fill(newPassword);
    await expect(submit).toBeEnabled({ timeout: 1000 });
  }).toPass({ timeout: 20_000 });
  await submit.click();
}

export async function signOut(page: Page) {
  await page.locator("summary", { hasText: "Open account menu" }).click();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
}
