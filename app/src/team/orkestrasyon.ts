import type { Mesaj } from "../screens/Conversation";

/**
 * Ekip panosu (P-061) ve iş akışı panosu (P-062) olayları.
 *
 * Çekirdek her değişiklikte panonun TAM görüntüsünü yollar (`TeamBoardChanged`,
 * `WorkflowProgress`); burada fark birleştirilmez, aynı kimlikli pano yerinde
 * değiştirilir. Pano bir "ekip" mesajına bağlanır ve o koşunun alt ajan kartları
 * (`SubAgentStarted.group_size` = pano boyutu) aynı mesajda toplanır.
 */

export type DugumDurumu = "bekliyor" | "calisiyor" | "tamam" | "basarisiz" | "iptal" | "atlandi";

export interface AkisDugumu { id: string; etiket: string; durum: DugumDurumu; evre: string; ozet: string }

export interface IsAkisiDurumu {
  kimlik: string;
  ad: string;
  durum: string;
  evre: string;
  ajanSayisi: number;
  ajanTavani: number;
  dugumler: AkisDugumu[];
  sureSn: number;
  mesaj: string;
}

export interface PanoGorevi { id: string; baslik: string; durum: string; sahip: string; bagimli: string[]; sonuc: string }
export interface PanoUyesi { ad: string; uzman: string; durum: string; uyanma: number }
export interface PanoMesaji { kimden: string; kime: string; metin: string }

export interface EkipPanosu {
  ad: string;
  hedef: string;
  durum: string;
  gorevler: PanoGorevi[];
  uyeler: PanoUyesi[];
  mesajlar: PanoMesaji[];
}

function metin(deger: unknown): string {
  return typeof deger === "string" ? deger : "";
}

function sayi(deger: unknown): number {
  return typeof deger === "number" && Number.isFinite(deger) ? deger : 0;
}

function liste(deger: unknown): Record<string, unknown>[] {
  return Array.isArray(deger) ? deger.filter((x): x is Record<string, unknown> => !!x && typeof x === "object") : [];
}

const DUGUM_DURUMLARI = new Set<DugumDurumu>(["bekliyor", "calisiyor", "tamam", "basarisiz", "iptal", "atlandi"]);

export function akisDurumu(event: Record<string, unknown>): IsAkisiDurumu {
  return {
    kimlik: metin(event.run_id),
    ad: metin(event.name) || "iş akışı",
    durum: metin(event.status) || "calisiyor",
    evre: metin(event.phase),
    ajanSayisi: sayi(event.agents_started),
    ajanTavani: sayi(event.agents_limit),
    dugumler: liste(event.nodes).map((dugum) => {
      const durum = metin(dugum.status) as DugumDurumu;
      return {
        id: metin(dugum.id),
        etiket: metin(dugum.label),
        durum: DUGUM_DURUMLARI.has(durum) ? durum : "bekliyor",
        evre: metin(dugum.phase),
        ozet: metin(dugum.summary),
      };
    }),
    sureSn: sayi(event.elapsed_s),
    mesaj: metin(event.message),
  };
}

export function ekipPanosu(event: Record<string, unknown>): EkipPanosu {
  return {
    ad: metin(event.team),
    hedef: metin(event.goal),
    durum: metin(event.status) || "calisiyor",
    gorevler: liste(event.tasks).map((gorev) => ({
      id: metin(gorev.id),
      baslik: metin(gorev.title),
      durum: metin(gorev.status) || "bekliyor",
      sahip: metin(gorev.owner),
      bagimli: Array.isArray(gorev.depends_on) ? gorev.depends_on.filter((x): x is string => typeof x === "string") : [],
      sonuc: metin(gorev.result),
    })),
    uyeler: liste(event.members).map((uye) => ({
      ad: metin(uye.name),
      uzman: metin(uye.persona),
      durum: metin(uye.status) || "bekliyor",
      uyanma: sayi(uye.wakes),
    })),
    mesajlar: liste(event.messages).map((mesaj) => ({
      kimden: metin(mesaj.sender),
      kime: metin(mesaj.recipient),
      metin: metin(mesaj.text),
    })),
  };
}

function yerinde(messages: Mesaj[], bul: (mesaj: Mesaj) => boolean, guncelle: (mesaj: Mesaj) => Mesaj, yeni: () => Mesaj): Mesaj[] {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (bul(messages[index])) {
      const guncel = [...messages];
      guncel[index] = guncelle(messages[index]);
      return guncel;
    }
  }
  return [...messages, yeni()];
}

/** Pano olayıysa güncel akışı, değilse `null`. */
export function orkestrasyonOlayi(messages: Mesaj[], event: Record<string, unknown>): Mesaj[] | null {
  if (event.olay === "WorkflowProgress") {
    const akis = akisDurumu(event);
    if (!akis.kimlik) return messages;
    return yerinde(
      messages,
      (mesaj) => mesaj.akis?.kimlik === akis.kimlik,
      (mesaj) => ({ ...mesaj, akis }),
      () => ({ rol: "ekip", metin: akis.ad, ajanlar: [], grupBoyutu: Math.max(1, akis.dugumler.length), akis }),
    );
  }
  if (event.olay === "TeamBoardChanged") {
    const pano = ekipPanosu(event);
    if (!pano.ad) return messages;
    const grup = Math.max(1, sayi(event.group_size));
    return yerinde(
      messages,
      // Aynı ekibin YALNIZ son panosu güncellenir; kullanıcı yeni tur açtıysa yeni pano.
      (mesaj) => mesaj.pano?.ad === pano.ad && mesaj.pano.durum === "calisiyor",
      (mesaj) => ({ ...mesaj, pano }),
      () => ({ rol: "ekip", metin: pano.ad, ajanlar: [], grupBoyutu: grup, pano }),
    );
  }
  return null;
}
