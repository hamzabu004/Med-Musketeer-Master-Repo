import { existsSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { ROLES, canAccessRoute, roleHome } from "@/auth/roles";
import { navigationByRole } from "./navigation";

const appDir = join(__dirname, "..", "app");

describe("navigation", () => {
  it.each(ROLES)("%s links only to pages that exist in its own area", (role) => {
    const items = navigationByRole[role];
    expect(items.map((item) => item.href)).toContain(roleHome(role));
    for (const item of items) {
      expect(canAccessRoute(role, item.href)).toBe(true);
      expect(existsSync(join(appDir, item.href, "page.tsx")), item.href).toBe(true);
    }
  });
});
