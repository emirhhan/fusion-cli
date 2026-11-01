import { useEffect, useRef } from "react";
import type { SessionModel } from "../sessions/types";
import {
  parseAction,
  SESSION_WINDOW_ACTION,
  SESSION_WINDOW_STATE,
  snapshotOf,
  tauriWindowEvents,
  type WindowEvents,
} from "./sessionWindowBridge";

export interface SessionWindowHandlers {
  send: (id: string, task: string) => void;
  answer: (id: string, data: Record<string, unknown>) => void;
  focus: (id: string) => void;
}

/**
 * Ana pencere tarafı (#443): açık sohbet pencerelerine durum yayar, onlardan gelen eylemi uygular.
 * `enabled` false ise (tarayıcı/test) hiçbir dinleyici kurulmaz.
 */
export function useSessionWindows(
  sessions: SessionModel[],
  handlers: SessionWindowHandlers,
  { enabled, events = tauriWindowEvents }: { enabled: boolean; events?: WindowEvents },
): void {
  const open = useRef(new Set<string>());
  const latest = useRef({ sessions, handlers });
  latest.current = { sessions, handlers };

  const publish = (id: string) => {
    const session = latest.current.sessions.find((item) => item.id === id);
    if (session) void events.emit(SESSION_WINDOW_STATE, snapshotOf(session)).catch(() => undefined);
  };

  useEffect(() => {
    if (!enabled) return;
    let stop: (() => void) | null = null;
    let active = true;
    void events.listen(SESSION_WINDOW_ACTION, (payload) => {
      const action = parseAction(payload);
      if (!action) return;
      const { handlers: current } = latest.current;
      if (action.tur === "hazir") { open.current.add(action.id); publish(action.id); }
      else if (action.tur === "kapandi") open.current.delete(action.id);
      else if (action.tur === "gonder") current.send(action.id, action.gorev);
      else if (action.tur === "cevap") current.answer(action.id, action.veri);
      else current.focus(action.id);
    }).then((unlisten) => { if (active) stop = unlisten; else unlisten(); })
      // Olay veriyolu yoksa (kabuk kapanıyor) pencere eşlemesi sessizce devre dışı kalır.
      .catch(() => undefined);
    return () => { active = false; stop?.(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, events]);

  useEffect(() => {
    if (!enabled) return;
    for (const id of open.current) publish(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, sessions]);
}
