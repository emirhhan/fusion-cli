import { useEffect, useRef } from "react";
import { FitAddon } from "@xterm/addon-fit";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import type { TerminalSession } from "./terminalBridge";

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
  session,
  active,
  closedReason = null,
  adapter: providedAdapter,
  createAdapter,
}: {
  session: TerminalSession;
  active: boolean;
  closedReason?: string | null;
  adapter?: XtermAdapter;
  createAdapter?: () => XtermAdapter;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const adapterRef = useRef<XtermAdapter | null>(null);
  const decoderRef = useRef<TextDecoder | null>(null);

  useEffect(() => {
    const adapter = createAdapter?.() ?? providedAdapter ?? createXtermAdapter();
    adapterRef.current = adapter;
    const host = hostRef.current!;
    const decoder = new TextDecoder();
    decoderRef.current = decoder;
    const encoder = new TextEncoder();
    adapter.open(host);
    const stopData = adapter.onData((data) => { void session.write(encoder.encode(data)); });
    const fit = () => {
      const { cols, rows } = adapter.fit();
      if (cols > 0 && rows > 0) void session.resize(cols, rows);
    };
    fit();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(fit);
    observer?.observe(host);
    const stopOutput = session.onOutput((bytes) => {
      const text = decoder.decode(bytes, { stream: true });
      if (text) adapter.write(text);
    });
    return () => {
      observer?.disconnect();
      stopData();
      stopOutput();
      adapter.dispose();
      if (adapterRef.current === adapter) adapterRef.current = null;
      if (decoderRef.current === decoder) decoderRef.current = null;
    };
  }, [createAdapter, providedAdapter, session]);

  useEffect(() => {
    if (active) adapterRef.current?.focus();
  }, [active]);

  useEffect(() => {
    if (!closedReason) return;
    const tail = decoderRef.current?.decode() ?? "";
    if (tail) adapterRef.current?.write(tail);
  }, [closedReason]);

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
