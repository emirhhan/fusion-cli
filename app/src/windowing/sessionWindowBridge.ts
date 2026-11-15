import { invoke } from "@tauri-apps/api/core";
import { emit as tauriEmit, listen as tauriListen } from "@tauri-apps/api/event";
import type { Mesaj } from "../screens/Conversation";
import type { SessionModel, SessionQuestion } from "../sessions/types";

/**
 * Sohbeti yeni pencerede aç (#443; Claude Desktop: Cmd-tık ya da Open in > New window).
 *
 * Çekirdek süreci ve oturum durumu ANA pencerede kalır. Sohbet penceresi bir görünümdür: ana
 * pencere oturumun anlık görüntüsünü `pencere://oturum-durumu` olayıyla yayar; pencere mesaj
 * gönderme, onay cevabı ve "ana pencerede aç" eylemlerini `pencere://oturum-eylemi` ile geri
 * yollar. Böylece iki pencere aynı çekirdeğe ayrı istemciyle yazıp istek kimliklerini
 * çakıştırmaz, zamanlayıcılar ve oturum yaşam döngüsü ikiye katlanmaz.
 */
export const SESSION_WINDOW_STATE = "pencere://oturum-durumu";
export const SESSION_WINDOW_ACTION = "pencere://oturum-eylemi";
const ID = /^[A-Za-z0-9_-]{1,128}$/;
/** Pencereye taşınan en çok mesaj (olay yükü sınırsız büyümesin). */
export const SESSION_WINDOW_MESSAGE_LIMIT = 400;

export interface SessionWindowState {
  id: string;
  title: string;
  running: boolean;
  status: SessionModel["status"];
  messages: Mesaj[];
  question: SessionQuestion | null;
}

export type SessionWindowAction =
  | { id: string; tur: "hazir" | "odak" | "kapandi" }
  | { id: string; tur: "gonder"; gorev: string }
  | { id: string; tur: "cevap"; veri: Record<string, unknown> };

export interface WindowEvents {
  emit(event: string, payload: unknown): Promise<void>;
  listen(event: string, handler: (payload: unknown) => void): Promise<() => void>;
}

export const tauriWindowEvents: WindowEvents = {
  emit: (event, payload) => tauriEmit(event, payload),
  listen: (event, handler) => tauriListen(event, (message) => handler(message.payload)),
};

/** Tauri kabuğunda mı? (Test taklitleri `isTauri`yi tanımlamadığı için iç işaretle bakılır.) */
export function inTauriShell(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export function sessionWindowId(search: string = window.location.search): string | null {
  const params = new URLSearchParams(search);
  const id = params.get("oturum");
  return params.get("pencere") === "oturum" && id && ID.test(id) ? id : null;
}

export async function openSessionWindow(id: string, title: string): Promise<void> {
  if (!ID.test(id)) throw new Error("Geçersiz sohbet kimliği.");
  await invoke("oturum_penceresi_ac", { oturumId: id, baslik: title });
}

export function snapshotOf(session: Pick<SessionModel, "id" | "title" | "running" | "status" | "messages" | "question">): SessionWindowState {
  return {
    id: session.id,
    title: session.title,
    running: session.running,
    status: session.status,
    messages: session.messages.slice(-SESSION_WINDOW_MESSAGE_LIMIT),
    question: session.question,
  };
}

/** Pencereden gelen eylemi doğrula; tanınmıyorsa `null`. */
export function parseAction(payload: unknown): SessionWindowAction | null {
  if (!payload || typeof payload !== "object") return null;
  const raw = payload as Record<string, unknown>;
  if (typeof raw.id !== "string" || !ID.test(raw.id)) return null;
  if (raw.tur === "hazir" || raw.tur === "odak" || raw.tur === "kapandi") return { id: raw.id, tur: raw.tur };
  if (raw.tur === "gonder" && typeof raw.gorev === "string" && raw.gorev.trim() && raw.gorev.length <= 100_000) {
    return { id: raw.id, tur: "gonder", gorev: raw.gorev };
  }
  if (raw.tur === "cevap" && raw.veri && typeof raw.veri === "object") {
    return { id: raw.id, tur: "cevap", veri: raw.veri as Record<string, unknown> };
  }
  return null;
}

/** Ana pencereden gelen durumu bu pencerenin oturumu için doğrula. */
export function parseState(payload: unknown, id: string): SessionWindowState | null {
  if (!payload || typeof payload !== "object") return null;
  const raw = payload as Record<string, unknown>;
  if (raw.id !== id || typeof raw.title !== "string" || !Array.isArray(raw.messages)) return null;
  const status = raw.status === "ready" || raw.status === "crashed" || raw.status === "closed" ? raw.status : "closed";
  return {
    id,
    title: raw.title,
    running: raw.running === true,
    status,
    messages: raw.messages as Mesaj[],
    question: (raw.question as SessionQuestion | null) ?? null,
  };
}
