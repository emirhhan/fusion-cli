import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

export interface TerminalSnapshot {
  terminalId: string;
  cwd: string;
  cols: number;
  rows: number;
  pid: number | null;
}

export interface TerminalRuntime {
  open(cwd: string, cols: number, rows: number): Promise<TerminalSnapshot>;
  write(terminalId: string, data: Uint8Array): Promise<void>;
  resize(terminalId: string, cols: number, rows: number): Promise<void>;
  close(terminalId: string): Promise<void>;
  onOutput(terminalId: string, handler: (data: Uint8Array) => void): Promise<UnlistenFn>;
  onClosed(terminalId: string, handler: (reason: string) => void): Promise<UnlistenFn>;
}

interface OutputPayload { terminalId: string; data: number[] }
interface ClosedPayload { terminalId: string; reason: string }

export function createTerminalRuntime(): TerminalRuntime {
  return {
    open: (cwd, cols, rows) => invoke<TerminalSnapshot>("terminal_ac", { cwd, cols, rows }),
    write: (terminalId, data) => invoke("terminal_yaz", { terminalId, data: Array.from(data) }),
    resize: (terminalId, cols, rows) => invoke("terminal_boyutla", { terminalId, cols, rows }),
    close: (terminalId) => invoke("terminal_kapat", { terminalId }),
    onOutput: (terminalId, handler) => listen<OutputPayload>("terminal://cikti", ({ payload }) => {
      if (payload.terminalId === terminalId) handler(Uint8Array.from(payload.data));
    }),
    onClosed: (terminalId, handler) => listen<ClosedPayload>("terminal://kapandi", ({ payload }) => {
      if (payload.terminalId === terminalId) handler(payload.reason);
    }),
  };
}

export const terminalRuntime = createTerminalRuntime();
