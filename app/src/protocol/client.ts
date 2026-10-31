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
  // Önizleme paneli (P-041): yapılandırma okuma kısadır; başlatma `npm install`e kadar
  // bekleyebilir; günlük/ekran görüntüsü başsız tarayıcı açar (sayfa yüklenmesi 30 sn'e kadar).
  "onizleme.yapilandirmalar": OKUMA_SON_SURESI_MS,
  "onizleme.baslat": 360_000,
  "onizleme.durdur": OKUMA_SON_SURESI_MS,
  "onizleme.gunluk": 90_000,
  "onizleme.ekran_goruntusu": 90_000,
  "proje.degisiklikler": OKUMA_SON_SURESI_MS,
  // Sağlayıcı paneli (U5-01): cevapsız kalan çekirdek `busy`/`mesgul` durumunu sonsuza dek
  // kilitliyordu (tüm kartlar disabled). Giriş penceresinin KENDİSİ (kullanıcı Chrome'da
  // giriş yapar) bu istekle değil `web.giris_durumu` yoklamasıyla beklenir; bu istekler kısadır.
  // Ölçümü/doğrulaması gerçek model çağrısı yaptığından `web.dogrula` ve `web.arac_olc` daha uzundur.
  "saglayici.katalog": OKUMA_SON_SURESI_MS,
  "web.giris": 60_000,
  "web.giris_durumu": OKUMA_SON_SURESI_MS,
  "web.baglan": OKUMA_SON_SURESI_MS,
  "web.cikis": OKUMA_SON_SURESI_MS,
  "web.model_secenekleri": 60_000,
  "web.model_sec": 60_000,
  "web.dogrula": 120_000,
  "web.arac_olc": 300_000,
  "kontrol.anahtar_dogrula": 90_000,
  // Model seçici (U1-41): cevapsız çekirdek listeyi sonsuza dek "Modeller okunuyor…"da bırakıyordu.
  // Katalog sağlayıcı sağlığını da sorabildiği için okuma süresinin iki katı tanınır.
  "model.katalog": 60_000,
  "kontrol.durum": OKUMA_SON_SURESI_MS,
};

/** Dinleyicisiz istemcide biriken soru sayısı sınırı; aşan soru düşer (bellek koruması). */
const BEKLEYEN_SORU_SINIRI = 32;

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
  /** Dinleyici yokken gelen sorular; ilk `onQuestion` aboneliğinde sırayla teslim edilir. */
  private bekleyenSorular: { id: string; veri: Record<string, unknown> }[] = [];
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
      try {
        this.gonder(JSON.stringify(istek));
      } catch (hata) {
        // Taşıma kapalıysa kayıt asılı kalmasın: zamanlayıcı ve bekleyen girdisi temizlenir.
        bitir(hata instanceof Error ? hata : new Error(String(hata)));
      }
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
    // Dinleyiciden önce gelen sorular düşmez (U5-02): çekirdek cevap beklemeye devam eder.
    const birikmis = this.bekleyenSorular;
    this.bekleyenSorular = [];
    for (const { id, veri } of birikmis) this.dinleyiciyiCagir(f, id, veri);
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
    this.bekleyenSorular = [];
  }

  /** Tek dinleyicinin hatası kardeşlerini ve taşıma katmanını düşürmez (U5-03). */
  private dinleyiciyiCagir<A extends unknown[]>(f: (...args: A) => void, ...args: A): void {
    try {
      f(...args);
    } catch (hata) {
      console.error("Protokol dinleyicisi hata verdi:", hata);
    }
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
      const veri = mesaj.veri ?? {};
      for (const f of [...this.olayDinleyicileri]) this.dinleyiciyiCagir(f, veri);
      return;
    }
    // Çekirdek kimliği sayı olarak yazarsa da eşleşsin (U5-04); boş kimlik geçersizdir.
    const kimlik = mesaj.id === undefined || mesaj.id === null || mesaj.id === "" ? null : String(mesaj.id);
    if (mesaj.tip === "soru" && kimlik) {
      const veri = mesaj.veri ?? {};
      if (this.soruDinleyicileri.length === 0) {
        if (this.bekleyenSorular.length < BEKLEYEN_SORU_SINIRI) this.bekleyenSorular.push({ id: kimlik, veri });
        return;
      }
      for (const f of [...this.soruDinleyicileri]) this.dinleyiciyiCagir(f, kimlik, veri);
      return;
    }
    if (mesaj.tip === "sonuc" && kimlik) {
      const beklenen = this.bekleyen.get(kimlik);
      if (!beklenen) return; // Eşleşmeyen kimlik yok sayılır.
      this.bekleyen.delete(kimlik);
      beklenen.temizle();
      beklenen.cozumle(mesaj.veri ?? {});
    }
  }
}
