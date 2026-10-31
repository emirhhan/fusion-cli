import { useEffect, useState } from "react";
import type { ProtocolClient } from "../protocol/client";
import { screenshotSize, type PreviewViewport } from "./previewViewports";

/**
 * Önizlemenin ekran görüntüsü (P-041): seçili cihaz boyutunda, istenirse koyu temada,
 * çekirdeğin başsız tarayıcısıyla alınır ve proje içine (`.fusion/onizleme-ekran.png`)
 * yazılır; kullanıcı dosyayı sohbete sürükleyebilir ya da başka yerde açabilir.
 */
export interface ScreenshotResult { base64: string; mime: string; yol: string; genislik: number; yukseklik: number }

export function decodeScreenshot(payload: Record<string, unknown>): ScreenshotResult {
  if (payload.ok !== true || typeof payload.base64 !== "string") {
    throw new Error(typeof payload.metin === "string" && payload.metin ? payload.metin : "Ekran görüntüsü alınamadı.");
  }
  return {
    base64: payload.base64,
    mime: typeof payload.mime === "string" ? payload.mime : "image/png",
    yol: typeof payload.yol === "string" ? payload.yol : "",
    genislik: typeof payload.genislik === "number" ? payload.genislik : 0,
    yukseklik: typeof payload.yukseklik === "number" ? payload.yukseklik : 0,
  };
}

export interface PreviewScreenshotProps {
  client: ProtocolClient;
  url: string;
  viewport: PreviewViewport;
  onClose: () => void;
}

/** Sayfanın `prefers-color-scheme` taklidi; "system" = başsız tarayıcının varsayılanı. */
type ShotTheme = "system" | "light" | "dark";

/**
 * Boyut/tema hızlı değişirken her adımda Chromium açılmasın: kısa bekleme. Ölçüldü (31 Ekim):
 * 320→375→768 geçişi üç tarayıcı başlatıyor, en son biten dosyayı eziyordu (çekirdek tarafında
 * ayrıca tek-yakalama kilidi var).
 */
export const SCREENSHOT_DEBOUNCE_MS = 250;

export function PreviewScreenshot({ client, url, viewport, onClose }: PreviewScreenshotProps) {
  const [theme, setTheme] = useState<ShotTheme>("system");
  const [result, setResult] = useState<ScreenshotResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    setResult(null);
    const data: Record<string, unknown> = { url, ...screenshotSize(viewport) };
    if (theme !== "system") data.tema = theme;
    const zamanlayici = window.setTimeout(() => {
      void client.request("onizleme.ekran_goruntusu", data)
        .then((payload) => { if (active) setResult(decodeScreenshot(payload)); })
        .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : String(reason)); })
        .finally(() => { if (active) setLoading(false); });
    }, SCREENSHOT_DEBOUNCE_MS);
    return () => { active = false; window.clearTimeout(zamanlayici); };
  }, [client, url, viewport, theme]);

  return (
    <section aria-label="Ekran görüntüsü" className="preview-shot" data-testid="preview-shot">
      <header className="preview-log__bar">
        <strong>Ekran görüntüsü{result ? ` · ${result.genislik}×${result.yukseklik}` : ""}</strong>
        {result?.yol && <code className="preview-shot__path" title="Proje içindeki dosya">{result.yol}</code>}
        <label className="preview-panel__sr-only" htmlFor="preview-shot-theme">Ekran görüntüsü teması</label>
        <select id="preview-shot-theme" onChange={(event) => setTheme(event.target.value as ShotTheme)} value={theme}>
          <option value="system">Sistem teması</option>
          <option value="light">Açık</option>
          <option value="dark">Koyu</option>
        </select>
        <button aria-label="Ekran görüntüsünü kapat" onClick={onClose} title="Kapat" type="button">×</button>
      </header>
      {loading ? (
        <p className="preview-log__status" role="status">Görüntü alınıyor…</p>
      ) : error ? (
        <p className="preview-log__status preview-log__status--error" role="alert">{error}</p>
      ) : result ? (
        <img alt={`${url} ekran görüntüsü`} className="preview-shot__image" src={`data:${result.mime};base64,${result.base64}`} />
      ) : null}
    </section>
  );
}
