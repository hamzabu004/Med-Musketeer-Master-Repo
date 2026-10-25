import { expect, test } from "@playwright/test";

test("the sign-in page shows the product, not a demo", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "MedMusketeer" })).toBeVisible();
  await expect(page.getByText(/demo|simulated|POC/i)).toHaveCount(0);
});

for (const area of ["system", "org", "doctor", "patient"]) {
  test(`the ${area} area sends a signed-out visitor to sign in`, async ({ page }) => {
    await page.goto(`/${area}/dashboard`);
    await expect(page).toHaveURL(/\/login$/);
  });
}

test("the sign-in page has no horizontal scroll", async ({ page }) => {
  await page.goto("/login");
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});
