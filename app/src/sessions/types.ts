import type { ProtocolClient } from "../protocol/client";
import type { Soru } from "../protocol/types";
import type { Mesaj } from "../screens/Conversation";

export type SessionSource = "fusion" | "claude" | "codex" | "hermes";
export type SessionStatus = "ready" | "crashed" | "closed";

export interface BackendSessionSnapshot {
  oturum_id: string;
  kok: string;
  pid: number;
  durum: "calisiyor" | "kapandi";
  kapanis_nedeni: string | null;
}

export interface SessionLineEvent {
  oturum_id: string;
  satir: string;
}

export interface SessionClosedEvent {
  oturum_id: string;
  neden: string;
}

export type Unlisten = () => void;

export interface SessionTransport {
  create(id: string, root?: string): Promise<BackendSessionSnapshot>;
  send(id: string, line: string): Promise<void>;
  close(id: string): Promise<void>;
  list(): Promise<BackendSessionSnapshot[]>;
  onLine(handler: (event: SessionLineEvent) => void): Promise<Unlisten>;
  onClosed(handler: (event: SessionClosedEvent) => void): Promise<Unlisten>;
}

export interface SessionQuestion {
  id: string;
  data: Soru;
}

export interface SessionModel {
  id: string;
  title: string;
  source: SessionSource;
  root: string;
  pid: number | null;
  status: SessionStatus;
  error: string | null;
  running: boolean;
  messages: Mesaj[];
  question: SessionQuestion | null;
  client: ProtocolClient;
}

export interface NewSession {
  id?: string;
  title?: string;
  source?: SessionSource;
  root?: string;
}

export interface ResumeSession {
  source: Exclude<SessionSource, "fusion">;
  sessionId: string;
  title: string;
  root?: string;
}

export interface SessionAttachment {
  kind: "file" | "image";
  name: string;
  path: string;
}

export interface SessionState {
  activeId: string | null;
  order: string[];
  sessions: Record<string, SessionModel>;
  connectionError: string | null;
}

export interface RecentProject {
  name: string;
  root: string;
  updatedAt: number;
}
