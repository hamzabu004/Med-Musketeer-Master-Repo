"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** `reload` exists in every state, so a change made while a list is loading or failed still refreshes it. */
export type Resource<T> = { reload: () => void } & (
  | { status: "loading" }
  | { status: "error"; error: unknown }
  | { status: "ready"; data: T; refreshing: boolean; fetchedAt: number }
);

type Result<T> = { key: string; version: number } & ({ ok: true; data: T; fetchedAt: number } | { ok: false; error: unknown });

/** Loads data for a screen and reloads it on demand (after a change). While a reload runs, the
 * previous data stays on screen; when `deps` change (another record), it shows loading again. */
export function useResource<T>(load: () => Promise<T>, deps: readonly unknown[]): Resource<T> {
  const key = JSON.stringify(deps);
  const [version, setVersion] = useState(0);
  const [result, setResult] = useState<Result<T> | null>(null);
  const loader = useRef(load);
  useEffect(() => {
    loader.current = load;
  });

  useEffect(() => {
    let live = true;
    loader.current().then(
      (data) => live && setResult({ key, version, ok: true, data, fetchedAt: Date.now() }),
      (error: unknown) => live && setResult({ key, version, ok: false, error }),
    );
    return () => {
      live = false;
    };
  }, [key, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);

  if (!result || result.key !== key) return { status: "loading", reload };
  if (!result.ok) return result.version === version ? { status: "error", error: result.error, reload } : { status: "loading", reload };
  return { status: "ready", data: result.data, reload, refreshing: result.version !== version, fetchedAt: result.fetchedAt };
}
