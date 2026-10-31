/**
 * Web önizlemesinin cihaz boyutları (P-041).
 *
 * Ölçüldü (31 Ekim): yalnız Masaüstü/Tablet/Mobil vardı ve genişlikler CSS'e gömülüydü;
 * 320/375/1024/1440 kırılımları denenemiyor, ekran görüntüsü RPC'si de aynı genişliği
 * bilmiyordu. Liste tek kaynaktır: hem iframe genişliği hem `onizleme.ekran_goruntusu`
 * isteği buradan okur. `width: null` = panelin tamamı.
 */
export interface PreviewViewport {
  id: string;
  label: string;
  /** CSS piksel genişliği; `null` panel genişliği. */
  width: number | null;
  /** Ekran görüntüsünde kullanılacak yükseklik. */
  height: number;
}

export const PREVIEW_VIEWPORTS: readonly PreviewViewport[] = [
  { id: "desktop", label: "Masaüstü", width: null, height: 800 },
  { id: "laptop", label: "1440", width: 1440, height: 900 },
  { id: "small-laptop", label: "1024", width: 1024, height: 768 },
  { id: "tablet", label: "Tablet · 768", width: 768, height: 1024 },
  { id: "mobile", label: "Mobil · 375", width: 375, height: 812 },
  { id: "mobile-small", label: "Mobil · 320", width: 320, height: 568 },
];

export const DEFAULT_VIEWPORT_ID = PREVIEW_VIEWPORTS[0].id;
/** Masaüstü (tam panel) için ekran görüntüsü genişliği: panel ölçüsü bilinmez, standart masaüstü. */
export const DESKTOP_SCREENSHOT_WIDTH = 1280;

export function findViewport(id: string): PreviewViewport {
  return PREVIEW_VIEWPORTS.find((item) => item.id === id) ?? PREVIEW_VIEWPORTS[0];
}

/** iframe'in satır içi genişliği; panelden genişse CSS `max-width` kırpar. */
export function frameWidth(viewport: PreviewViewport): string {
  return viewport.width === null ? "100%" : `${viewport.width}px`;
}

/** Ekran görüntüsü RPC'sine gidecek ölçü. */
export function screenshotSize(viewport: PreviewViewport): { genislik: number; yukseklik: number } {
  return { genislik: viewport.width ?? DESKTOP_SCREENSHOT_WIDTH, yukseklik: viewport.height };
}
