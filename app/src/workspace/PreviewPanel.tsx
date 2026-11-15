import { useEffect, useMemo, useRef, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { isPickShortcut } from "../browser/BrowserToolbar";
import { kabukVar } from "../voice/bridge";
import { ayriKokenliOnizlemeAdresi } from "./htmlPreviewSource";
import { PreviewLaunch } from "./PreviewLaunch";
import { PreviewLog } from "./PreviewLog";
import { PreviewScreenshot } from "./PreviewScreenshot";
import { DEFAULT_VIEWPORT_ID, PREVIEW_VIEWPORTS, findViewport, frameWidth } from "./previewViewports";
import "./PreviewPanel.css";

type PreviewKind = "image" | "audio" | "video" | "pdf" | "html" | "text";
interface PreviewAsset { yol: string; tur: PreviewKind; mime: string; boyut: number; base64: string }

const LOOPBACK_HOSTS = ["localhost", "127.0.0.1", "[::1]"];

const LOCAL_PROTOCOLS = ["http:", "https:"];

/** Yerel geliştirme sunucusu adresi mi (http ya da https loopback, P-041)? Uygulamanın KENDİ
 * kökeni (geliştirmede Vite portu) hariç: `allow-same-origin` + `allow-scripts` ile kendini
 * çerçeveleyen sayfa sandbox'ını söker (U4-48). Üretimde uygulama `tauri://localhost` olduğundan
 * loopback adresle çakışmaz. */
export function isLocalPreviewUrl(value: string): boolean {
  try {
    const url = new URL(value);
    if (!LOCAL_PROTOCOLS.includes(url.protocol) || !LOOPBACK_HOSTS.includes(url.hostname)) return false;
    const own = window.location;
    const ownIsLoopback = own.protocol === url.protocol && LOOPBACK_HOSTS.includes(own.hostname);
    const defaultPort = url.protocol === "https:" ? "443" : "80";
    return !(ownIsLoopback && (url.port || defaultPort) === (own.port || defaultPort));
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

/** Geçersiz base64 render sırasında fırlayıp paneli çökertmesin; `null` = çözülemedi (U4-46). */
function textFromBase64(value: string): string | null {
  try {
    const bytes = Uint8Array.from(atob(value), (character) => character.charCodeAt(0));
    return new TextDecoder().decode(bytes);
  } catch {
    return null;
  }
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
  revision?: number;
  /** Ajanın başlattığı önizleme (`PreviewReady`): gelince web kipinde açılır. `seq`
   *  aynı adresin yeniden istenmesini (sayfa yenilensin) ayırt eder. */
  requestedUrl?: { url: string; seq: number } | null;
  /** Uygulama içi Tarayıcı paneline aktar (P-045): uzak adres ya da öğe seçici (`pick`). */
  onOpenInBrowser?: (url: string, pick?: boolean) => void;
}

/** Önizlemeye gömülemeyen ama Tarayıcı panelinde açılabilen adres (http/https). */
function browsableUrl(value: string): string | null {
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
  } catch {
    return null;
  }
}

async function openWithSystem(url: string): Promise<void> {
  const { openUrl } = await import("@tauri-apps/plugin-opener");
  await openUrl(url);
}

type PreviewMode = "file" | "web";
/** Alt çekmece: konsol/ağ günlüğü ya da ekran görüntüsü (P-041); ikisi aynı anda açılmaz. */
type PreviewDrawer = "none" | "log" | "shot";

export function PreviewPanel({
  client,
  openExternal = openWithSystem,
  selectedPath,
  requestedUrl = null,
  revision = 0,
  onOpenInBrowser,
}: PreviewPanelProps) {
  const [asset, setAsset] = useState<PreviewAsset | null>(null);
  const [assetError, setAssetError] = useState<string | null>(null);
  const [assetLoading, setAssetLoading] = useState(false);
  const [mode, setMode] = useState<PreviewMode>(selectedPath ? "file" : "web");
  const [input, setInput] = useState("");
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const [addressError, setAddressError] = useState<string | null>(null);
  /** Önizlemeye gömülemeyen adres: Tarayıcı paneline aktarılabilir. */
  const [remoteUrl, setRemoteUrl] = useState<string | null>(null);
  const [frameError, setFrameError] = useState<string | null>(null);
  const [frameErrorUrl, setFrameErrorUrl] = useState<string | null>(null);
  /** Kendinden imzalı yerel https: WebView iframe'i boş bırakabilir, Tarayıcı paneli önerilir. */
  const [tlsNote, setTlsNote] = useState<string | null>(null);
  const [frameChecking, setFrameChecking] = useState(false);
  const [frameRevision, setFrameRevision] = useState(0);
  const [viewportId, setViewportId] = useState<string>(DEFAULT_VIEWPORT_ID);
  const [drawer, setDrawer] = useState<PreviewDrawer>("none");
  const viewport = findViewport(viewportId);
  const [objectUrl, setObjectUrl] = useState("");
  const inputValueRef = useRef("");
  const modeRefs = useRef<Record<PreviewMode, HTMLButtonElement | null>>({ file: null, web: null });
  const validationRun = useRef(0);
  const localUrl = historyIndex >= 0 ? history[historyIndex] ?? null : null;
  // Cmd/Ctrl+Shift+S: önizlenen sayfayı öğe seçiciyle Tarayıcı paneline aç (#444). Tarayıcı
  // paneli de dinliyorsa önce işleyen `preventDefault` ile ötekini susturur.
  useEffect(() => {
    if (!localUrl || !onOpenInBrowser) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || !isPickShortcut(event)) return;
      event.preventDefault();
      onOpenInBrowser(localUrl, true);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [localUrl, onOpenInBrowser]);
  // Büyük metin/HTML varlığı her render'da (adres kutusundaki her tuşta) yeniden çözülmesin.
  const assetText = useMemo(
    () => (asset && (asset.tur === "html" || asset.tur === "text") ? textFromBase64(asset.base64) : null),
    [asset],
  );

  useEffect(() => {
    let active = true;
    setAsset(null);
    setAssetError(null);
    setAssetLoading(Boolean(selectedPath));
    if (!selectedPath) return () => { active = false; };
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
  }, [client, selectedPath, revision]);

  // HTML önizlemesi ayrı kökenden sunulur (U4-47); `undefined`: henüz çözülmedi, `null`: srcdoc yedeği.
  const [htmlSrc, setHtmlSrc] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    setHtmlSrc(undefined);
    if (asset?.tur !== "html" || assetText === null) return;
    let active = true;
    void ayriKokenliOnizlemeAdresi(assetText).then((src) => { if (active) setHtmlSrc(src); });
    return () => { active = false; };
  }, [asset, assetText]);

  useEffect(() => { if (selectedPath) setMode("file"); }, [client, selectedPath]);

  useEffect(() => {
    setObjectUrl("");
    if (!asset || asset.tur === "html" || asset.tur === "text") return;
    const url = URL.createObjectURL(new Blob([bytesFromBase64(asset.base64)], { type: asset.mime }));
    setObjectUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [asset]);

  useEffect(() => {
    if (!requestedUrl || !isLocalPreviewUrl(requestedUrl.url)) return;
    setMode("web");
    setInput(requestedUrl.url);
    inputValueRef.current = requestedUrl.url;
    void openAddress(requestedUrl.url);
    // Yalnız yeni istek tetikler; `openAddress` her çizimde yeniden kurulur.
  }, [requestedUrl?.seq]);

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
        setTlsNote(null);
        return null;
      }
      setTlsNote(result.kendinden_imzali === true
        ? (typeof result.not === "string" && result.not ? result.not : "Sertifika kendinden imzalı.")
        : null);
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
  const openLocal = async () => openAddress(input.trim());
  const openAddress = async (value: string) => {
    if (!isLocalPreviewUrl(value)) {
      validationRun.current += 1;
      setFrameChecking(false);
      setRemoteUrl(onOpenInBrowser ? browsableUrl(value) : null);
      setAddressError("Güvenlik için önizlemeye yalnız localhost adresleri gömülür.");
      return;
    }
    setAddressError(null);
    setRemoteUrl(null);
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
                  setRemoteUrl(null);
                  setFrameChecking(false);
                  setFrameError(null);
                  setFrameErrorUrl(null);
                }} placeholder="http://localhost:5173" value={input} />
                <button aria-label="Adrese git" disabled={frameChecking} type="submit">Git</button>
              </form>
              <select
                aria-label="Önizleme boyutu"
                onChange={(event) => setViewportId(event.target.value)}
                value={viewportId}
              >
                {PREVIEW_VIEWPORTS.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
              </select>
              <div className="preview-panel__actions">
                <button
                  aria-label="Konsol ve ağ günlüğü"
                  aria-pressed={drawer === "log"}
                  disabled={!localUrl}
                  onClick={() => setDrawer((current) => (current === "log" ? "none" : "log"))}
                  title="Konsol ve ağ günlüğü"
                  type="button"
                >≡</button>
                <button
                  aria-label="Ekran görüntüsü al"
                  aria-pressed={drawer === "shot"}
                  disabled={!localUrl}
                  onClick={() => setDrawer((current) => (current === "shot" ? "none" : "shot"))}
                  title="Ekran görüntüsü al"
                  type="button"
                >◧</button>
                {onOpenInBrowser && (
                  <button
                    aria-label="Öğe seç (Tarayıcı panelinde)"
                    disabled={!localUrl}
                    onClick={() => { if (localUrl) onOpenInBrowser(localUrl, true); }}
                    title="Öğe seç (⌘⇧S): sayfayı Tarayıcı panelinde açar, tıkladığın öğe sohbete eklenir"
                    type="button"
                  >⌖</button>
                )}
                <button aria-label="Dışarıda aç" disabled={!localUrl} onClick={() => void launchExternal()} title="Dışarıda aç" type="button">↗</button>
              </div>
            </div>
            {addressError && (
              <p className="preview-panel__address-error" role="alert">
                {addressError}
                {remoteUrl && onOpenInBrowser && (
                  <button className="preview-panel__inline-action" onClick={() => onOpenInBrowser(remoteUrl)} type="button">
                    Tarayıcı panelinde aç
                  </button>
                )}
              </p>
            )}
            <PreviewLaunch
              client={client}
              disabled={frameChecking}
              onStarted={(url) => {
                setInput(url);
                inputValueRef.current = url;
                void openAddress(url);
              }}
            />
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
            <div className="preview-panel__stage" data-note={tlsNote ? "tls" : undefined}>
              {tlsNote && (
                <p className="preview-panel__tls-note" role="status">
                  {tlsNote}
                  {onOpenInBrowser && (
                    <button className="preview-panel__inline-action" onClick={() => onOpenInBrowser(localUrl)} type="button">
                      Tarayıcı panelinde aç
                    </button>
                  )}
                </p>
              )}
              <div className="preview-panel__viewport" data-testid="web-preview-viewport" data-viewport={viewport.id}>
                <iframe
                  className="preview-panel__frame"
                  data-revision={frameRevision}
                  key={`${localUrl}-${frameRevision}`}
                  sandbox="allow-forms allow-modals allow-pointer-lock allow-same-origin allow-scripts"
                  src={localUrl}
                  style={{ width: frameWidth(viewport) }}
                  title="Yerel geliştirme önizlemesi"
                />
              </div>
              {drawer === "log" && <PreviewLog client={client} onClose={() => setDrawer("none")} url={localUrl} />}
              {drawer === "shot" && (
                <PreviewScreenshot client={client} onClose={() => setDrawer("none")} url={localUrl} viewport={viewport} />
              )}
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
              {(asset.tur === "html" || asset.tur === "text") && assetText === null && (
                <p className="preview-panel__error" role="alert">Dosya içeriği çözülemedi.</p>
              )}
              {asset.tur === "html" && assetText !== null && htmlSrc === undefined && kabukVar() && (
                <p className="preview-panel__empty">Önizleme hazırlanıyor…</p>
              )}
              {/* Opak köken: allow-same-origin YOK. Ayrı kökenli adres kendi CSP'siyle gelir; yedek srcdoc ana CSP'yi miras alır. */}
              {asset.tur === "html" && assetText !== null && htmlSrc !== undefined && (
                <iframe
                  className="preview-panel__frame"
                  sandbox="allow-scripts"
                  title={`${asset.yol} HTML önizlemesi`}
                  {...(htmlSrc === null ? { srcDoc: assetText } : { src: htmlSrc })}
                />
              )}
              {asset.tur === "text" && assetText !== null && <pre>{assetText}</pre>}
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
