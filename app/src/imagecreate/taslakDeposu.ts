import type { Akis } from "./akis";

/**
 * Görsel oluştur taslağı (istem, akış, kip): bileşen sayfa değişince sökülür; kullanıcı Beceriler'e
 * gidip dönünce uzun bir istem kaybolmasın (U3-05). Sohbet taslakları da oturum durumunda tutulur.
 *
 * Yalnız bellekte durur (modül ömrü = uygulama ömrü): istem metni diske yazılmaz, gizlilik kararı gerekmez.
 */
export interface GorselTaslagi {
  akis: Akis;
  basitAkis: Akis;
  mod: "basit" | "akis";
}

const MAKS_KAPSAM = 20;
const depo = new Map<string, GorselTaslagi>();

export function taslagiOku(kapsam: string): GorselTaslagi | undefined {
  return depo.get(kapsam);
}

export function taslagiYaz(kapsam: string, taslak: GorselTaslagi): void {
  depo.delete(kapsam);
  depo.set(kapsam, taslak);
  // Eski kapsamlar birikmesin (en eskiden başlayarak at).
  while (depo.size > MAKS_KAPSAM) depo.delete(depo.keys().next().value as string);
}

/** Testler için. */
export function taslaklariSifirla(): void {
  depo.clear();
}
