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
  const explanations = useRef(readExplanationSeen(storage));
  const pending = useRef<{
    kind: PermissionKind;
    promise: Promise<boolean>;
    resolve: (granted: boolean) => void;
  } | null>(null);

  const resolvePending = useCallback((kind: PermissionKind, granted: boolean) => {
    if (pending.current?.kind !== kind) return;
    pending.current.resolve(granted);
    pending.current = null;
  }, []);

  const ensure = useCallback((kind: PermissionKind): Promise<boolean> => {
    if (state[kind] === "granted") return Promise.resolve(true);
    if (pending.current?.kind === kind) return pending.current.promise;

    let resolve!: (granted: boolean) => void;
    const promise = new Promise<boolean>((next) => { resolve = next; });
    pending.current = { kind, promise, resolve };
    setActiveKind(kind);
    setPhase(explanations.current[kind] ? state[kind] === "restricted" ? "restricted" : "denied" : "preflight");
    return promise;
  }, [state]);

  const request = useCallback(async (kind: PermissionKind) => {
    const next = await bridge.request(kind);
    setState((current) => ({ ...current, [kind]: next }));
    if (next === "granted") {
      setActiveKind(null);
      resolvePending(kind, true);
      return;
    }
    setActiveKind(kind);
    setPhase(next === "restricted" ? "restricted" : "denied");
    resolvePending(kind, false);
  }, [bridge, resolvePending]);

  const continuePermission = useCallback(async () => {
    if (!activeKind) return;
    explanations.current = { ...explanations.current, [activeKind]: true };
    saveExplanationSeen(storage, explanations.current);
    await request(activeKind);
  }, [activeKind, request, storage]);

  const retry = useCallback(async () => {
    if (activeKind) await request(activeKind);
  }, [activeKind, request]);

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
    openSettings,
  };
}
