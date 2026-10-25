export function mockDelay(ms = 280) {
  return new Promise<void>((resolve) => globalThis.setTimeout(resolve, ms));
}
