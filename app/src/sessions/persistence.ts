import type { SessionSource, SessionState } from "./types";

export const SESSION_VIEW_KEY = "fusion.session-view";
const SESSION_VIEW_VERSION = 1;

export interface PersistedSessionMetadata {
  id: string;
  title: string;
  source: SessionSource;
  root: string;
  updatedAt: number;
}

export interface PersistedSessionView {
  version: 1;
  activeId: string | null;
  sessions: PersistedSessionMetadata[];
}

type StorageLike = Pick<Storage, "getItem" | "setItem">;

function isSource(value: unknown): value is SessionSource {
  return value === "fusion" || value === "claude" || value === "codex" || value === "hermes";
}

function isMetadata(value: unknown): value is PersistedSessionMetadata {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return typeof item.id === "string"
    && typeof item.title === "string"
    && isSource(item.source)
    && typeof item.root === "string"
    && typeof item.updatedAt === "number"
    && Number.isFinite(item.updatedAt);
}

export function loadSessionView(storage: StorageLike): PersistedSessionView | null {
  try {
    const raw = storage.getItem(SESSION_VIEW_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    if (parsed.version !== SESSION_VIEW_VERSION || !Array.isArray(parsed.sessions)) return null;
    if (parsed.activeId !== null && typeof parsed.activeId !== "string") return null;
    if (!parsed.sessions.every(isMetadata)) return null;
    return parsed as unknown as PersistedSessionView;
  } catch {
    return null;
  }
}

export function saveSessionView(
  storage: StorageLike,
  state: SessionState,
  updatedAt = Date.now(),
): void {
  const view: PersistedSessionView = {
    version: SESSION_VIEW_VERSION,
    activeId: state.activeId,
    sessions: state.order.flatMap((id) => {
      const session = state.sessions[id];
      if (!session) return [];
      return [{
        id: session.id,
        title: session.title,
        source: session.source,
        root: session.root,
        updatedAt,
      }];
    }),
  };
  try {
    storage.setItem(SESSION_VIEW_KEY, JSON.stringify(view));
  } catch {
    // Gizli gezinme/kota gibi depolama hataları ürünün çalışmasını engellemez.
  }
}
