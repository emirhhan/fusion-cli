import { useSyncExternalStore } from "react";

/**
 * Sohbet görünüm kipleri (#444; Claude Desktop: Verbose / Normal / Summary, Ctrl+O döndürür).
 *
 * - `verbose` (Ayrıntılı): bütün araç adımları açık; biten çalışma blokları da açık gelir.
 * - `normal`: bugünkü görünüm; biten çalışma tek satırlık katlanmış özet.
 * - `summary` (Özet): biten çalışma blokları gizlenir, yalnız sonuçlar kalır.
 *
 * Tercih tarayıcı deposundadır; depo düşerse bu pencerede yine uygulanır.
 */
export type ViewMode = "verbose" | "normal" | "summary";
export const VIEW_MODE_STORAGE_KEY = "fusion.conversation.view-mode";
export const VIEW_MODES: readonly ViewMode[] = ["normal", "verbose", "summary"];
export const VIEW_MODE_LABELS: Record<ViewMode, string> = {
  verbose: "Ayrıntılı (Verbose)",
  normal: "Normal",
  summary: "Özet (Summary)",
};

const listeners = new Set<() => void>();
let current: ViewMode | null = null;

function isViewMode(value: unknown): value is ViewMode {
  return value === "verbose" || value === "normal" || value === "summary";
}

export function readViewMode(storage: Pick<Storage, "getItem"> = localStorage): ViewMode {
  try {
    const value = storage.getItem(VIEW_MODE_STORAGE_KEY);
    return isViewMode(value) ? value : "normal";
  } catch {
    return "normal";
  }
}

export function getViewMode(): ViewMode {
  if (current === null) current = readViewMode();
  return current;
}

export function setViewMode(mode: ViewMode): void {
  current = mode;
  try {
    localStorage.setItem(VIEW_MODE_STORAGE_KEY, mode);
  } catch {
    // Kalıcılaşmasa da bu pencerede uygulanır.
  }
  for (const listener of listeners) listener();
}

/** Ctrl+O: Normal → Ayrıntılı → Özet → Normal. Yeni kipi döndürür. */
export function cycleViewMode(): ViewMode {
  const index = VIEW_MODES.indexOf(getViewMode());
  const next = VIEW_MODES[(index + 1) % VIEW_MODES.length];
  setViewMode(next);
  return next;
}

export function subscribeViewMode(listener: () => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function useViewMode(): ViewMode {
  return useSyncExternalStore(subscribeViewMode, getViewMode, getViewMode);
}

/** Testlerin depoyu sıfırlaması için. */
export function resetViewModeCache(): void {
  current = null;
}
