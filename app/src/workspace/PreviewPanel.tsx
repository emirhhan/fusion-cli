import { useEffect, useState } from "react";
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
  loadTimeoutMs?: number;
  openExternal?: (url: string) => Promise<void>;
  selectedPath: string | null;
}

async function openWithSystem(url: string): Promise<void> {
  const { openUrl } = await import("@tauri-apps/plugin-opener");
  await openUrl(url);
}

type PreviewMode = "file" | "web";
type PreviewViewport = "desktop" | "tablet" | "mobile";

export function PreviewPanel({ client, loadTimeoutMs = 8_000, openExternal = openWithSystem, selectedPath }: PreviewPanelProps) {
  const [asset, setAsset] = useState<PreviewAsset | null>(null);
  const [assetError, setAssetError] = useState<string | null>(null);
  const [assetLoading, setAssetLoading] = useState(false);
  const [mode, setMode] = useState<PreviewMode>(selectedPath ? "file" : "web");
  const [input, setInput] = useState("");
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const [addressError, setAddressError] = useState<string | null>(null);
  const [frameError, setFrameError] = useState<string | null>(null);
  const [frameLoaded, setFrameLoaded] = useState(false);
  const [frameRevision, setFrameRevision] = useState(0);
  const [viewport, setViewport] = useState<PreviewViewport>("desktop");
  const [objectUrl, setObjectUrl] = useState("");
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

  useEffect(() => {
    if (!localUrl || frameLoaded || frameError) return;
    const timer = window.setTimeout(() => {
      setFrameError("Sunucu zamanında yanıt vermedi veya bu sayfa uygulama içinde görüntülenemiyor.");
    }, loadTimeoutMs);
    return () => window.clearTimeout(timer);
  }, [frameError, frameLoaded, frameRevision, loadTimeoutMs, localUrl]);

  const openLocal = () => {
    const value = input.trim();
    if (!isLocalPreviewUrl(value)) {
      setAddressError("Güvenlik için uygulama içine yalnız localhost adresleri açılabilir.");
      return;
    }
    const next = history.slice(0, historyIndex + 1);
    if (next[next.length - 1] !== value) next.push(value);
    setHistory(next);
    setHistoryIndex(next.length - 1);
    setAddressError(null);
    setFrameError(null);
    setFrameLoaded(false);
    setFrameRevision((current) => current + 1);
  };
  const moveHistory = (nextIndex: number) => {
    if (nextIndex < 0 || nextIndex >= history.length) return;
    setHistoryIndex(nextIndex);
    setInput(history[nextIndex]);
    setAddressError(null);
    setFrameError(null);
    setFrameLoaded(false);
    setFrameRevision((current) => current + 1);
  };
  const refreshFrame = () => {
    if (!localUrl) return;
    setFrameError(null);
    setFrameLoaded(false);
    setFrameRevision((current) => current + 1);
  };
  const launchExternal = async () => {
    if (!localUrl) return;
    try {
      await openExternal(localUrl);
      setFrameError(null);
    } catch {
      setFrameError("Önizleme sistem tarayıcısında açılamadı.");
    }
  };

  return (
    <div className="preview-panel">
      <div aria-label="Önizleme türü" className="preview-panel__modes" role="tablist">
        {(["file", "web"] as const).map((item) => (
          <button
            aria-controls={mode === item ? `preview-${item}-panel` : undefined}
            aria-selected={mode === item}
            key={item}
            onClick={() => setMode(item)}
            role="tab"
            type="button"
          >
            {item === "file" ? "Dosya" : "Web"}
          </button>
        ))}
      </div>

      {mode === "web" ? (
        <section aria-label="Web önizlemesi" className="preview-panel__web" id="preview-web-panel" role="tabpanel">
          <div className="preview-panel__chrome">
            <div className="preview-panel__toolbar">
              <div className="preview-panel__navigation">
                <button aria-label="Geri" disabled={historyIndex <= 0} onClick={() => moveHistory(historyIndex - 1)} title="Geri" type="button">‹</button>
                <button aria-label="İleri" disabled={historyIndex < 0 || historyIndex >= history.length - 1} onClick={() => moveHistory(historyIndex + 1)} title="İleri" type="button">›</button>
                <button aria-label="Yenile" disabled={!localUrl} onClick={refreshFrame} title="Yenile" type="button">↻</button>
              </div>
              <form onSubmit={(event) => { event.preventDefault(); openLocal(); }}>
                <label className="preview-panel__sr-only" htmlFor="local-preview-url">Yerel önizleme adresi</label>
                <input id="local-preview-url" onChange={(event) => { setInput(event.target.value); setAddressError(null); }} placeholder="http://localhost:5173" value={input} />
                <button aria-label="Adrese git" type="submit">Git</button>
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

          {frameError ? (
            <div className="preview-panel__frame-error" role="alert">
              <strong>Yerel önizleme yüklenemedi.</strong>
              <p>{frameError}</p>
              {localUrl && <button onClick={() => void launchExternal()} type="button">Dışarıda aç</button>}
            </div>
          ) : localUrl ? (
            <div className="preview-panel__viewport" data-testid="web-preview-viewport" data-viewport={viewport}>
              <iframe
                className="preview-panel__frame"
                data-revision={frameRevision}
                key={`${localUrl}-${frameRevision}`}
                onError={() => setFrameError("Sunucu yanıt vermedi veya bu sayfa uygulama içinde görüntülenemiyor.")}
                onLoad={() => setFrameLoaded(true)}
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
      ) : (
        <section aria-label="Dosya önizlemesi" className="preview-panel__file" id="preview-file-panel" role="tabpanel">
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
      )}
    </div>
  );
}
