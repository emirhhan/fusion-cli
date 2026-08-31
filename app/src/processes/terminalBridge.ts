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
  clearRetention(): void;
  onOutput(handler: (data: Uint8Array) => void): UnlistenFn;
  onClosed(handler: (reason: string) => void): UnlistenFn;
  dispose(): void;
}

interface OutputPayload { terminalId: string; data: number[] }
interface ClosedPayload { terminalId: string; reason: string }
const TRANSCRIPT_LIMIT_BYTES = 256 * 1024;

class SafeReplayRetention {
  private bytes = 0;
  private frozen = false;
  private pending: number[] = [];
  private retained: Uint8Array[] = [];
  private skipNextUnit = false;

  push(data: Uint8Array) {
    for (const byte of data) this.pending.push(byte);
    while (this.pending.length) {
      const length = safeUnitLength(this.pending);
      if (length === null) return;
      if (length === 0) {
        this.pending.shift();
        continue;
      }
      const unit = Uint8Array.from(this.pending.slice(0, length));
      this.pending.splice(0, length);
      if (this.skipNextUnit) {
        this.skipNextUnit = false;
        continue;
      }
      if (this.frozen) continue;
      if (this.bytes + unit.byteLength > TRANSCRIPT_LIMIT_BYTES) {
        this.frozen = true;
        continue;
      }
      this.retained.push(unit);
      this.bytes += unit.byteLength;
    }
  }

  replay(handler: (data: Uint8Array) => void) {
    this.retained.forEach((unit) => handler(unit));
  }

  clear() {
    this.bytes = 0;
    this.frozen = false;
    this.retained = [];
    this.skipNextUnit = this.pending.length > 0;
  }
}

function safeUnitLength(bytes: number[]): number | null {
  const first = bytes[0];
  if (first === 0x1b) return escapeUnitLength(bytes);
  if (first === 0x9b) return csiLength(bytes, 1);
  if (first === 0x9d) return stringControlLength(bytes, 1, true);
  if ([0x90, 0x98, 0x9e, 0x9f].includes(first)) return stringControlLength(bytes, 1, false);
  if (first < 0x80) {
    let length = 1;
    while (length < bytes.length && bytes[length] < 0x80 && bytes[length] !== 0x1b) length += 1;
    return length;
  }
  const width = first >= 0xc2 && first <= 0xdf ? 2
    : first >= 0xe0 && first <= 0xef ? 3
      : first >= 0xf0 && first <= 0xf4 ? 4
        : 0;
  if (width === 0) return 0;
  if (bytes.length < width) return null;
  for (let index = 1; index < width; index += 1) {
    if (bytes[index] < 0x80 || bytes[index] > 0xbf) return 0;
  }
  return width;
}

function escapeUnitLength(bytes: number[]): number | null {
  if (bytes.length < 2) return null;
  const second = bytes[1];
  if (second === 0x5b) return csiLength(bytes, 2);
  if (second === 0x5d) return stringControlLength(bytes, 2, true);
  if ([0x50, 0x58, 0x5e, 0x5f].includes(second)) return stringControlLength(bytes, 2, false);
  if (second >= 0x20 && second <= 0x2f) {
    for (let index = 2; index < bytes.length; index += 1) {
      if (bytes[index] >= 0x30 && bytes[index] <= 0x7e) return index + 1;
    }
    return null;
  }
  return 2;
}

function csiLength(bytes: number[], start: number): number | null {
  for (let index = start; index < bytes.length; index += 1) {
    if (bytes[index] >= 0x40 && bytes[index] <= 0x7e) return index + 1;
  }
  return null;
}

function stringControlLength(bytes: number[], start: number, allowBell: boolean): number | null {
  for (let index = start; index < bytes.length; index += 1) {
    if (allowBell && bytes[index] === 0x07) return index + 1;
    if (bytes[index] === 0x9c) return index + 1;
    if (bytes[index] === 0x1b && bytes[index + 1] === 0x5c) return index + 2;
  }
  return null;
}

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
      let closeFinished = false;
      let closingPromise: Promise<void> | undefined;
      let disposed = false;
      const transcript = new SafeReplayRetention();
      const outputHandlers = new Set<(data: Uint8Array) => void>();
      const closedHandlers = new Set<(reason: string) => void>();
      const pendingOutput: OutputPayload[] = [];
      const pendingClosed: ClosedPayload[] = [];
      const routeOutput = (payload: OutputPayload) => {
        if (!terminalId) { pendingOutput.push(payload); return; }
        if (payload.terminalId !== terminalId) return;
        const data = Uint8Array.from(payload.data);
        transcript.push(data);
        outputHandlers.forEach((handler) => handler(data));
      };
      const routeClosed = (payload: ClosedPayload) => {
        if (!terminalId) { pendingClosed.push(payload); return; }
        if (payload.terminalId !== terminalId) return;
        closedReason = payload.reason;
        closedHandlers.forEach((handler) => handler(payload.reason));
      };
      let stopOutput: UnlistenFn | undefined;
      let stopClosed: UnlistenFn | undefined;
      try {
        stopOutput = await listen<OutputPayload>("terminal://cikti", ({ payload }) => routeOutput(payload));
        stopClosed = await listen<ClosedPayload>("terminal://kapandi", ({ payload }) => routeClosed(payload));
      } catch (error) {
        stopClosed?.();
        stopOutput?.();
        throw error;
      }
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
        close: () => {
          if (closedReason !== undefined || closeFinished) return Promise.resolve();
          if (closingPromise) return closingPromise;
          closingPromise = runtime.close(snapshot.terminalId)
            .then(() => { closeFinished = true; })
            .catch((error) => {
              if (closedReason !== undefined) { closeFinished = true; return; }
              throw error;
            })
            .finally(() => {
              if (!closeFinished) closingPromise = undefined;
            });
          return closingPromise;
        },
        clearRetention: () => transcript.clear(),
        onOutput: (handler) => {
          outputHandlers.add(handler);
          transcript.replay(handler);
          return () => outputHandlers.delete(handler);
        },
        onClosed: (handler) => {
          closedHandlers.add(handler);
          if (closedReason !== undefined) handler(closedReason);
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
