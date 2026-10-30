/**
 * `fusion://` derin bağlantı olayı (P-064).
 *
 * Rust (`derin_baglanti.rs`) adresi çözer ve `uygulama://derin-baglanti` olayıyla
 * `{ hedef, ... }` yükü yayınlar. Burada yük YENİDEN doğrulanır: dış kaynaktan gelen
 * veri güvenilmezdir; bilinmeyen hedef ya da bozuk alan sessizce yok sayılır.
 */

export const DEEP_LINK_EVENT = "uygulama://derin-baglanti";
export const TRAY_NEW_CHAT_EVENT = "uygulama://yeni-sohbet";

export type DerinBaglanti =
  | { hedef: "sohbet"; id: string }
  | { hedef: "yeni"; kok: string | null }
  | { hedef: "ayarlar"; bolum: string | null };

const KIMLIK = /^[A-Za-z0-9_-]{1,128}$/;

/** Olay yükünü doğrula; tanınmıyorsa null. */
export function parseDeepLink(payload: unknown): DerinBaglanti | null {
  if (!payload || typeof payload !== "object") return null;
  const yuk = payload as Record<string, unknown>;
  switch (yuk.hedef) {
    case "sohbet":
      return typeof yuk.id === "string" && KIMLIK.test(yuk.id) ? { hedef: "sohbet", id: yuk.id } : null;
    case "yeni":
      return { hedef: "yeni", kok: typeof yuk.kok === "string" && yuk.kok.startsWith("/") ? yuk.kok : null };
    case "ayarlar":
      return { hedef: "ayarlar", bolum: typeof yuk.bolum === "string" && /^[a-z]{1,32}$/.test(yuk.bolum) ? yuk.bolum : null };
    default:
      return null;
  }
}

/** Kullanıcıya göstermek/paylaşmak için adres üret (ör. "Bağlantıyı kopyala"). */
export function deepLinkFor(hedef: DerinBaglanti): string {
  switch (hedef.hedef) {
    case "sohbet":
      return `fusion://sohbet/${hedef.id}`;
    case "yeni":
      return hedef.kok ? `fusion://yeni?kok=${encodeURIComponent(hedef.kok)}` : "fusion://yeni";
    case "ayarlar":
      return hedef.bolum ? `fusion://ayarlar/${hedef.bolum}` : "fusion://ayarlar";
  }
}
