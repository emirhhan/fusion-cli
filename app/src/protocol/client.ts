import type { Cevap, GelenMesaj, Istek } from "./types";

type Cozucu = (veri: Record<string, unknown>) => void;
type Reddeden = (hata: Error) => void;

/** Kapanış nedeni verilmezse kullanılan varsayılan mesaj. */
const VARSAYILAN_KAPANIS_MESAJI = "Çekirdek bağlantısı kapatıldı.";

/**
 * Protokol istemcisi.
 *
 * Taşımadan bağımsızdır: satır gönderen ve satır dinleyen iki fonksiyon alır.
 * Böylece gerçek süreç başlatmadan test edilebilir.
 *
 * Hiçbir bozuk satır istemciyi düşürmez; çözülemeyen satır atlanır.
 *
 * `close()` çağrıldıktan sonra istemci kalıcı olarak kapalı sayılır: bekleyen
 * tüm istekler reddedilir (asla sessizce asılı kalmaz), yeni istekler hemen
 * reddedilir ve gelen satırlar yok sayılır.
 */
export class ProtocolClient {
  private sayac = 0;
  private bekleyen = new Map<string, { cozumle: Cozucu; reddet: Reddeden }>();
  private olayDinleyicileri: ((veri: Record<string, unknown>) => void)[] = [];
  private soruDinleyicileri: ((id: string, veri: Record<string, unknown>) => void)[] = [];
  private kapandi = false;

  constructor(
    private readonly gonder: (satir: string) => void,
    dinle: (f: (satir: string) => void) => void,
  ) {
    dinle((satir) => this.satirAlindi(satir));
  }

  request(ad: string, veri: Record<string, unknown>): Promise<Record<string, unknown>> {
    if (this.kapandi) {
      return Promise.reject(new Error(VARSAYILAN_KAPANIS_MESAJI));
    }
    const id = String(++this.sayac);
    const istek: Istek = { tip: "istek", id, ad, veri };
    return new Promise((cozumle, reddet) => {
      this.bekleyen.set(id, { cozumle, reddet });
      this.gonder(JSON.stringify(istek));
    });
  }

  reply(id: string, veri: Record<string, unknown>): void {
    const cevap: Cevap = { tip: "cevap", id, veri };
    this.gonder(JSON.stringify(cevap));
  }

  onEvent(f: (veri: Record<string, unknown>) => void): () => void {
    this.olayDinleyicileri.push(f);
    return () => {
      this.olayDinleyicileri = this.olayDinleyicileri.filter((listener) => listener !== f);
    };
  }

  onQuestion(f: (id: string, veri: Record<string, unknown>) => void): () => void {
    this.soruDinleyicileri.push(f);
    return () => {
      this.soruDinleyicileri = this.soruDinleyicileri.filter((listener) => listener !== f);
    };
  }

  /**
   * İstemciyi kapat: bekleyen tüm `request()` promise'leri REDDEDİLİR (asla
   * sessizce çözülmez — çağıran taraf hatayı görmelidir), bekleyen tablo ve
   * dinleyiciler temizlenir. Sonraki `satirAlindi` çağrıları yok sayılır.
   */
  close(mesaj: string = VARSAYILAN_KAPANIS_MESAJI): void {
    if (this.kapandi) return;
    this.kapandi = true;
    const hata = new Error(mesaj);
    for (const { reddet } of this.bekleyen.values()) reddet(hata);
    this.bekleyen.clear();
    this.olayDinleyicileri = [];
    this.soruDinleyicileri = [];
  }

  private satirAlindi(satir: string): void {
    if (this.kapandi) return;
    let mesaj: GelenMesaj;
    try {
      mesaj = JSON.parse(satir) as GelenMesaj;
    } catch {
      return; // Çözülemeyen satır atlanır; arayüz bozulmaz.
    }
    if (!mesaj || typeof mesaj !== "object") return;
    if (mesaj.tip === "olay") {
      this.olayDinleyicileri.forEach((f) => f(mesaj.veri ?? {}));
      return;
    }
    if (mesaj.tip === "soru" && mesaj.id) {
      this.soruDinleyicileri.forEach((f) => f(mesaj.id as string, mesaj.veri ?? {}));
      return;
    }
    if (mesaj.tip === "sonuc" && mesaj.id) {
      const beklenen = this.bekleyen.get(mesaj.id);
      if (!beklenen) return; // Eşleşmeyen kimlik yok sayılır.
      this.bekleyen.delete(mesaj.id);
      beklenen.cozumle(mesaj.veri ?? {});
    }
  }
}
