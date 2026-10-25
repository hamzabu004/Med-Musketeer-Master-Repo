import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const replace = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }), usePathname: () => "/doctor/dashboard" }));

/** Sample mode, so the session needs no server. */
async function setup() {
  vi.stubEnv("NEXT_PUBLIC_DATA_SOURCE", "mock");
  vi.resetModules();
  const { SessionProvider, useSession } = await import("@/auth/session");
  const { RoleGuard } = await import("./role-guard");
  const { sampleWorld } = await import("@/services/mock/sample-session");
  return { SessionProvider, useSession, RoleGuard, sampleWorld };
}

beforeEach(() => {
  replace.mockClear();
  window.sessionStorage.clear();
});
afterEach(() => vi.unstubAllEnvs());

describe("RoleGuard", () => {
  it("sends a signed-out visitor to sign in", async () => {
    const { SessionProvider, RoleGuard } = await setup();
    render(<SessionProvider><RoleGuard role="doctor">doctor area</RoleGuard></SessionProvider>);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/login"));
    expect(screen.queryByText("doctor area")).toBeNull();
  });

  it("shows the area to its role and sends another role to its own dashboard", async () => {
    const { SessionProvider, useSession, RoleGuard, sampleWorld } = await setup();
    let signIn: (userId?: string) => Promise<void> = async () => {};
    function Capture() {
      signIn = useSession().signIn;
      return null;
    }
    const user = (key: string) => sampleWorld().users.find((u) => u.email.startsWith(`${key}@`))!.user_id;
    render(<SessionProvider><Capture /><RoleGuard role="doctor">doctor area</RoleGuard></SessionProvider>);

    await act(() => signIn(user("doctor1")));
    expect(await screen.findByText("doctor area")).toBeInTheDocument();

    await act(() => signIn(user("orgadmin")));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/org/dashboard"));
    expect(screen.queryByText("doctor area")).toBeNull();
  });
});
