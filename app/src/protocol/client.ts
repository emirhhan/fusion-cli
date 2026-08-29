import type { Cevap, GelenMesaj, Istek } from "./types";

type Cozucu = (veri: Record<string, unknown>) => void;

/**
 * Protokol istemcisi.
 *
 * Taşımadan bağımsızdır: satır gönderen ve satır dinleyen iki fonksiyon alır.
 * Böylece gerçek süreç başlatmadan test edilebilir.
 *
 * Hiçbir bozuk satır istemciyi düşürmez; çözülemeyen satır atlanır.
 */
export class ProtocolClient {
  private sayac = 0;
  private bekleyen = new Map<string, Cozucu>();
  private olayDinleyicileri: ((veri: Record<string, unknown>) => void)[] = [];
  private soruDinleyicileri: ((id: string, veri: Record<string, unknown>) => void)[] = [];

  constructor(
    private readonly gonder: (satir: string) => void,
    dinle: (f: (satir: string) => void) => void,
  ) {
    dinle((satir) => this.satirAlindi(satir));
  }

  request(ad: string, veri: Record<string, unknown>): Promise<Record<string, unknown>> {
    const id = String(++this.sayac);
    const istek: Istek = { tip: "istek", id, ad, veri };
    return new Promise((cozumle) => {
      this.bekleyen.set(id, cozumle);
      this.gonder(JSON.stringify(istek));
    });
  }

  reply(id: string, veri: Record<string, unknown>): void {
    const cevap: Cevap = { tip: "cevap", id, veri };
    this.gonder(JSON.stringify(cevap));
  }

  onEvent(f: (veri: Record<string, unknown>) => void): void {
    this.olayDinleyicileri.push(f);
  }

  onQuestion(f: (id: string, veri: Record<string, unknown>) => void): void {
    this.soruDinleyicileri.push(f);
  }

  close(): void {
    this.bekleyen.clear();
    this.olayDinleyicileri = [];
    this.soruDinleyicileri = [];
  }

  private satirAlindi(satir: string): void {
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
      const cozumle = this.bekleyen.get(mesaj.id);
      if (!cozumle) return; // Eşleşmeyen kimlik yok sayılır.
      this.bekleyen.delete(mesaj.id);
      cozumle(mesaj.veri ?? {});
    }
  }
}
