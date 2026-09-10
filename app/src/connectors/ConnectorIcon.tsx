import type { CatalogEntry } from "./catalog";

/** Katalog kartlarının ikon kutusu.
 *
 * Marka logolarını gömmek yerine (telif ve iki-tema okunurluğu derdi) monogram +
 * kategori tint'i kullanılır; ProviderLogo'nun "kurumsal rengi taklit etme"
 * ilkesiyle aynı çizgi. Tint yalnız ikon kutusunda görünür, metinde değil.
 */
export function ConnectorIcon({ entry, size = 40 }: { entry: CatalogEntry; size?: number }) {
  return (
    <span
      aria-hidden="true"
      className="connector-icon"
      style={{
        // Kutu dolgusu tint'in üstüne yüzey karışımıyla kurulur: koyu temada
        // düz saydam karışım kayboluyordu, yüzeye demirlemek iki temada da
        // görünür bir kutu bırakır. İnce kenarlık kenarı yüzeyden ayırır.
        background: `color-mix(in srgb, ${entry.tint} 20%, var(--surface-canvas))`,
        border: `1px solid color-mix(in srgb, ${entry.tint} 30%, transparent)`,
        color: entry.tint,
        height: size,
        width: size,
      }}
    >
      {entry.glyph}
    </span>
  );
}
