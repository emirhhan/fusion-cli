import { useEffect, useRef, useSyncExternalStore } from "react";
import type { SessionModel } from "../sessions/types";
import { osBildirimiGonder } from "./osNotice";
import { getNotificationPreferences, subscribeNotificationPreferences } from "./preferences";
import { playChime } from "./sound";
import { planNotifications, unreadTransitions, type OturumIzi, type PlanlananBildirim } from "./turnNotifier";
import { clearUnread, getUnread, markUnread, subscribeUnread } from "./unread";

export interface TurBildirimBagimliliklari {
  gonder: (bildirim: PlanlananBildirim) => Promise<unknown>;
  sesCal: () => void;
  odakta: () => boolean;
}

const varsayilan: TurBildirimBagimliliklari = {
  gonder: (bildirim) => osBildirimiGonder(bildirim.baslik, bildirim.metin, undefined, { odaktaDaGonder: bildirim.odaktaDaGonder }),
  sesCal: playChime,
  odakta: () => typeof document !== "undefined" && document.hasFocus() && document.visibilityState === "visible",
};

function iz(sessions: Record<string, SessionModel>): Record<string, OturumIzi> {
  const sonuc: Record<string, OturumIzi> = {};
  for (const [id, session] of Object.entries(sessions)) {
    sonuc[id] = { running: session.running, questionId: session.question?.id ?? null, title: session.title };
  }
  return sonuc;
}

/** Okunmamış sohbet kimliklerini canlı okuyan kanca. */
export function useUnread(): ReadonlySet<string> {
  return useSyncExternalStore(subscribeUnread, getUnread, getUnread);
}

/** Bildirim tercihlerini canlı okuyan kanca. */
export function useNotificationPreferences() {
  return useSyncExternalStore(subscribeNotificationPreferences, getNotificationPreferences, getNotificationPreferences);
}

/**
 * Oturum durumlarını izler; tur bitişi ve onay beklemede işletim sistemi bildirimi
 * gönderir, bakılmayan sohbeti okunmamış işaretler, seçilen sohbeti okunmuşa çevirir.
 */
export function useTurnNotifications(
  sessions: Record<string, SessionModel>,
  activeId: string | null,
  bag: TurBildirimBagimliliklari = varsayilan,
): void {
  const onceki = useRef<Record<string, OturumIzi> | null>(null);
  const bagRef = useRef(bag);
  bagRef.current = bag;
  const activeRef = useRef(activeId);
  activeRef.current = activeId;

  useEffect(() => {
    const simdi = iz(sessions);
    const previous = onceki.current;
    onceki.current = simdi;
    if (!previous) return;
    const bakis = { activeId, focused: bagRef.current.odakta() };
    const tercihler = getNotificationPreferences();
    markUnread(unreadTransitions(previous, simdi, bakis));
    const plan = planNotifications(previous, simdi, bakis, tercihler);
    if (plan.length === 0) return;
    if (tercihler.ses) bagRef.current.sesCal();
    for (const bildirim of plan) {
      void bagRef.current.gonder(bildirim).catch(() => undefined);
    }
  }, [sessions, activeId]);

  // Seçilen sohbet okunmuş sayılır; pencereye dönülünce de bakılan sohbet temizlenir.
  useEffect(() => {
    if (activeId && bagRef.current.odakta()) clearUnread(activeId);
    const odaklandi = () => {
      if (activeRef.current) clearUnread(activeRef.current);
    };
    window.addEventListener("focus", odaklandi);
    return () => window.removeEventListener("focus", odaklandi);
  }, [activeId]);
}
