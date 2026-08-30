import { useEffect, useRef, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import "./PreviewPanel.css";

type PreviewKind = "image" | "audio" | "video" | "pdf" | "html" | "text";
interface PreviewAsset { yol: string; tur: PreviewKind; mime: string; boyut: number; base64: string }

export function isLocalPreviewUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "http:" && ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  } catch {
    return false;
  }
}

function decode(payload: Record<string, unknown>): PreviewAsset {
  if (payload.ok !== true) {
    throw new Error(typeof payload.metin === "string" ? payload.metin : "Önizleme alınamadı.");
  }
  const kinds: PreviewKind[] = ["image", "audio", "video", "pdf", "html", "text"];
  if (
    typeof payload.yol !== "string" || typeof payload.tur !== "string" ||
    !kinds.includes(payload.tur as PreviewKind) || typeof payload.mime !== "string" ||
    typeof payload.boyut !== "number" || typeof payload.base64 !== "string"
  ) throw new Error("Geçersiz önizleme verisi alındı.");
  return payload as unknown as PreviewAsset;
}

function textFromBase64(value: string): string {
  const bytes = Uint8Array.from(atob(value), (character) => character.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

function bytesFromBase64(value: string): Uint8Array<ArrayBuffer> {
  const raw = atob(value);
  const bytes = new Uint8Array(raw.length);
  for (let index = 0; index < raw.length; index += 1) bytes[index] = raw.charCodeAt(index);
  return bytes;
}

export interface PreviewPanelProps {
  client: ProtocolClient;
  openExternal?: (url: string) => Promise<void>;
  selectedPath: string | null;
}

async function openWithSystem(url: string): Promise<void> {
  const { openUrl } = await import("@tauri-apps/plugin-opener");
  await openUrl(url);
}

type PreviewMode = "file" | "web";
type PreviewViewport = "desktop" | "tablet" | "mobile";

export function PreviewPanel({ client, openExternal = openWithSystem, selectedPath }: PreviewPanelProps) {
  const [asset, setAsset] = useState<PreviewAsset | null>(null);
  const [assetError, setAssetError] = useState<string | null>(null);
  const [assetLoading, setAssetLoading] = useState(false);
  const [mode, setMode] = useState<PreviewMode>(selectedPath ? "file" : "web");
  const [input, setInput] = useState("");
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const [addressError, setAddressError] = useState<string | null>(null);
  const [frameError, setFrameError] = useState<string | null>(null);
  const [frameErrorUrl, setFrameErrorUrl] = useState<string | null>(null);
  const [frameChecking, setFrameChecking] = useState(false);
  const [frameRevision, setFrameRevision] = useState(0);
  const [viewport, setViewport] = useState<PreviewViewport>("desktop");
  const [objectUrl, setObjectUrl] = useState("");
  const inputValueRef = useRef("");
  const modeRefs = useRef<Record<PreviewMode, HTMLButtonElement | null>>({ file: null, web: null });
  const validationRun = useRef(0);
  const localUrl = historyIndex >= 0 ? history[historyIndex] ?? null : null;

  useEffect(() => {
    let active = true;
    setAsset(null);
    setAssetError(null);
    setAssetLoading(Boolean(selectedPath));
    if (!selectedPath) return () => { active = false; };
    setMode("file");
    void client.request("proje.onizle", { yol: selectedPath })
      .then((payload) => {
        if (!active) return;
        setAsset(decode(payload));
        setAssetLoading(false);
      })
      .catch((reason) => {
        if (!active) return;
        setAssetError(reason instanceof Error ? reason.message : String(reason));
        setAssetLoading(false);
      });
    return () => { active = false; };
  }, [client, selectedPath]);

  useEffect(() => {
    setObjectUrl("");
    if (!asset || asset.tur === "html" || asset.tur === "text") return;
    const url = URL.createObjectURL(new Blob([bytesFromBase64(asset.base64)], { type: asset.mime }));
    setObjectUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [asset]);

  const validateAddress = async (value: string): Promise<string | null> => {
    const run = ++validationRun.current;
    setFrameChecking(true);
    setFrameError(null);
    setFrameErrorUrl(null);
    try {
      const result = await client.request("web.onizleme_dogrula", { url: value });
      if (run !== validationRun.current) return null;
      if (result.ok !== true || typeof result.url !== "string" || !isLocalPreviewUrl(result.url)) {
        setFrameError(typeof result.metin === "string" ? result.metin : "Yerel önizleme doğrulanamadı.");
        setFrameErrorUrl(value);
        return null;
      }
      return result.url;
    } catch (reason) {
      if (run !== validationRun.current) return null;
      setFrameError(reason instanceof Error ? reason.message : "Yerel önizleme doğrulanamadı.");
      setFrameErrorUrl(value);
      return null;
    } finally {
      if (run === validationRun.current) setFrameChecking(false);
    }
  };
  const openLocal = async () => {
    const value = input.trim();
    if (!isLocalPreviewUrl(value)) {
      validationRun.current += 1;
      setFrameChecking(false);
      setAddressError("Güvenlik için uygulama içine yalnız localhost adresleri açılabilir.");
      return;
    }
    setAddressError(null);
    const verified = await validateAddress(value);
    if (!verified || inputValueRef.current.trim() !== value) return;
    const next = history.slice(0, historyIndex + 1);
    if (next[next.length - 1] !== verified) next.push(verified);
    setHistory(next);
    setHistoryIndex(next.length - 1);
    setFrameError(null);
    setFrameErrorUrl(null);
    setInput(verified);
    inputValueRef.current = verified;
    setFrameRevision((current) => current + 1);
  };
  const moveHistory = async (nextIndex: number) => {
    if (nextIndex < 0 || nextIndex >= history.length) return;
    const verified = await validateAddress(history[nextIndex]);
    if (!verified) return;
    const nextHistory = [...history];
    nextHistory[nextIndex] = verified;
    setHistory(nextHistory);
    setHistoryIndex(nextIndex);
    setInput(verified);
    inputValueRef.current = verified;
    setAddressError(null);
    setFrameError(null);
    setFrameErrorUrl(null);
    setFrameRevision((current) => current + 1);
  };
  const refreshFrame = async () => {
    if (!localUrl) return;
    if (!await validateAddress(localUrl)) return;
    setFrameError(null);
    setFrameErrorUrl(null);
    setFrameRevision((current) => current + 1);
  };
  const launchExternal = async (url = localUrl) => {
    if (!url) return;
    try {
      await openExternal(url);
    } catch {
      setFrameError("Önizleme sistem tarayıcısında açılamadı.");
      setFrameErrorUrl(url);
    }
  };
  const moveModeFocus = (current: PreviewMode, key: string) => {
    const modes: PreviewMode[] = ["file", "web"];
    const currentIndex = modes.indexOf(current);
    const next = key === "Home" ? modes[0]
      : key === "End" ? modes[modes.length - 1]
        : key === "ArrowLeft" ? modes[(currentIndex - 1 + modes.length) % modes.length]
          : key === "ArrowRight" ? modes[(currentIndex + 1) % modes.length]
            : null;
    if (!next) return false;
    setMode(next);
    window.requestAnimationFrame(() => modeRefs.current[next]?.focus());
    return true;
  };

  return (
    <div className="preview-panel">
      <div aria-label="Önizleme türü" className="preview-panel__modes" role="tablist">
        {(["file", "web"] as const).map((item) => (
          <button
            aria-controls={`preview-${item}-panel`}
            aria-selected={mode === item}
            key={item}
            onClick={() => setMode(item)}
            onKeyDown={(event) => {
              if (moveModeFocus(item, event.key)) event.preventDefault();
            }}
            ref={(node) => { modeRefs.current[item] = node; }}
            role="tab"
            tabIndex={mode === item ? 0 : -1}
            type="button"
          >
            {item === "file" ? "Dosya" : "Web"}
          </button>
        ))}
      </div>

      <section aria-label="Web önizlemesi" className="preview-panel__web" hidden={mode !== "web"} id="preview-web-panel" role="tabpanel">
          <div className="preview-panel__chrome">
            <div className="preview-panel__toolbar">
              <div className="preview-panel__navigation">
                <button aria-label="Geri" disabled={frameChecking || historyIndex <= 0} onClick={() => void moveHistory(historyIndex - 1)} title="Geri" type="button">‹</button>
                <button aria-label="İleri" disabled={frameChecking || historyIndex < 0 || historyIndex >= history.length - 1} onClick={() => void moveHistory(historyIndex + 1)} title="İleri" type="button">›</button>
                <button aria-label="Yenile" disabled={frameChecking || !localUrl} onClick={() => void refreshFrame()} title="Yenile" type="button">↻</button>
              </div>
              <form onSubmit={(event) => { event.preventDefault(); void openLocal(); }}>
                <label className="preview-panel__sr-only" htmlFor="local-preview-url">Yerel önizleme adresi</label>
                <input id="local-preview-url" onChange={(event) => {
                  validationRun.current += 1;
                  inputValueRef.current = event.target.value;
                  setInput(event.target.value);
                  setAddressError(null);
                  setFrameChecking(false);
                  setFrameError(null);
                  setFrameErrorUrl(null);
                }} placeholder="http://localhost:5173" value={input} />
                <button aria-label="Adrese git" disabled={frameChecking} type="submit">Git</button>
              </form>
              <select
                aria-label="Önizleme boyutu"
                onChange={(event) => setViewport(event.target.value as PreviewViewport)}
                value={viewport}
              >
                <option value="desktop">Masaüstü</option>
                <option value="tablet">Tablet</option>
                <option value="mobile">Mobil</option>
              </select>
              <button aria-label="Dışarıda aç" disabled={!localUrl} onClick={() => void launchExternal()} title="Dışarıda aç" type="button">↗</button>
            </div>
            {addressError && <p className="preview-panel__address-error" role="alert">{addressError}</p>}
          </div>

          {frameChecking ? (
            <div className="preview-panel__empty" role="status">
              <strong>Yerel sunucu doğrulanıyor…</strong>
              <p>Adres, yönlendirmeler ve gömme izinleri kontrol ediliyor.</p>
            </div>
          ) : frameError ? (
            <div className="preview-panel__frame-error" role="alert">
              <strong>Yerel önizleme yüklenemedi.</strong>
              <p>{frameError}</p>
              {frameErrorUrl && <button onClick={() => void launchExternal(frameErrorUrl)} type="button">Dışarıda aç</button>}
            </div>
          ) : localUrl ? (
            <div className="preview-panel__viewport" data-testid="web-preview-viewport" data-viewport={viewport}>
              <iframe
                className="preview-panel__frame"
                data-revision={frameRevision}
                key={`${localUrl}-${frameRevision}`}
                sandbox="allow-forms allow-modals allow-pointer-lock allow-same-origin allow-scripts"
                src={localUrl}
                title="Yerel geliştirme önizlemesi"
              />
            </div>
          ) : (
            <div className="preview-panel__empty">
              <strong>Yerel uygulamanı burada aç</strong>
              <p>Çalışan localhost adresini üstteki çubuğa yaz.</p>
            </div>
          )}
      </section>
      <section aria-label="Dosya önizlemesi" className="preview-panel__file" hidden={mode !== "file"} id="preview-file-panel" role="tabpanel">
          {assetError && <p className="preview-panel__error" role="alert">{assetError}</p>}
          {assetLoading ? (
            <p className="preview-panel__empty">Önizleme hazırlanıyor…</p>
          ) : asset ? (
            <div className="preview-panel__asset">
              <header><strong>{asset.yol}</strong><span>{asset.mime} · {asset.boyut.toLocaleString("tr-TR")} bayt</span></header>
              {asset.tur === "image" && objectUrl && <img alt={`${asset.yol} önizlemesi`} src={objectUrl} />}
              {asset.tur === "audio" && objectUrl && <audio controls src={objectUrl}>Ses önizlemesi desteklenmiyor.</audio>}
              {asset.tur === "video" && objectUrl && <video controls src={objectUrl}>Video önizlemesi desteklenmiyor.</video>}
              {asset.tur === "pdf" && objectUrl && <iframe className="preview-panel__frame" sandbox="" src={objectUrl} title={`${asset.yol} PDF önizlemesi`} />}
              {asset.tur === "html" && <iframe className="preview-panel__frame" sandbox="" srcDoc={textFromBase64(asset.base64)} title={`${asset.yol} HTML önizlemesi`} />}
              {asset.tur === "text" && <pre>{textFromBase64(asset.base64)}</pre>}
            </div>
          ) : !assetError ? (
            <div className="preview-panel__empty">
              <strong>Önizlenecek dosyayı seç</strong>
              <p>Dosyalar sekmesinden metin, görsel, ses, video veya PDF aç.</p>
            </div>
          ) : null}
      </section>
    </div>
  );
}
