/**
 * Model çıktısındaki bağlantı ve görsel adresleri için tek karar noktası.
 *
 * Uzak görsel `<img src>` olarak çizildiği anda tarayıcı isteği gönderir; adrese
 * gömülü veri (sohbetten sızdırılmış bir sır olabilir) kullanıcı hiçbir şeye
 * tıklamadan dışarı çıkar. Referrer gizlemek bunu engellemez. Bu yüzden uzak
 * görsel ancak kullanıcı yüklemeyi seçince istenir; bağlantılar açık bir şema
 * izin listesinden geçer.
 */

export type ImageSourceDecision =
  | { kind: "local"; src: string }
  | { kind: "remote"; src: string; host: string }
  | { kind: "blocked" };

const SAFE_LINK_PROTOCOLS = new Set(["http:", "https:", "mailto:"]);
const REMOTE_IMAGE_PROTOCOLS = new Set(["http:", "https:"]);
/** Mutlak yol ya da file:// — Tauri varlık protokolüne çevrilir. */
const LOCAL_PATH = /^(?:file:\/\/|\/|[A-Za-z]:[\\/])/;

/**
 * `file://` adresini yola çevirir. Hatalı `%` dizisi (`a%zz.png`) render'ı çökertmesin diye ham
 * hâli kullanılır; `file://localhost/x` ana makine adını atar ve `file:///C:/x` Windows sürücüsüne
 * döner (U5-22).
 */
function fileUrlToPath(href: string): string {
  let path = href.slice("file://".length);
  if (/^localhost\//i.test(path)) path = path.slice("localhost".length);
  try {
    path = decodeURIComponent(path);
  } catch {
    // Geçersiz kaçış: olduğu gibi bırak.
  }
  return /^\/[A-Za-z]:[\\/]/.test(path) ? path.slice(1) : path;
}

function parse(href: string): URL | null {
  try {
    return new URL(href);
  } catch {
    return null;
  }
}

/** Bağlantı güvenli bir şemadaysa adresi, değilse `null` (düz metin çizilir). */
export function safeLinkHref(href: string): string | null {
  const trimmed = href.trim();
  if (trimmed.startsWith("#")) return trimmed;
  const url = parse(trimmed);
  return url && SAFE_LINK_PROTOCOLS.has(url.protocol) ? trimmed : null;
}

/** Relative files open through the project preview, never through browser navigation. */
export function projectFilePath(href: string): string | null {
  if (!href || href !== href.trim() || /%2f|%5c/i.test(href)) return null;
  let path: string;
  try {
    path = decodeURIComponent(href);
  } catch {
    return null;
  }
  // No schemes, drives, UNC paths, fragments, query strings, nested encoding or controls.
  if (path.startsWith("/") || /[\\:#?%\u0000-\u001f\u007f-\u009f]/.test(path)) return null;
  const parts = path.split("/");
  if (parts[0] === ".") parts.shift();
  if (!parts.length || parts.some((part) => !part || part === "." || part === ".."
    || part !== part.trim() || /[. ]$/.test(part))) return null;
  return parts.join("/");
}

/** Görsel yerel mi, uzak mı (onay ister), yoksa engellenmiş mi? */
export function classifyImageSource(
  href: string,
  toAsset: (path: string) => string | null,
): ImageSourceDecision {
  const trimmed = href.trim();
  if (LOCAL_PATH.test(trimmed)) {
    const path = trimmed.startsWith("file://") ? fileUrlToPath(trimmed) : trimmed;
    const src = toAsset(path);
    return src === null ? { kind: "blocked" } : { kind: "local", src };
  }
  const url = parse(trimmed);
  if (!url || !REMOTE_IMAGE_PROTOCOLS.has(url.protocol)) return { kind: "blocked" };
  return { kind: "remote", src: trimmed, host: url.host };
}
