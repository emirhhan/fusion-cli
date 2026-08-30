import { useCallback, useEffect, useMemo, useReducer, useRef } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { ProtocolClient } from "../protocol/client";
import { olayMetni } from "../protocol/olayMetni";
import type { Soru } from "../protocol/types";
import { initialSessionState, sessionReducer } from "./store";
import { loadSessionView, saveSessionView } from "./persistence";
import { isProjectRoot, projectName } from "./projectRoots";
import type {
  BackendSessionSnapshot,
  NewSession,
  ResumeSession,
  SessionClosedEvent,
  SessionLineEvent,
  SessionAttachment,
  SessionTransport,
} from "./types";

const DEFAULT_SESSION_ID = "varsayilan";
const CORE_CLOSED = "Bu konuşmanın çekirdeği beklenmedik şekilde kapandı.";

export const tauriSessionTransport: SessionTransport = {
  create: (id, root) =>
    invoke<BackendSessionSnapshot>("oturum_olustur", {
      oturumId: id,
      kok: root ?? null,
    }),
  send: (id, line) => invoke("oturuma_yaz", { oturumId: id, satir: line }),
  close: (id) => invoke("oturum_kapat", { oturumId: id }),
  list: () => invoke<BackendSessionSnapshot[]>("oturumlari_listele"),
  onLine: (handler) =>
    listen<SessionLineEvent>("oturum-satir", (event) => handler(event.payload)),
  onClosed: (handler) =>
    listen<SessionClosedEvent>("oturum-kapandi", (event) => handler(event.payload)),
};

function nextSessionId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `oturum-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function useSessions(transport: SessionTransport = tauriSessionTransport) {
  const [state, dispatch] = useReducer(sessionReducer, initialSessionState);
  const persistedView = useRef(
    typeof window === "undefined" ? null : loadSessionView(window.localStorage),
  );
  const clients = useRef(new Map<string, ProtocolClient>());
  const lineHandlers = useRef(new Map<string, (line: string) => void>());
  const requestedClose = useRef(new Set<string>());
  const mounted = useRef(false);

  const connect = useCallback(
    async (input: NewSession = {}, publish = true) => {
      const id = input.id ?? nextSessionId();
      requestedClose.current.delete(id);
      const existing = clients.current.get(id);
      if (existing) {
        if (publish) dispatch({ type: "selected", id });
        return { id, client: existing, snapshot: null };
      }

      const snapshot = await transport.create(id, input.root);
      if (!mounted.current) throw new Error("Oturum görünümü kapandı.");
      const client = new ProtocolClient(
        (line) => {
          void transport.send(id, line).catch((reason) => {
            const message = String(reason);
            client.close(message);
            dispatch({ type: "crashed", id, reason: message });
          });
        },
        (handler) => lineHandlers.current.set(id, handler),
      );
      client.onEvent((event) => {
        const text = olayMetni(event);
        if (text) {
          dispatch({ type: "messageAdded", id, message: { rol: "olay", metin: text } });
        }
      });
      client.onQuestion((questionId, data) => {
        if (data.tur === "onay") {
          dispatch({
            type: "questionChanged",
            id,
            question: { id: questionId, data: data as unknown as Soru },
          });
        }
      });
      clients.current.set(id, client);
      if (publish) {
        dispatch({
          type: "created",
          session: {
            id,
            title: input.title ?? "Yeni görev",
            source: input.source ?? "fusion",
            root: snapshot.kok,
            pid: snapshot.pid,
            client,
          },
        });
      }
      return { id, client, snapshot };
    },
    [transport],
  );

  const create = useCallback(
    async (input: NewSession = {}) => (await connect(input)).id,
    [connect],
  );

  const resume = useCallback(
    async (input: ResumeSession) => {
      const connection = await connect(
        {
          title: `[${input.source}] ${input.title}`,
          source: input.source,
          root: input.root,
        },
        false,
      );
      if (!connection.snapshot) {
        throw new Error("Devralma için yeni bir konuşma oluşturulamadı.");
      }
      try {
        const result = await connection.client.request("gecmis.surdur", {
          kaynak: input.source,
          oturum_id: input.sessionId,
        });
        if (result.ok !== true) {
          throw new Error(typeof result.metin === "string" ? result.metin : "Geçmiş devralınamadı.");
        }
        dispatch({
          type: "created",
          session: {
            id: connection.id,
            title: `[${input.source}] ${input.title}`,
            source: input.source,
            root: connection.snapshot.kok,
            pid: connection.snapshot.pid,
            client: connection.client,
          },
        });
        return {
          id: connection.id,
          secretCount: typeof result.sir_sayisi === "number" ? result.sir_sayisi : 0,
        };
      } catch (reason) {
        connection.client.close();
        clients.current.delete(connection.id);
        lineHandlers.current.delete(connection.id);
        requestedClose.current.add(connection.id);
        await transport.close(connection.id).catch(() => undefined);
        throw reason;
      }
    },
    [connect, transport],
  );

  useEffect(() => {
    mounted.current = true;
    let active = true;
    let unlistenLine: (() => void) | null = null;
    let unlistenClosed: (() => void) | null = null;

    const install = async () => {
      try {
        const listeners = await Promise.all([
          transport.onLine((event) => lineHandlers.current.get(event.oturum_id)?.(event.satir)),
          transport.onClosed((event) => {
            const client = clients.current.get(event.oturum_id);
            client?.close(CORE_CLOSED);
            clients.current.delete(event.oturum_id);
            lineHandlers.current.delete(event.oturum_id);
            if (requestedClose.current.has(event.oturum_id)) {
              dispatch({ type: "statusChanged", id: event.oturum_id, status: "closed" });
            } else {
              dispatch({
                type: "crashed",
                id: event.oturum_id,
                reason: event.neden || CORE_CLOSED,
              });
            }
          }),
        ]);
        if (!active) {
          listeners.forEach((unlisten) => unlisten());
          return;
        }
        [unlistenLine, unlistenClosed] = listeners;
        const previousActive = persistedView.current?.sessions.find(
          (session) => session.id === persistedView.current?.activeId,
        );
        await create({ id: DEFAULT_SESSION_ID, root: previousActive?.root });
      } catch (reason) {
        if (active) dispatch({ type: "connectionFailed", reason: String(reason) });
      }
    };
    void install();

    return () => {
      active = false;
      mounted.current = false;
      unlistenLine?.();
      unlistenClosed?.();
      clients.current.forEach((client) => client.close());
      clients.current.clear();
      lineHandlers.current.clear();
      requestedClose.current.clear();
    };
  }, [create, transport]);

  useEffect(() => {
    if (state.order.length === 0 || typeof window === "undefined") return;
    saveSessionView(window.localStorage, state);
  }, [state]);

  const send = useCallback(
    (id: string, task: string, attachments: SessionAttachment[] = []) => {
      const session = state.sessions[id];
      if (!session || !task.trim() || session.status !== "ready") return;
      dispatch({ type: "runningChanged", id, running: true });
      dispatch({ type: "messageAdded", id, message: { rol: "kullanici", metin: task } });
      if (session.title === "Yeni görev") {
        dispatch({ type: "titleChanged", id, title: task.trim().slice(0, 64) });
      }
      void session.client
        .request("tur.calistir", { gorev: task, ekler: attachments })
        .then((result) => {
          const text = typeof result.metin === "string" ? result.metin : "";
          if (text) {
            dispatch({ type: "messageAdded", id, message: { rol: "asistan", metin: text } });
          }
        })
        .catch((reason) => {
          dispatch({
            type: "messageAdded",
            id,
            message: { rol: "asistan", metin: `Hata: ${String(reason)}` },
          });
        })
        .finally(() => dispatch({ type: "runningChanged", id, running: false }));
    },
    [state.sessions],
  );

  const runCommand = useCallback(
    async (id: string, input: string, recordInput = true) => {
      const session = state.sessions[id];
      const trimmed = input.trim();
      if (!session || !trimmed.startsWith("/") || session.status !== "ready") {
        return { ok: false, metin: "Komut çalıştırılamadı." };
      }
      const [name, ...parts] = trimmed.slice(1).split(/\s+/);
      if (recordInput) {
        dispatch({ type: "messageAdded", id, message: { rol: "kullanici", metin: trimmed } });
      }
      const result = await session.client.request("komut.calistir", {
        ad: name,
        arguman: parts.join(" "),
      });
      const text = typeof result.metin === "string" ? result.metin : "";
      if (text || !result.secici) {
        dispatch({
          type: "messageAdded",
          id,
          message: { rol: "asistan", metin: text || "Komut tamamlandı." },
        });
      }
      return result;
    },
    [state.sessions],
  );

  const stop = useCallback(
    (id: string) => {
      const session = state.sessions[id];
      if (!session) return;
      void session.client.request("tur.kes", {}).catch(() => undefined);
      dispatch({ type: "runningChanged", id, running: false });
    },
    [state.sessions],
  );

  const answer = useCallback(
    (id: string, data: Record<string, unknown>) => {
      const session = state.sessions[id];
      if (!session?.question) return;
      session.client.reply(session.question.id, data);
      dispatch({ type: "questionChanged", id, question: null });
    },
    [state.sessions],
  );

  const close = useCallback(
    async (id: string) => {
      requestedClose.current.add(id);
      try {
        await transport.close(id);
        clients.current.get(id)?.close();
        clients.current.delete(id);
        lineHandlers.current.delete(id);
        dispatch({ type: "statusChanged", id, status: "closed" });
      } catch (reason) {
        requestedClose.current.delete(id);
        dispatch({ type: "crashed", id, reason: String(reason) });
        throw reason;
      }
    },
    [transport],
  );

  /** Sohbeti KALICI olarak sil.
   *
   * Kayıt ÖNCE listeden çıkar, çekirdek kapanışı arkada sürer. Eskiden tersiydi
   * ve kullanıcı sil'e bastığında saniyelerce tüm ekranı kaplayan
   * "Bağlanıyor…" görüyordu — silme anında hissedilmeli.
   */
  const remove = useCallback(
    async (id: string) => {
      dispatch({ type: "removed", id });
      // Süreç zaten çökmüş olabilir; kapatma hatası silmeyi geri almamalı,
      // yoksa kullanıcı bozuk bir kaydı hiç temizleyemez.
      await close(id).catch(() => undefined);
    },
    [close],
  );

  const activeSession = state.activeId ? state.sessions[state.activeId] ?? null : null;
  const sessions = useMemo(
    () => state.order.map((id) => state.sessions[id]).filter(Boolean),
    [state.order, state.sessions],
  );
  const recentProjects = useMemo(() => {
    const roots = new Map<string, { name: string; root: string; updatedAt: number }>();
    for (const session of persistedView.current?.sessions ?? []) {
      const name = projectName(session.root);
      roots.set(session.root, { name, root: session.root, updatedAt: session.updatedAt });
    }
    const now = Date.now();
    sessions.forEach((session) => {
      const name = projectName(session.root);
      roots.set(session.root, { name, root: session.root, updatedAt: now });
    });
    return [...roots.values()]
      .filter((project) => isProjectRoot(project.root))
      .sort((left, right) => right.updatedAt - left.updatedAt);
  }, [sessions]);

  return {
    activeSession,
    answer,
    clear: (id: string) => dispatch({ type: "cleared", id }),
    close,
    create,
    select: (id: string) => dispatch({ type: "selected", id }),
    resume,
    recentProjects,
    remove,
    runCommand,
    send,
    sessions,
    state,
    stop,
  };
}
