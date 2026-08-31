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
  openSession(cwd: string, cols: number, rows: number): Promise<TerminalSession>;
}

export interface TerminalSession {
  snapshot: TerminalSnapshot;
  write(data: Uint8Array): Promise<void>;
  resize(cols: number, rows: number): Promise<void>;
  close(): Promise<void>;
  onOutput(handler: (data: Uint8Array) => void): UnlistenFn;
  onClosed(handler: (reason: string) => void): UnlistenFn;
  dispose(): void;
}

interface OutputPayload { terminalId: string; data: number[] }
interface ClosedPayload { terminalId: string; reason: string }

export function createTerminalRuntime(): TerminalRuntime {
  const runtime: TerminalRuntime = {
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
    openSession: async (cwd, cols, rows) => {
      let terminalId: string | undefined;
      let closedReason: string | undefined;
      let disposed = false;
      const outputBuffer: Uint8Array[] = [];
      const closedBuffer: string[] = [];
      const outputHandlers = new Set<(data: Uint8Array) => void>();
      const closedHandlers = new Set<(reason: string) => void>();
      const pendingOutput: OutputPayload[] = [];
      const pendingClosed: ClosedPayload[] = [];
      const routeOutput = (payload: OutputPayload) => {
        if (!terminalId) { pendingOutput.push(payload); return; }
        if (payload.terminalId !== terminalId) return;
        const data = Uint8Array.from(payload.data);
        if (outputHandlers.size) outputHandlers.forEach((handler) => handler(data));
        else outputBuffer.push(data);
      };
      const routeClosed = (payload: ClosedPayload) => {
        if (!terminalId) { pendingClosed.push(payload); return; }
        if (payload.terminalId !== terminalId) return;
        closedReason = payload.reason;
        if (closedHandlers.size) closedHandlers.forEach((handler) => handler(payload.reason));
        else closedBuffer.push(payload.reason);
      };
      const [stopOutput, stopClosed] = await Promise.all([
        listen<OutputPayload>("terminal://cikti", ({ payload }) => routeOutput(payload)),
        listen<ClosedPayload>("terminal://kapandi", ({ payload }) => routeClosed(payload)),
      ]);
      let snapshot: TerminalSnapshot;
      try {
        snapshot = await runtime.open(cwd, cols, rows);
      } catch (error) {
        stopOutput();
        stopClosed();
        throw error;
      }
      terminalId = snapshot.terminalId;
      pendingOutput.splice(0).forEach(routeOutput);
      pendingClosed.splice(0).forEach(routeClosed);
      return {
        snapshot,
        write: (data) => runtime.write(snapshot.terminalId, data),
        resize: (nextCols, nextRows) => runtime.resize(snapshot.terminalId, nextCols, nextRows),
        close: async () => {
          if (closedReason !== undefined) return;
          try {
            await runtime.close(snapshot.terminalId);
          } catch (error) {
            if (closedReason !== undefined) return;
            throw error;
          }
        },
        onOutput: (handler) => {
          outputHandlers.add(handler);
          outputBuffer.splice(0).forEach((data) => handler(data));
          return () => outputHandlers.delete(handler);
        },
        onClosed: (handler) => {
          closedHandlers.add(handler);
          closedBuffer.splice(0).forEach((reason) => handler(reason));
          return () => closedHandlers.delete(handler);
        },
        dispose: () => {
          if (disposed) return;
          disposed = true;
          stopOutput();
          stopClosed();
          outputHandlers.clear();
          closedHandlers.clear();
        },
      };
    },
  };
  return runtime;
}

export const terminalRuntime = createTerminalRuntime();
