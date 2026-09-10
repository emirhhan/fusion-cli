import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { ProtocolClient } from "../protocol/client";
import type { Soru } from "../protocol/types";
import type { Mesaj } from "../screens/Conversation";
import { initialSessionState, sessionReducer } from "./store";
import { loadSessionView, saveSessionView } from "./persistence";
import { isProjectRoot, projectName } from "./projectRoots";
import { DEFAULT_TITLE, titleFromTask } from "./title";
import type {
  BackendSessionSnapshot,
  NewSession,
  ResumeSession,
  SessionClosedEvent,
  SessionLineEvent,
  SessionAttachment,
  SessionTransport,
  StoredConversation,
} from "./types";

const DEFAULT_SESSION_ID = "varsayilan";
//: Açılışta geri açılacak en fazla sekme.
//
// Sınır bir tercih değil, koruma: 110 sohbeti olan bir kullanıcıda hepsini
// açmak her biri için ayrı bir çekirdek süreci başlatırdı. Gerisi saklı
// sohbet listesinden tek tıkla açılır.
const MAX_RESTORED_SESSIONS = 8;
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
  const clientRoots = useRef(new Map<string, string>());
  const deletedIds = useRef(new Set<string>());
  const lineHandlers = useRef(new Map<string, (line: string) => void>());
  const requestedClose = useRef(new Set<string>());
  const runningRequests = useRef(new Set<string>());
  const mounted = useRef(false);
  const [stored, setStored] = useState<StoredConversation[]>([]);
  const storedRef = useRef<StoredConversation[]>([]);
  storedRef.current = stored;

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
      client.onEvent((event) => dispatch({ type: "eventReceived", id, event }));
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
      clientRoots.current.set(id, snapshot.kok);
      // Sekme kimliği HER bağlanmada bildirilir. Ölçüldü (kullanıcının diski):
      // `resume` yolu kimliği hiç göndermiyordu, çekirdek de rastgele bir kimlik
      // üretiyordu; o konuşmalara bir daha ulaşılamıyordu.
      const baslatildi = client.request("oturum.baslat", { sohbet_id: id }).catch(() => undefined);
      if (publish) {
        dispatch({
          type: "created",
          session: {
            id,
            title: input.title ?? DEFAULT_TITLE,
            updatedAt: input.updatedAt,
            source: input.source ?? "fusion",
            root: snapshot.kok,
            pid: snapshot.pid,
            client,
          },
        });
        // Geçmiş, sekme kimliği arka uca bildirildikten SONRA istenir: kimliksiz
        // sorulursa proje genelindeki başka bir konuşma yüklenir.
        void baslatildi
          .then(() => client.request("oturum.gecmis", {}))
          .then((result) => {
            if (!Array.isArray(result.mesajlar)) return;
            const messages: Mesaj[] = result.mesajlar.flatMap((item) => {
              if (!item || typeof item !== "object") return [];
              const row = item as Record<string, unknown>;
              if (
                (row.rol !== "kullanici" && row.rol !== "asistan") ||
                typeof row.metin !== "string"
              ) return [];
              return [{ rol: row.rol, metin: row.metin }];
            });
            dispatch({ type: "historyLoaded", id, messages });
          })
          .catch(() => undefined);
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
        void connection.client.request("oturum.gecmis", {}).then((history) => {
          if (!Array.isArray(history.mesajlar)) return;
          const messages: Mesaj[] = history.mesajlar.flatMap((item) => {
            if (!item || typeof item !== "object") return [];
            const row = item as Record<string, unknown>;
            if (
              (row.rol !== "kullanici" && row.rol !== "asistan") ||
              typeof row.metin !== "string"
            ) return [];
            return [{ rol: row.rol, metin: row.metin }];
          });
          dispatch({ type: "historyLoaded", id: connection.id, messages });
        }).catch(() => undefined);
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

  const restoreSessions = useCallback(async () => {
    // Kaydedilmiş sekmeler zaten yazılıyordu; yalnız okunmuyordu. Ölçüldü
    // (kullanıcının makinesi, 7-8 Eylül): her açılışta tek ve sabit kimlikli bir
    // sekme açılıyor, dünkü konuşmalara giden yol tamamen kapanıyordu.
    const saved = persistedView.current?.sessions ?? [];
    const restorable = [...saved]
      .sort((left, right) => left.updatedAt - right.updatedAt)
      .slice(-MAX_RESTORED_SESSIONS);
    if (restorable.length === 0) {
      // Boş kayıt, son sohbetin silindiğini gösterir; eski sabit kimliği diriltme.
      await create(persistedView.current ? {} : { id: DEFAULT_SESSION_ID });
      return;
    }
    for (const session of restorable) {
      await connect({
        id: session.id,
        title: session.title,
        source: session.source,
        root: session.root,
        updatedAt: session.updatedAt,
      }).catch(() => undefined);
    }
    const activeId = persistedView.current?.activeId;
    if (activeId && restorable.some((session) => session.id === activeId)) {
      dispatch({ type: "selected", id: activeId });
    }
  }, [connect, create]);

  const refreshStored = useCallback(async () => {
    // Liste AÇIK sekmeden istenir: çekirdek kendi kökündeki sohbetleri bilir.
    const entry = clients.current.entries().next().value;
    if (!entry) return;
    const [clientId, client] = entry;
    const result = await client.request("sohbet.listele", {}).catch(() => null);
    if (!result || !Array.isArray(result.sohbetler)) return;
    const rows: StoredConversation[] = result.sohbetler.flatMap((item) => {
      if (!item || typeof item !== "object") return [];
      const row = item as Record<string, unknown>;
      if (typeof row.sohbet_id !== "string" || typeof row.baslik !== "string") return [];
      if (deletedIds.current.has(row.sohbet_id)) return [];
      return [{
        id: row.sohbet_id,
        root: typeof row.kok === "string" ? row.kok : clientRoots.current.get(clientId) ?? "",
        title: row.baslik,
        updatedAt: typeof row.guncelleme === "number" ? row.guncelleme : 0,
        messageCount: typeof row.mesaj_sayisi === "number" ? row.mesaj_sayisi : 0,
      }];
    });
    setStored(rows);
  }, []);

  const openStored = useCallback(
    async (id: string, root?: string) => {
      const known = storedRef.current.find((item) => item.id === id);
      await connect({ id, title: known?.title ?? DEFAULT_TITLE, root: root ?? known?.root, updatedAt: known ? known.updatedAt * 1000 : undefined });
      dispatch({ type: "selected", id });
    },
    [connect],
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
        await restoreSessions();
        // Saklı sohbetler açılışta bir kez okunur: liste kullanıcıya
        // "nereye dönebilirim" sorusunun cevabıdır, sekmelerden bağımsızdır.
        await refreshStored();
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
      runningRequests.current.clear();
    };
  }, [refreshStored, restoreSessions, transport]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    // İlk yüklemede kayıtları koru; başarılı silme sonrası boş görünümü de sakla.
    if (state.order.length === 0 && deletedIds.current.size === 0) return;
    saveSessionView(window.localStorage, state);
  }, [state]);

  const send = useCallback(
    (id: string, task: string, attachments: SessionAttachment[] = [], recordMessage = true) => {
      const session = state.sessions[id];
      if (
        !session || !task.trim() || session.status !== "ready" ||
        session.running || runningRequests.current.has(id)
      ) return false;
      runningRequests.current.add(id);
      dispatch({ type: "runningChanged", id, running: true });
      // Ekler mesajla birlikte KAYDEDİLİR: gönderdikten sonra composer temizlenir
      // ve aksi hâlde kullanıcının ne gönderdiğinin geçmişte hiçbir izi kalmaz.
      // Makro turunda kullanıcının yazdığı `/goal …` satırı zaten kayıtlıdır.
      if (recordMessage) {
        dispatch({
          type: "messageAdded",
          id,
          message: {
            rol: "kullanici",
            metin: task,
            ...(attachments.length > 0 ? { ekler: attachments } : {}),
          },
        });
      }
      if (session.title === DEFAULT_TITLE) {
        dispatch({ type: "titleChanged", id, title: titleFromTask(task) });
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
        .finally(() => {
          runningRequests.current.delete(id);
          dispatch({ type: "runningChanged", id, running: false });
        });
      return true;
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
          message: {
            rol: "asistan",
            metin: text || (result.ok === false ? "Komut başarısız." : "Komut tamamlandı."),
          },
        });
      }
      // Makro (`/goal` …) görevi yalnız hazırlar; çekirdek görevi geri verir ve
      // tur burada normal gönderim yolundan başlar. Aksi hâlde komut
      // "çalıştırılıyor…" deyip hiçbir iş yapmıyordu.
      if (typeof result.gorev === "string" && result.gorev.trim()) {
        send(id, result.gorev, [], false);
      }
      return result;
    },
    [state.sessions, send],
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

  /** Disk kaydı silinmeden görünümden çıkarma; başarısızlık tekrar denenebilsin. */
  const remove = useCallback(
    async (id: string) => {
      const session = state.sessions[id];
      const known = storedRef.current.find((item) => item.id === id);
      const root = session?.root ?? known?.root;
      if (!root) throw new Error("Sohbetin proje kökü bulunamadı. Geçmişi yenileyin.");
      const live = session?.status === "ready" ? session : Object.values(state.sessions)
        .find((item) => item.status === "ready" && clients.current.has(item.id));
      const temporary = live ? null : await connect({ root }, false);
      const client = live?.client ?? temporary!.client;
      try {
        const result = await client.request("sohbet.sil", { sohbet_id: id, kok: root });
        if (result.ok !== true) throw new Error(String(result.metin ?? "Sohbet silinemedi."));
        deletedIds.current.add(id);
        setStored((rows) => rows.filter((item) => item.id !== id));
        dispatch({ type: "removed", id });
        // Diskte silme tamamlandı; çökmüş sürecin kapanma hatası bunu geri alamaz.
        if (session) await close(id).catch(() => undefined);
      } finally {
        if (temporary) await close(temporary.id).catch(() => undefined);
      }
    },
    [close, connect, state.sessions],
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
    openStored,
    refreshStored,
    storedConversations: stored,
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
