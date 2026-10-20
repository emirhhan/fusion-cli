import { closeUnfinishedAgents } from "../team/ekipOlaylari";
import { migrateMessageIds } from "./messageIdentity";
import type { ProtocolClient } from "../protocol/client";
import type { BaglamOlcusu, Soru } from "../protocol/types";
import type { Mesaj } from "../screens/Conversation";
import type { SessionModel, SessionSource, SessionState, SessionStatus } from "./types";
import { olayEkle } from "../protocol/olayAkisi";
import { canApplySuggestedTitle } from "./title";

// Opak eski olaylarda pencere belleği sınırlıdır; wire v1 sequence kalıcı high-water kullanır.
export const EVENT_REPLAY_WINDOW = 256;

export const initialSessionState: SessionState = {
  activeId: null,
  order: [],
  sessions: {},
  connectionError: null,
};

interface SessionSeed {
  updatedAt?: number;
  id: string;
  title: string;
  source: SessionSource;
  root: string;
  client: ProtocolClient;
  pid?: number;
}

export type SessionAction =
  | { type: "submissionCompleted"; id: string; requestId: string }
  | { type: "submissionStarted"; id: string; requestId: string; expectedTurnId?: string }
  | { type: "created"; session: SessionSeed }
  | { type: "historyLoaded"; id: string; messages: Mesaj[] }
  | { type: "selected"; id: string }
  | { type: "titleChanged"; id: string; title: string }
  | { type: "titleSuggested"; id: string; title: string }
  | { type: "messageAdded"; id: string; message: Mesaj }
  | { type: "eventReceived"; id: string; event: Record<string, unknown> }
  | { type: "runningChanged"; id: string; running: boolean }
  | { type: "stopRequested"; id: string }
  | { type: "stopFailed"; id: string; error: string }
  | { type: "questionChanged"; id: string; question: { id: string; data: Soru } | null }
  /** Soru başka yerden (Chrome yan paneli) cevaplandı; yalnız aynı kartsa kapanır. */
  | { type: "questionClosed"; id: string; questionId: string }
  | {
      type: "contextMeasured";
      id: string;
      baglam: BaglamOlcusu | null;
      maliyetUsd: number | null;
      depoProjeleri: string[];
    }
  | { type: "statusChanged"; id: string; status: SessionStatus; error?: string | null }
  | { type: "crashed"; id: string; reason: string }
  | { type: "cleared"; id: string }
  | { type: "removed"; id: string }
  | { type: "connectionFailed"; reason: string };

function updateSession(
  state: SessionState,
  id: string,
  update: (session: SessionModel) => SessionModel,
): SessionState {
  const current = state.sessions[id];
  if (!current) return state;
  return {
    ...state,
    sessions: { ...state.sessions, [id]: update(current) },
  };
}

export function sessionReducer(state: SessionState, action: SessionAction): SessionState {
  switch (action.type) {
    case "created": {
      const exists = Boolean(state.sessions[action.session.id]);
      const model: SessionModel = {
        ...action.session,
        updatedAt: action.session.updatedAt ?? Date.now(),
        pid: action.session.pid ?? null,
        status: "ready",
        error: null,
        running: false,
        stopping: false,
        stopError: null,
        messages: [],
        question: null,
        questionQueue: [],
        baglam: null,
        maliyetUsd: null,
        depoProjeleri: [],
      };
      return {
        ...state,
        activeId: action.session.id,
        order: exists ? state.order : [...state.order, action.session.id],
        sessions: { ...state.sessions, [action.session.id]: model },
        connectionError: null,
      };
    }
    case "historyLoaded":
      return updateSession(state, action.id, (session) => ({
        ...session,
        messages: session.messages.length === 0 ? migrateMessageIds(action.messages, action.id) : session.messages,
      }));
    case "selected":
      return state.sessions[action.id] ? { ...state, activeId: action.id } : state;
    case "titleChanged":
      return updateSession(state, action.id, (session) => ({ ...session, title: action.title, updatedAt: Date.now() }));
    case "titleSuggested":
      // Öneri eşzamansız gelir; o arada sekme adlandırıldıysa dokunulmaz.
      return updateSession(state, action.id, (session) =>
        canApplySuggestedTitle(session.title, action.title)
          ? { ...session, title: action.title.trim() }
          : session,
      );
    case "messageAdded":
      return updateSession(state, action.id, (session) => ({
        ...session,
        messages: action.message.id && session.messages.some((message) => message.id === action.message.id)
          ? session.messages.map((message) => message.id === action.message.id ? action.message : message)
          : migrateMessageIds([...session.messages, action.message], action.id),
        updatedAt: Date.now(),
      }));
    case "submissionCompleted":
      return updateSession(state, action.id, session => ({ ...session, completedRequestIds: [...(session.completedRequestIds ?? []).filter(id => id !== action.requestId), action.requestId].slice(-100) }));
    case "submissionStarted":
      return updateSession(state, action.id, (session) => ({ ...session, messages: closeUnfinishedAgents(session.messages), requestId: action.requestId,
        turnId: undefined, expectedTurnId: action.expectedTurnId, eventSequence: undefined, eventIds: [] }));
    case "eventReceived": {
      const current = state.sessions[action.id];
      if (!current) return state;
      const eventId = typeof action.event.event_id === "string" ? action.event.event_id : null;
      const sessionId = action.event.session_id;
      const turnId = typeof action.event.turn_id === "string" ? action.event.turn_id : undefined;
      if (typeof sessionId === "string" && sessionId !== action.id) return state;
      const receipt = action.event.olay === "GonderimMakbuzu";
      if (receipt && (action.event.gonderim_id !== current.requestId || (current.expectedTurnId && turnId !== current.expectedTurnId))) return state;
      if (turnId && !receipt && current.requestId && (!current.turnId || turnId !== current.turnId)) return state;
      if (turnId && current.turnId && turnId !== current.turnId) return state;
      const suffix = eventId?.split(":").slice(-1)[0];
      const sequence = action.event.schema_version === 1 && turnId && suffix && /^\d+$/.test(suffix) ? Number(suffix) : undefined;
      if (eventId && (current.eventIds?.includes(eventId) || current.messages.some((message) => message.id?.startsWith(`${eventId}:`)))) return state;
      if (sequence !== undefined && current.eventSequence !== undefined && sequence <= current.eventSequence) return state;
      // Olaylar akışa BİRLEŞTİRİLEREK girer; birleştirme kuralı `olayEkle`de.
      return updateSession(state, action.id, (session) => ({
        ...session,
        messages: olayEkle(session.messages, action.event).map((message, index) =>
          message.id ? message : { ...message, id: eventId ? `${eventId}:${message.rol}:${index}` : migrateMessageIds([message], `${action.id}:${index}`)[0].id }),
        eventSequence: sequence ?? session.eventSequence,
        eventIds: eventId ? [...(session.eventIds ?? []), eventId].slice(-EVENT_REPLAY_WINDOW) : session.eventIds,
        turnId: turnId ?? session.turnId,
        updatedAt: Date.now(),
      }));
    }
    case "runningChanged":
      return updateSession(state, action.id, (session) => ({
        ...session,
        running: action.running,
        stopping: action.running ? session.stopping : false,
        stopError: action.running ? session.stopError : null,
      }));
    case "stopRequested":
      return updateSession(state, action.id, (session) => ({ ...session, stopping: true, stopError: null }));
    case "stopFailed":
      return updateSession(state, action.id, (session) => ({ ...session, stopping: false, stopError: action.error }));
    case "questionChanged":
      return updateSession(state, action.id, (session) => {
        if (!action.question) return { ...session, question: null, questionQueue: [] };
        if (!session.question || session.question.id === action.question.id) return { ...session, question: action.question };
        const queue = session.questionQueue ?? [];
        return { ...session, questionQueue: [...queue.filter((question) => question.id !== action.question?.id), action.question] };
      });
    case "questionClosed":
      return updateSession(state, action.id, (session) => {
        const queue = session.questionQueue ?? [];
        return session.question?.id === action.questionId
          ? { ...session, question: queue[0] ?? null, questionQueue: queue.slice(1) }
          : { ...session, questionQueue: queue.filter((question) => question.id !== action.questionId) };
      });
    case "contextMeasured":
      return updateSession(state, action.id, (session) => ({
        ...session,
        baglam: action.baglam,
        maliyetUsd: action.maliyetUsd,
        depoProjeleri: action.depoProjeleri,
      }));
    case "statusChanged":
      return updateSession(state, action.id, (session) => ({
        ...session,
        status: action.status,
        error: action.error ?? null,
      }));
    case "crashed":
      return updateSession(state, action.id, (session) => ({
        ...session,
        status: "crashed",
        error: action.reason,
        running: false,
        stopping: false,
        stopError: null,
        question: null,
        questionQueue: [],
      }));
    case "cleared":
      return updateSession(state, action.id, (session) => ({
        ...session,
        messages: [],
        question: null,
        questionQueue: [],
        running: false,
        stopping: false,
        stopError: null,
      }));
    case "removed": {
      // Silme geri alınamaz: oturum listeden çıkar. Son oturum silinirse
      // etkin seçim boşa düşer ve arayüz yeni görev ekranına döner.
      const kalan = { ...state.sessions };
      delete kalan[action.id];
      const sira = state.order.filter((item) => item !== action.id);
      const etkin =
        state.activeId === action.id ? (sira[sira.length - 1] ?? null) : state.activeId;
      return { ...state, sessions: kalan, order: sira, activeId: etkin };
    }
    case "connectionFailed":
      return { ...state, connectionError: action.reason };
  }
}
