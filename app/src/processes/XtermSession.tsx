import { useEffect, useRef } from "react";
import { FitAddon } from "@xterm/addon-fit";
import { WebglAddon } from "@xterm/addon-webgl";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { SCROLLBACK_LINES, resolveMonoFont } from "./terminalTheme";
import type { TerminalClosedEvent, TerminalSession } from "./terminalBridge";

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
    // GERÇEK yazı tipi yığını verilir. xterm karakter genişliğini canvas'a
    // yazarak ölçer ve `var(--font-mono)` orada çözülmez; yanlış ölçüm yanlış
    // sütun/satır sayısına, o da yazdıkça kayan bir ekrana yol açıyordu.
    fontFamily: resolveMonoFont(),
    fontSize: 12,
    scrollback: SCROLLBACK_LINES,
    theme: { background: "#0f1115" },
  });
  const fitAddon = new FitAddon();
  terminal.loadAddon(fitAddon);
  return {
    open: (element) => {
      terminal.open(element);
      // WebGL çizimi DOM renderer'ından belirgin biçimde hızlıdır ama her
      // ortamda yoktur (yazılım render, bağlam kaybı). Yüklenemezse xterm
      // kendi varsayılanıyla çalışmaya devam eder — terminal açılmamazlık
      // etmez.
      try {
        terminal.loadAddon(new WebglAddon());
      } catch {
        // WebGL yok; varsayılan renderer yeterlidir.
      }
    },
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
  closed = null,
  adapter: providedAdapter,
  createAdapter,
}: {
  session: TerminalSession;
  active: boolean;
  closed?: TerminalClosedEvent | null;
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
    // Yeniden boyutlandırma, çerçeve başına EN FAZLA bir kez ölçülür ve boyut
    // gerçekten değiştiyse çekirdeğe bildirilir. Eskiden her ResizeObserver
    // tetiklemesi senkron ölçüm + IPC yapıyordu; pencere sürüklenirken bu
    // saniyede onlarca kez olup terminali takıyordu.
    let son = { cols: 0, rows: 0 };
    let bekleyen = 0;
    const olc = () => {
      bekleyen = 0;
      const { cols, rows } = adapter.fit();
      if (cols <= 0 || rows <= 0) return;
      if (cols === son.cols && rows === son.rows) return;
      son = { cols, rows };
      void session.resize(cols, rows);
    };
    const planla = () => {
      if (bekleyen) return;
      bekleyen =
        typeof requestAnimationFrame === "function"
          ? requestAnimationFrame(olc)
          : (setTimeout(olc, 0) as unknown as number);
    };
    // İlk ölçüm de ertelenir: `open` hemen ardından ölçmek, yerleşim ve yazı
    // tipi oturmadan yanlış sütun sayısı üretebiliyordu.
    planla();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(planla);
    observer?.observe(host);
    const stopOutput = session.onOutput((bytes) => {
      const text = decoder.decode(bytes, { stream: true });
      if (text) adapter.write(text);
    });
    return () => {
      observer?.disconnect();
      if (bekleyen && typeof cancelAnimationFrame === "function") cancelAnimationFrame(bekleyen);
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
    if (!closed) return;
    const tail = decoderRef.current?.decode() ?? "";
    if (tail) adapterRef.current?.write(tail);
  }, [closed]);

  const copy = async () => {
    const selection = adapterRef.current?.getSelection() ?? "";
    if (selection) await navigator.clipboard.writeText(selection);
  };
  const paste = async () => adapterRef.current?.paste(await navigator.clipboard.readText());

  return (
    <div className="xterm-session" hidden={!active}>
      <div className="xterm-session__actions">
        <button
          aria-label="Terminali temizle"
          onClick={() => {
            adapterRef.current?.clear();
            session.clearRetention();
          }}
          type="button"
        >Temizle</button>
        <button aria-label="Seçimi kopyala" onClick={() => void copy()} type="button">Kopyala</button>
        <button aria-label="Panodan yapıştır" onClick={() => void paste()} type="button">Yapıştır</button>
      </div>
      <div aria-label="Terminal ekranı" className="xterm-session__host" ref={hostRef} />
      <span className="xterm-session__status" role="status">
        {closed === null ? "Terminal çalışıyor"
          : closed.exitCode === null ? "Terminal durduruldu"
            : closed.exitCode === 0 ? "Terminal bitti"
              : `Terminal hata ile kapandı (çıkış kodu: ${closed.exitCode})`}
      </span>
    </div>
  );
}
