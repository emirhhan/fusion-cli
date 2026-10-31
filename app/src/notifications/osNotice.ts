import { isPermissionGranted, requestPermission, sendNotification } from "@tauri-apps/plugin-notification";
import { kabukVar } from "../voice/bridge";

export interface OsBildirimBagimliliklari {
  kabukVar: () => boolean;
  uygulamaOdakta: () => boolean;
  izinVerildi: () => Promise<boolean>;
  izinIste: () => Promise<"granted" | "denied" | "default">;
  gonder: (secenekler: { title: string; body: string }) => void;
}

const varsayilan: OsBildirimBagimliliklari = {
  kabukVar,
  uygulamaOdakta: () => typeof document !== "undefined" && document.hasFocus() && document.visibilityState === "visible",
  izinVerildi: isPermissionGranted,
  izinIste: requestPermission,
  gonder: sendNotification,
};

export type OsBildirimSonucu = "gonderildi" | "izin-yok" | "odakta" | "kabuk-yok" | "hata";

export interface OsBildirimSecenekleri {
  /** Pencere odaktayken de gönder: kullanıcı BAŞKA sohbete bakıyordur (P-047). */
  odaktaDaGonder?: boolean;
}

/**
 * Kullanıcı uygulamada değilken (zamanlanmış görev onay beklerken) işletim sistemi bildirimi gösterir
 * (U5-57). Uygulama odaktayken uygulama içi şerit yeter; izin yoksa bir kez istenir, verilmezse
 * bildirim atlanır ve şerit tek kanal olarak kalır. Hata çağıranı bozmaz.
 */
export async function osBildirimiGonder(
  baslik: string,
  metin: string,
  bag: OsBildirimBagimliliklari = varsayilan,
  secenekler: OsBildirimSecenekleri = {},
): Promise<OsBildirimSonucu> {
  if (!bag.kabukVar()) return "kabuk-yok";
  if (!secenekler.odaktaDaGonder && bag.uygulamaOdakta()) return "odakta";
  try {
    if (!(await bag.izinVerildi()) && (await bag.izinIste()) !== "granted") return "izin-yok";
    bag.gonder({ title: baslik, body: metin });
    return "gonderildi";
  } catch {
    return "hata";
  }
}
