import { useEffect, useRef, useState } from "react";
import { FitAddon } from "@xterm/addon-fit";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import type { TerminalRuntime } from "./terminalBridge";

export interface XtermAdapter {
  open(element: HTMLElement): void;
  onData(handler: (data: string) => void): () => void;
  write(data: string): void;
  fit(): { cols: number; rows: number };
  focus(): void;
  clear(): void;
  getSelection(): string;
  paste(data: string): void;
  dispose(): void;
}

export function createXtermAdapter(): XtermAdapter {
  const terminal = new Terminal({
    cursorBlink: true,
    convertEol: false,
    fontFamily: "var(--font-mono)",
    fontSize: 12,
    theme: { background: "#0f1115" },
  });
  const fitAddon = new FitAddon();
  terminal.loadAddon(fitAddon);
  return {
    open: (element) => terminal.open(element),
    onData: (handler) => {
      const disposable = terminal.onData(handler);
      return () => disposable.dispose();
    },
    write: (data) => terminal.write(data),
    fit: () => {
      fitAddon.fit();
      return { cols: terminal.cols, rows: terminal.rows };
    },
    focus: () => terminal.focus(),
    clear: () => terminal.clear(),
    getSelection: () => terminal.getSelection(),
    paste: (data) => terminal.paste(data),
    dispose: () => terminal.dispose(),
  };
}

export function XtermSession({
  terminalId,
  runtime,
  active,
  adapter: providedAdapter,
}: {
  terminalId: string;
  runtime: TerminalRuntime;
  active: boolean;
  adapter?: XtermAdapter;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const adapterRef = useRef<XtermAdapter | null>(null);
  const [closedReason, setClosedReason] = useState<string | null>(null);

  if (!adapterRef.current) adapterRef.current = providedAdapter ?? createXtermAdapter();

  useEffect(() => {
    const adapter = adapterRef.current!;
    const host = hostRef.current!;
    const decoder = new TextDecoder();
    const encoder = new TextEncoder();
    let disposed = false;
    let stopOutput: (() => void) | undefined;
    let stopClosed: (() => void) | undefined;
    adapter.open(host);
    const stopData = adapter.onData((data) => { void runtime.write(terminalId, encoder.encode(data)); });
    const fit = () => {
      const { cols, rows } = adapter.fit();
      if (cols > 0 && rows > 0) void runtime.resize(terminalId, cols, rows);
    };
    fit();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(fit);
    observer?.observe(host);
    void runtime.onOutput(terminalId, (bytes) => {
      const text = decoder.decode(bytes, { stream: true });
      if (text) adapter.write(text);
    }).then((unlisten) => disposed ? unlisten() : stopOutput = unlisten);
    void runtime.onClosed(terminalId, (reason) => {
      const tail = decoder.decode();
      if (tail) adapter.write(tail);
      setClosedReason(reason);
    }).then((unlisten) => disposed ? unlisten() : stopClosed = unlisten);
    return () => {
      disposed = true;
      observer?.disconnect();
      stopData();
      stopOutput?.();
      stopClosed?.();
      adapter.dispose();
    };
  }, [runtime, terminalId]);

  useEffect(() => {
    if (active) adapterRef.current?.focus();
  }, [active]);

  const copy = async () => {
    const selection = adapterRef.current?.getSelection() ?? "";
    if (selection) await navigator.clipboard.writeText(selection);
  };
  const paste = async () => adapterRef.current?.paste(await navigator.clipboard.readText());

  return (
    <div className="xterm-session" hidden={!active}>
      <div className="xterm-session__actions">
        <button aria-label="Terminali temizle" onClick={() => adapterRef.current?.clear()} type="button">Temizle</button>
        <button aria-label="Seçimi kopyala" onClick={() => void copy()} type="button">Kopyala</button>
        <button aria-label="Panodan yapıştır" onClick={() => void paste()} type="button">Yapıştır</button>
      </div>
      <div aria-label="Terminal ekranı" className="xterm-session__host" ref={hostRef} />
      <span className="xterm-session__status" role="status">
        {closedReason ? `Terminal kapandı: ${closedReason}` : "Terminal çalışıyor"}
      </span>
    </div>
  );
}
