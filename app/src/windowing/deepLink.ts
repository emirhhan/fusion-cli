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

/** Rust tarafındaki `derin_baglanti_al` komutu: soğuk açılışta bekletilen hedefi çeker. */
export const DEEP_LINK_PULL_COMMAND = "derin_baglanti_al";

/**
 * Yol ayracına bölünmüş parçalar (boşlar atılır); `/` için boş dizi.
 */
const parcalar = (kok: string): string[] => kok.split("/").filter(Boolean);

/** Kullanıcı ev dizinlerinin bulunduğu üst klasörler: altındaki ilk kademe ev dizinidir. */
const EV_USTLERI = new Set(["Users", "home"]);
/** Proje kökü olamayacak sistem klasörleri (ilk kademe). */
const SISTEM_KOKLERI = new Set([
  "", "bin", "sbin", "etc", "usr", "var", "tmp", "private", "dev", "proc", "sys", "System", "Library",
  "Applications", "cores", "opt",
]);

export type DeepLinkRootDecision = "onayla" | "reddet";

/**
 * Bağlantıdan gelen kök için karar: çok geniş ya da sistem klasörü ise reddedilir, kalanı
 * kullanıcıya SORULUR (onaysız açılmaz). Ölçüldü (31 Ekim): `fusion://yeni?kok=%2F` kökü
 * `/` olan bir kod sohbeti hazırlıyordu.
 */
export function deepLinkRootDecision(kok: string): DeepLinkRootDecision {
  if (!kok.startsWith("/") || kok.includes("\0") || /\/\.\.(\/|$)/.test(kok)) return "reddet";
  const parca = parcalar(kok);
  if (parca.length === 0) return "reddet";
  const [ilk] = parca;
  if (SISTEM_KOKLERI.has(ilk)) return "reddet";
  // `/Users`, `/Users/ali`, `/home/ali` çok geniştir; en az ev dizininin bir alt klasörü gerekir.
  if (EV_USTLERI.has(ilk) && parca.length < 3) return "reddet";
  if (!EV_USTLERI.has(ilk) && parca.length < 2) return "reddet";
  return "onayla";
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
