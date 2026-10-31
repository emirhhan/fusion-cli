import type { SurfaceSection } from "../sections/MainSurface";

/**
 * Ana uygulamanın gezinebileceği sayfalar; üst çubuktaki geri/ileri düğmeleri bu
 * sayfalar arasındaki geçmişi gezer (bkz. `useNavigationHistory`).
 */
export type Page =
  | "chat"
  | "skills"
  | "control"
  | "connectors"
  | "help"
  | "settings"
  | "account"
  | "image-create"
  | "video-create";

/**
 * Sohbet kabuğunda açılan sayfalar: sohbet ve sohbete iş üreten ekranlar (görsel/video
 * oluşturma komut paletinden açılır, Home vurgulu kalır). Sol sohbet kenar çubuğu
 * (Fusion başlığı, Yeni sohbet, Projeler) YALNIZ bu sayfalarda görünür.
 */
export const SOHBET_KABUGU_SAYFALARI: readonly Page[] = ["chat", "image-create", "video-create"];

/**
 * TAM SAYFA KURALI — tek yer burası.
 *
 * Sohbetle ilgisi olmayan her yönetim ekranı Ayarlar gibi tam sayfa açılır ve sohbet
 * kenar çubuğunu gizler: Ayarlar, Hesabım, Yardım, Kontrol Paneli, Beceriler ve Ajanlar,
 * MCP bağlantıları ve raydan açılan bölümler (Zamanlananlar, Kitaplık, Kits).
 * Kural "izin listesi" değil "istisna listesi"dir: yeni eklenen bir sayfa, açıkça
 * `SOHBET_KABUGU_SAYFALARI`na yazılmadıkça tam sayfa olur. Geri bildirim bir sayfa
 * değil, sohbetin üstünde açılan penceredir.
 */
export function isFullPage(page: Page, surfaceSection: SurfaceSection | null): boolean {
  return surfaceSection !== null || !SOHBET_KABUGU_SAYFALARI.includes(page);
}
