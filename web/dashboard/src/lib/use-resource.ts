"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type Resource<T> =
  | { status: "loading" }
  | { status: "error"; error: unknown; reload: () => void }
  | { status: "ready"; data: T; reload: () => void; refreshing: boolean };

type Result<T> = { key: string; version: number } & ({ ok: true; data: T } | { ok: false; error: unknown });

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
      (data) => live && setResult({ key, version, ok: true, data }),
      (error: unknown) => live && setResult({ key, version, ok: false, error }),
    );
    return () => {
      live = false;
    };
  }, [key, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);

  if (!result || result.key !== key) return { status: "loading" };
  if (!result.ok) return result.version === version ? { status: "error", error: result.error, reload } : { status: "loading" };
  return { status: "ready", data: result.data, reload, refreshing: result.version !== version };
}
