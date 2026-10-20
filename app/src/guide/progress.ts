import { readStorage, writeStorage } from "../platform/storage";

export const GUIDE_PROGRESS_KEY = "fusion.guide.progress.v1";

/** Yalnız "gördüm" denenler tutulur; atlanan konu kaybolmaz, "bakılmadı" sayılır. */
export function readSeen(): ReadonlySet<string> {
  const result = readStorage(() => window.localStorage, GUIDE_PROGRESS_KEY);
  if (!result.ok || !result.value) return new Set();
  try {
    const value = JSON.parse(result.value) as { version?: unknown; seen?: unknown };
    if (value.version !== 1 || !Array.isArray(value.seen)) return new Set();
    return new Set(value.seen.filter((item): item is string => typeof item === "string"));
  } catch { return new Set(); }
}

export function markSeen(id: string): ReadonlySet<string> {
  const next = new Set(readSeen()).add(id);
  writeStorage(() => window.localStorage, GUIDE_PROGRESS_KEY, JSON.stringify({ version: 1, seen: [...next] }));
  return next;
}

export function pendingIds(ids: readonly string[], seen: ReadonlySet<string>): string[] {
  return ids.filter((id) => !seen.has(id));
}
