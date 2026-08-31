import { useCallback, useRef, useState } from "react";
import type {
  PermissionBridge,
  PermissionKind,
  PermissionPromptPhase,
  PermissionState,
} from "./types";

export const EXPLANATION_SEEN_KEY = "fusion.permission-explanations.v1";

type ExplanationSeen = Partial<Record<PermissionKind, true>>;
type PermissionStates = Record<PermissionKind, PermissionState>;

const UNKNOWN_STATES: PermissionStates = {
  workspace: "unknown",
  microphone: "unknown",
  speech: "unknown",
  keychain: "unknown",
};

function readExplanationSeen(storage: Pick<Storage, "getItem">): ExplanationSeen {
  try {
    const raw = storage.getItem(EXPLANATION_SEEN_KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return {};
    return Object.fromEntries(
      Object.entries(parsed).filter(
        ([kind, seen]) => kind in UNKNOWN_STATES && seen === true,
      ),
    ) as ExplanationSeen;
  } catch {
    return {};
  }
}

function saveExplanationSeen(storage: Pick<Storage, "setItem">, seen: ExplanationSeen): void {
  storage.setItem(EXPLANATION_SEEN_KEY, JSON.stringify(seen));
}

export function usePermissions(
  bridge: PermissionBridge,
  storage: Storage = window.localStorage,
) {
  const [state, setState] = useState<PermissionStates>(UNKNOWN_STATES);
  const [activeKind, setActiveKind] = useState<PermissionKind | null>(null);
  const [phase, setPhase] = useState<PermissionPromptPhase>("preflight");
  const [hasQueuedPermission, setHasQueuedPermission] = useState(false);
  const states = useRef<PermissionStates>(UNKNOWN_STATES);
  const explanations = useRef(readExplanationSeen(storage));
  const pending = useRef(new Map<PermissionKind, {
    kind: PermissionKind;
    promise: Promise<boolean>;
    resolve: (granted: boolean) => void;
  }>());
  const queued = useRef<PermissionKind[]>([]);
  const active = useRef<PermissionKind | null>(null);
  const requestPermission = useRef<((kind: PermissionKind) => Promise<void>) | null>(null);

  const begin = useCallback((kind: PermissionKind) => {
    active.current = kind;
    setActiveKind(kind);
    setPhase("preflight");
    if (explanations.current[kind]) void requestPermission.current?.(kind);
  }, []);

  const beginNext = useCallback(() => {
    const following = queued.current.shift();
    setHasQueuedPermission(queued.current.length > 0);
    if (following) {
      begin(following);
      return;
    }
    active.current = null;
    setActiveKind(null);
  }, [begin]);

  const ensure = useCallback((kind: PermissionKind): Promise<boolean> => {
    if (states.current[kind] === "granted") return Promise.resolve(true);
    const existing = pending.current.get(kind);
    if (existing) return existing.promise;

    let resolve!: (granted: boolean) => void;
    const promise = new Promise<boolean>((next) => { resolve = next; });
    pending.current.set(kind, { kind, promise, resolve });
    if (active.current === null) begin(kind);
    else {
      queued.current.push(kind);
      setHasQueuedPermission(true);
    }
    return promise;
  }, [begin]);

  const request = useCallback(async (kind: PermissionKind) => {
    let next: PermissionState;
    try {
      next = await bridge.request(kind);
    } catch {
      next = "denied";
    }
    states.current = { ...states.current, [kind]: next };
    setState(states.current);
    const waiting = pending.current.get(kind);
    pending.current.delete(kind);
    waiting?.resolve(next === "granted");

    if (next === "granted") {
      beginNext();
      return;
    }
    active.current = kind;
    setActiveKind(kind);
    setPhase(next === "restricted" ? "restricted" : "denied");
  }, [beginNext, bridge]);

  requestPermission.current = request;

  const continuePermission = useCallback(async () => {
    if (!activeKind) return;
    explanations.current = { ...explanations.current, [activeKind]: true };
    saveExplanationSeen(storage, explanations.current);
    await request(activeKind);
  }, [activeKind, request, storage]);

  const retry = useCallback(async () => {
    if (activeKind) await request(activeKind);
  }, [activeKind, request]);

  const continueToNext = useCallback(() => {
    if (!activeKind || !hasQueuedPermission) return;
    beginNext();
  }, [activeKind, beginNext, hasQueuedPermission]);

  const openSettings = useCallback(async (kind: PermissionKind) => {
    await bridge.openSettings(kind);
  }, [bridge]);

  return {
    state,
    activeKind,
    phase,
    ensure,
    continue: continuePermission,
    retry,
    continueToNext,
    hasQueuedPermission,
    openSettings,
  };
}
