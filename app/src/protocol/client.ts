import type { Cevap, GelenMesaj, Istek } from "./types";

type Cozucu = (veri: Record<string, unknown>) => void;
type Reddeden = (hata: Error) => void;

/** Kapanış nedeni verilmezse kullanılan varsayılan mesaj. */
const VARSAYILAN_KAPANIS_MESAJI = "Çekirdek bağlantısı kapatıldı.";

/** Tek bir isteğin son süresi (ms) ve/veya iptal sinyali. */
export interface RequestOptions {
  timeoutMs?: number;
  signal?: AbortSignal;
}

/** Çekirdek son süre içinde cevap vermedi; geç gelen sonuç yok sayılır. */
export class RequestTimeoutError extends Error {
  readonly code = "TIMEOUT";
  constructor(ad: string, timeoutMs: number) {
    super(`Çekirdek ${Math.round(timeoutMs / 1000)} sn içinde cevap vermedi (${ad}).`);
    this.name = "RequestTimeoutError";
  }
}

/** İstek çağıran tarafından iptal edildi. */
export class RequestAbortedError extends Error {
  readonly code = "ABORTED";
  constructor(ad: string) {
    super(`İstek iptal edildi (${ad}).`);
    this.name = "RequestAbortedError";
  }
}

/**
 * Yalnız hızlı dönmesi GEREKEN çalışma alanı okumalarının varsayılan son süresi.
 * Tur, ses, giriş ve kurulum gibi istekler dakikalarca sürebilir; onlara varsayılan
 * süre konmaz, gerekiyorsa çağıran `timeoutMs` ya da `signal` verir.
 */
const OKUMA_SON_SURESI_MS = 30_000;
export const DEFAULT_DEADLINES_MS: Readonly<Record<string, number>> = {
  "proje.durum": OKUMA_SON_SURESI_MS,
  "proje.listele": OKUMA_SON_SURESI_MS,
  "proje.oku": OKUMA_SON_SURESI_MS,
  "proje.onizle": OKUMA_SON_SURESI_MS,
  "proje.degisiklikler": OKUMA_SON_SURESI_MS,
};

interface BekleyenIstek {
  cozumle: Cozucu;
  reddet: Reddeden;
  temizle: () => void;
}

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
  private bekleyen = new Map<string, BekleyenIstek>();
  private olayDinleyicileri: ((veri: Record<string, unknown>) => void)[] = [];
  private soruDinleyicileri: ((id: string, veri: Record<string, unknown>) => void)[] = [];
  private kapandi = false;

  constructor(
    private readonly gonder: (satir: string) => void,
    dinle: (f: (satir: string) => void) => void,
  ) {
    dinle((satir) => this.satirAlindi(satir));
  }

  /**
   * İstek gönder. Son süre dolarsa ya da sinyal iptal edilirse istek bekleyenlerden
   * ÇIKARILIR ve reddedilir: geç gelen sonuç kimliği eşleşmediği için yok sayılır,
   * başka bir isteğe asla yazılmaz.
   */
  request(
    ad: string,
    veri: Record<string, unknown>,
    options: RequestOptions = {},
  ): Promise<Record<string, unknown>> {
    if (this.kapandi) {
      return Promise.reject(new Error(VARSAYILAN_KAPANIS_MESAJI));
    }
    if (options.signal?.aborted) {
      return Promise.reject(new RequestAbortedError(ad));
    }
    const id = String(++this.sayac);
    const istek: Istek = { tip: "istek", id, ad, veri };
    const sure = options.timeoutMs ?? DEFAULT_DEADLINES_MS[ad];
    return new Promise((cozumle, reddet) => {
      const bitir = (hata: Error) => {
        const beklenen = this.bekleyen.get(id);
        if (!beklenen) return;
        this.bekleyen.delete(id);
        beklenen.temizle();
        reddet(hata);
      };
      const zamanlayici = sure !== undefined ? setTimeout(() => bitir(new RequestTimeoutError(ad, sure)), sure) : undefined;
      const iptal = () => bitir(new RequestAbortedError(ad));
      options.signal?.addEventListener("abort", iptal, { once: true });
      const temizle = () => {
        if (zamanlayici !== undefined) clearTimeout(zamanlayici);
        options.signal?.removeEventListener("abort", iptal);
      };
      this.bekleyen.set(id, { cozumle, reddet, temizle });
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
    for (const { reddet, temizle } of this.bekleyen.values()) {
      temizle();
      reddet(hata);
    }
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
      beklenen.temizle();
      beklenen.cozumle(mesaj.veri ?? {});
    }
  }
}
