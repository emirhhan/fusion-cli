import type { ProtocolClient } from "../protocol/client";
import type { Soru } from "../protocol/types";
import type { Mesaj } from "../screens/Conversation";
import type { SessionModel, SessionSource, SessionState, SessionStatus } from "./types";

export const initialSessionState: SessionState = {
  activeId: null,
  order: [],
  sessions: {},
  connectionError: null,
};

interface SessionSeed {
  id: string;
  title: string;
  source: SessionSource;
  root: string;
  client: ProtocolClient;
  pid?: number;
}

export type SessionAction =
  | { type: "created"; session: SessionSeed }
  | { type: "selected"; id: string }
  | { type: "titleChanged"; id: string; title: string }
  | { type: "messageAdded"; id: string; message: Mesaj }
  | { type: "runningChanged"; id: string; running: boolean }
  | { type: "questionChanged"; id: string; question: { id: string; data: Soru } | null }
  | { type: "statusChanged"; id: string; status: SessionStatus; error?: string | null }
  | { type: "crashed"; id: string; reason: string }
  | { type: "cleared"; id: string }
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
        pid: action.session.pid ?? null,
        status: "ready",
        error: null,
        running: false,
        messages: [],
        question: null,
      };
      return {
        ...state,
        activeId: action.session.id,
        order: exists ? state.order : [...state.order, action.session.id],
        sessions: { ...state.sessions, [action.session.id]: model },
        connectionError: null,
      };
    }
    case "selected":
      return state.sessions[action.id] ? { ...state, activeId: action.id } : state;
    case "titleChanged":
      return updateSession(state, action.id, (session) => ({ ...session, title: action.title }));
    case "messageAdded":
      return updateSession(state, action.id, (session) => ({
        ...session,
        messages: [...session.messages, action.message],
      }));
    case "runningChanged":
      return updateSession(state, action.id, (session) => ({
        ...session,
        running: action.running,
      }));
    case "questionChanged":
      return updateSession(state, action.id, (session) => ({
        ...session,
        question: action.question,
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
        question: null,
      }));
    case "cleared":
      return updateSession(state, action.id, (session) => ({
        ...session,
        messages: [],
        question: null,
        running: false,
      }));
    case "connectionFailed":
      return { ...state, connectionError: action.reason };
  }
}
