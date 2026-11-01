import { useEffect, useState } from "react";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { useShowSteps } from "../settings/useShowSteps";
import { SplitPane } from "./SplitPane";
import {
  parseState,
  SESSION_WINDOW_ACTION,
  SESSION_WINDOW_STATE,
  tauriWindowEvents,
  type SessionWindowAction,
  type SessionWindowState,
  type WindowEvents,
} from "./sessionWindowBridge";

/** Sohbet penceresi (#443): ana pencerenin sohbetini gösterir, eylemleri ona iletir. */
export function SessionWindow({
  id,
  events = tauriWindowEvents,
  closeWindow = () => getCurrentWindow().close(),
}: {
  id: string;
  events?: WindowEvents;
  closeWindow?: () => Promise<void> | void;
}) {
  const [state, setState] = useState<SessionWindowState | null>(null);
  const showSteps = useShowSteps();
  const send = (action: SessionWindowAction) => { void events.emit(SESSION_WINDOW_ACTION, action).catch(() => undefined); };

  useEffect(() => {
    let active = true;
    let stop: (() => void) | null = null;
    void events.listen(SESSION_WINDOW_STATE, (payload) => {
      const next = parseState(payload, id);
      if (next && active) setState(next);
    }).then((unlisten) => {
      if (!active) { unlisten(); return; }
      stop = unlisten;
      // Ana pencere hazır olduğumuzu duyunca anlık görüntüyü yollar.
      send({ id, tur: "hazir" });
    }).catch(() => undefined);
    const gone = () => send({ id, tur: "kapandi" });
    window.addEventListener("beforeunload", gone);
    return () => { active = false; stop?.(); window.removeEventListener("beforeunload", gone); gone(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, events]);

  useEffect(() => { if (state) document.title = state.title; }, [state]);

  if (!state) return <p className="split-pane__empty" role="status">Sohbet ana pencereden yükleniyor…</p>;
  return (
    <main className="session-window">
      <SplitPane
        onAnswer={(veri) => send({ id, tur: "cevap", veri })}
        onClose={() => void closeWindow()}
        onFocus={() => send({ id, tur: "odak" })}
        onSend={(gorev) => send({ id, tur: "gonder", gorev })}
        session={state}
        showSteps={showSteps}
      />
    </main>
  );
}
