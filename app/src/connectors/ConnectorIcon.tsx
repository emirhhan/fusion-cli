import type { CatalogEntry } from "./catalog";
import { brandIcon } from "./brandIcons";

/**
 * Katalog kartlarının simgesi.
 *
 * Marka logosu VARSA kullanılır: kullanıcı bağlanacağı servisi bir harf
 * çiftinden değil, tanıdığı işaretten seçer. Eskiden hepsi monogramdı ve
 * "logoları bile yok" şikayeti bundandı.
 *
 * Logo YOKSA (Slack gibi marka setinden çıkarılmış ya da dosya sistemi gibi
 * markası olmayan bağlantılar) monogram kalır — uydurma bir logo, yanlış bir
 * logodan beterdir.
 */
export function ConnectorIcon({ entry, size = 40 }: { entry: CatalogEntry; size?: number }) {
  const marka = brandIcon(entry.id);

  if (marka) {
    return (
      <span
        aria-hidden="true"
        className="connector-icon connector-icon--brand"
        style={{
          // Kutu markanın kendi renginden çok hafif bir zemin alır; logo o
          // rengin tam tonunda durur. Koyu temada kutu yüzeye demirlenir,
          // yoksa saydam karışım kayboluyordu.
          background: `color-mix(in srgb, ${marka.hex} 14%, var(--surface-canvas))`,
          border: `1px solid color-mix(in srgb, ${marka.hex} 26%, transparent)`,
          height: size,
          width: size,
        }}
      >
        {/* Simge DEKORATİFtir: adı hemen yanında yazıyor. `<title>` eklemek
            markayı ekran okuyucuya ve metin sorgularına ikinci kez sokuyordu. */}
        <svg
          height={size * 0.5}
          viewBox="0 0 24 24"
          width={size * 0.5}
          xmlns="http://www.w3.org/2000/svg"
        >
          {/* Siyah logolar koyu temada kaybolur; tam siyah marka rengi metin
              rengine düşürülür. */}
          <path d={marka.path} fill={marka.hex === "#000000" ? "currentColor" : marka.hex} />
        </svg>
      </span>
    );
  }

  return (
    <span
      aria-hidden="true"
      className="connector-icon"
      style={{
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
