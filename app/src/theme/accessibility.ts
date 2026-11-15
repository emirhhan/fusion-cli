/**
 * Erişilebilirlik tercihleri: yazı ölçeği, yüksek kontrast, hareketi azalt, vurgu rengi (P-065).
 *
 * `theme.ts` kalıbı: okuma/yazma ayrı, depo enjekte edilebilir, erişim düşerse varsayılan.
 * Uygulama belge köküne `data-*` öznitelikleriyle yapılır; CSS `accessibility.css`
 * bu öznitelikleri token'lara çevirir. Böylece her ekran tek kaynaktan etkilenir ve
 * tema (açık/koyu) ile çakışmaz.
 */

export const ACCESSIBILITY_STORAGE_KEY = "fusion.accessibility.v1";

export type FontScale = "small" | "normal" | "large" | "xlarge";
export type MotionPreference = "system" | "reduce" | "allow";
export type AccentPreference = "brand" | "blue" | "violet" | "mint";

export interface ErisilebilirlikTercihleri {
  fontScale: FontScale;
  highContrast: boolean;
  motion: MotionPreference;
  accent: AccentPreference;
}

export const VARSAYILAN_ERISILEBILIRLIK: ErisilebilirlikTercihleri = {
  fontScale: "normal",
  highContrast: false,
  motion: "system",
  accent: "brand",
};

/** Ölçek çarpanları: 15 px tabanın ±%12,5 adımları; en büyük %37,5 (iOS "Large Text" aralığı). */
export const FONT_SCALE_FACTORS: Record<FontScale, number> = {
  small: 0.875,
  normal: 1,
  large: 1.125,
  xlarge: 1.375,
};

const FONT_SCALES = new Set<string>(Object.keys(FONT_SCALE_FACTORS));
const MOTIONS = new Set<string>(["system", "reduce", "allow"]);
const ACCENTS = new Set<string>(["brand", "blue", "violet", "mint"]);

export function parseAccessibilityPreferences(raw: string | null): ErisilebilirlikTercihleri {
  if (!raw) return VARSAYILAN_ERISILEBILIRLIK;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return VARSAYILAN_ERISILEBILIRLIK;
    const kayit = parsed as Record<string, unknown>;
    return {
      fontScale: typeof kayit.fontScale === "string" && FONT_SCALES.has(kayit.fontScale) ? kayit.fontScale as FontScale : "normal",
      highContrast: kayit.highContrast === true,
      motion: typeof kayit.motion === "string" && MOTIONS.has(kayit.motion) ? kayit.motion as MotionPreference : "system",
      accent: typeof kayit.accent === "string" && ACCENTS.has(kayit.accent) ? kayit.accent as AccentPreference : "brand",
    };
  } catch {
    return VARSAYILAN_ERISILEBILIRLIK;
  }
}

export function readAccessibilityPreferences(storage?: Pick<Storage, "getItem">): ErisilebilirlikTercihleri {
  try {
    return parseAccessibilityPreferences((storage ?? localStorage).getItem(ACCESSIBILITY_STORAGE_KEY));
  } catch {
    return VARSAYILAN_ERISILEBILIRLIK;
  }
}

export function saveAccessibilityPreferences(
  tercihler: ErisilebilirlikTercihleri,
  storage?: Pick<Storage, "setItem">,
): void {
  try {
    (storage ?? localStorage).setItem(ACCESSIBILITY_STORAGE_KEY, JSON.stringify(tercihler));
  } catch {
    // Kalıcılaşmasa da bu pencerede uygulanır.
  }
}

/**
 * Tercihleri belge köküne uygula. Varsayılan değerler ÖZNİTELİK BIRAKMAZ: eski CSS
 * (öznitelik yokken) aynen çalışır, geri uyumluluk korunur.
 */
export function applyAccessibility(
  tercihler: ErisilebilirlikTercihleri,
  root: HTMLElement = document.documentElement,
): void {
  const ayarla = (ad: string, deger: string | null) => {
    if (deger === null) delete root.dataset[ad];
    else root.dataset[ad] = deger;
  };
  ayarla("fontScale", tercihler.fontScale === "normal" ? null : tercihler.fontScale);
  if (tercihler.fontScale === "normal") root.style.removeProperty("--font-scale");
  else root.style.setProperty("--font-scale", String(FONT_SCALE_FACTORS[tercihler.fontScale]));
  ayarla("contrast", tercihler.highContrast ? "high" : null);
  ayarla("motion", tercihler.motion === "system" ? null : tercihler.motion);
  ayarla("accent", tercihler.accent === "brand" ? null : tercihler.accent);
}

const aboneler = new Set<() => void>();
let anlik: ErisilebilirlikTercihleri | null = null;

function anlikDeger(): ErisilebilirlikTercihleri {
  if (anlik === null) anlik = readAccessibilityPreferences();
  return anlik;
}

export function subscribeAccessibility(listener: () => void): () => void {
  aboneler.add(listener);
  return () => {
    aboneler.delete(listener);
  };
}

export function getAccessibilityPreferences(): ErisilebilirlikTercihleri {
  return anlikDeger();
}

/** Tek alanı değiştir: kalıcılaştır, belge köküne uygula, açık ekranlara duyur. */
export function setAccessibilityPreference<K extends keyof ErisilebilirlikTercihleri>(
  anahtar: K,
  deger: ErisilebilirlikTercihleri[K],
): void {
  anlik = { ...anlikDeger(), [anahtar]: deger };
  saveAccessibilityPreferences(anlik);
  applyAccessibility(anlik);
  for (const listener of aboneler) listener();
}

/** Testler için depo önbelleğini sıfırla. */
export function resetAccessibilityCache(): void {
  anlik = null;
}
