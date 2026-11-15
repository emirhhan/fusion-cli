import { useEffect, useRef, useState } from "react";
import { FitAddon } from "@xterm/addon-fit";
import { WebglAddon } from "@xterm/addon-webgl";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { macTerminalShortcut } from "./macShortcuts";
import { SCROLLBACK_LINES, resolveMonoFont, resolveTerminalTheme, type TerminalTheme } from "./terminalTheme";
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
  /** Uygulama teması/kontrastı değişince terminal renklerini güncelle (P-065). */
  setTheme?(theme: TerminalTheme): void;
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
    // Tema token'lardan gelir: açık temada açık zemin, koyu temada koyu (P-065).
    theme: resolveTerminalTheme(),
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
        const webgl = new WebglAddon();
        // Bağlam kaybı (GPU sıfırlanması, tarayıcının bağlam sınırı) olursa eklenti atılır ve xterm
        // varsayılan renderer'a döner; aksi halde terminal boş/donuk kalıyordu (U4-23).
        webgl.onContextLoss(() => webgl.dispose());
        terminal.loadAddon(webgl);
      } catch {
        // WebGL yok; varsayılan renderer yeterlidir.
      }
    },
    onData: (handler) => {
      const disposable = terminal.onData(handler);
      // macOS satır/kelime kısayolları (bkz. `macShortcuts`). Eşleşen tuş
      // kabuğa dizisiyle gider ve xterm'in kendi işlemesi durdurulur.
      terminal.attachCustomKeyEventHandler((event) => {
        if (event.type !== "keydown") return true;
        const kisayol = macTerminalShortcut(event);
        if (kisayol === null) return true;
        event.preventDefault();
        if (kisayol === "temizle") terminal.clear();
        else handler(kisayol);
        return false;
      });
      return () => {
        terminal.attachCustomKeyEventHandler(() => true);
        disposable.dispose();
      };
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
    setTheme: (theme) => {
      terminal.options.theme = theme;
    },
  };
}

/**
 * Kabuğu doğuracak GERÇEK sütun/satır sayısını ölç.
 *
 * Ölçüm xterm'in KENDİ hesabıyla yapılır: geçici bir terminal açılır, `fit`
 * çağrılır, sayılar okunur ve terminal atılır.
 *
 * Ölçülen hata (kullanıcı makinesi): kabuk 8.4×18 piksellik TAHMİNİ hücre
 * boyutuyla doğuruluyor, hemen ardından xterm gerçek boyutu ölçüp yeniden
 * boyutlandırıyordu. Kabuk ilk istemini ilk boyutta çizmiş oluyor, yeniden
 * boyutlandırmada bir daha çiziyor ve ekranda İKİ İSTEM satırı kalıyordu —
 * "birden fazla terminal path'i görünüyor" şikayeti buydu. Tahmin yerine
 * ölçüm, sorunu kaynağında bitirir.
 */
export function measureTerminalSize(host: HTMLElement): { cols: number; rows: number } {
  const probe = new Terminal({ fontFamily: resolveMonoFont(), fontSize: 12 });
  const fit = new FitAddon();
  probe.loadAddon(fit);
  try {
    probe.open(host);
    fit.fit();
    return { cols: probe.cols, rows: probe.rows };
  } finally {
    probe.dispose();
  }
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
  const closedRef = useRef(closed);
  closedRef.current = closed;
  const [ioError, setIoError] = useState<string | null>(null);

  useEffect(() => {
    const adapter = createAdapter?.() ?? providedAdapter ?? createXtermAdapter();
    adapterRef.current = adapter;
    const host = hostRef.current!;
    const decoder = new TextDecoder();
    decoderRef.current = decoder;
    const encoder = new TextEncoder();
    adapter.open(host);
    // Kapanmış terminale yazılan tuş IPC'ye gitmez; başarısız yazma/boyutlandırma kullanıcıya
    // durum çubuğunda görünür, işlenmemiş promise reddi olmaz (U4-24).
    const bildir = (reason: unknown) => setIoError(reason instanceof Error ? reason.message : String(reason));
    const stopData = adapter.onData((data) => {
      if (closedRef.current !== null) return;
      session.write(encoder.encode(data)).catch(bildir);
    });
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
      session.resize(cols, rows).catch(bildir);
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

  // Tema (data-theme), kontrast ve vurgu belge kökünde değişince terminal renkleri de değişir;
  // eskiden terminal açık temada da koyu kalıyordu (P-065).
  useEffect(() => {
    if (typeof MutationObserver === "undefined") return;
    const root = document.documentElement;
    const observer = new MutationObserver(() => adapterRef.current?.setTheme?.(resolveTerminalTheme()));
    observer.observe(root, { attributeFilter: ["data-theme", "data-contrast", "data-accent"], attributes: true });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!closed) return;
    const tail = decoderRef.current?.decode() ?? "";
    if (tail) adapterRef.current?.write(tail);
  }, [closed]);

  const copy = async () => {
    try {
      const selection = adapterRef.current?.getSelection() ?? "";
      if (selection) await navigator.clipboard.writeText(selection);
    } catch {
      setIoError("Panoya kopyalanamadı (izin verilmedi).");
    }
  };
  const paste = async () => {
    try {
      adapterRef.current?.paste(await navigator.clipboard.readText());
    } catch {
      setIoError("Panodan yapıştırılamadı (izin verilmedi).");
    }
  };

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
        {ioError ? ioError
          : closed === null ? "Terminal çalışıyor"
            : closed.exitCode === null ? "Terminal durduruldu"
              : closed.exitCode === 0 ? "Terminal bitti"
                : `Terminal hata ile kapandı (çıkış kodu: ${closed.exitCode})`}
      </span>
    </div>
  );
}
