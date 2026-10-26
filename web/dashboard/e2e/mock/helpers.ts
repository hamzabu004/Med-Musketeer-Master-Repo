import { expect, type Page } from "@playwright/test";

/** Compares with the device's width, not window.innerWidth: a phone browser widens its layout
 * viewport (zooms out) to fit wide content, so innerWidth grows with the overflow it should catch. */
export async function expectFitsViewport(page: Page) {
  const width = page.viewportSize()!.width;
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
}

export async function signInAs(page: Page, name: string) {
  await page.goto("/login");
  await page.getByRole("button", { name: new RegExp(name) }).click();
}
