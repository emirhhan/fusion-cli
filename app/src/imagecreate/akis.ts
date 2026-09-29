/**
 * Görsel iş akışının saf modeli — düğümler, bağlantılar, doğrulama, çalışma sırası.
 *
 * Flora benzeri tuval: girdi (metin/görsel) → işlem (üret, varyasyon, büyüt,
 * düzenle) → çıktı. Model arayüzden bağımsızdır; tuval bunu çizer, çalıştırıcı
 * `calismaSirasi` ile işlem düğümlerini sırayla çekirdeğe gönderir.
 */

export type DugumTuru = "metin" | "gorsel" | "uret" | "varyasyon" | "buyut" | "duzenle" | "cikti";

export type Islem = "uret" | "varyasyon" | "buyut" | "duzenle";

export type DugumDurumu = "bos" | "calisiyor" | "bitti" | "hata";

export interface Dugum {
  id: string;
  tur: DugumTuru;
  x: number;
  y: number;
  /** Metin düğümünün istemi ya da işlem düğümünün ek talimatı. */
  istem?: string;
  /** Görsel girdi düğümünün ya da çalışmış işlemin ürettiği görselin yolu. */
  yol?: string;
  /** İşlem düğümünün seçili sağlayıcısı. */
  saglayici?: string;
  /** İşlem düğümünün kaç varyasyon üreteceği (1..MAX_ADET). */
  adet?: number;
  /** İşlemin ürettiği tüm görseller; `yol` bunlardan seçilen ve sonraki düğüme akandır. */
  sonuclar?: string[];
  durum?: DugumDurumu;
  hata?: string;
}

export interface Baglanti {
  kaynak: string;
  hedef: string;
}

export interface Akis {
  id?: string;
  ad: string;
  dugumler: Dugum[];
  baglantilar: Baglanti[];
}

/** Bir işlem düğümünün tek çalıştırmada üretebileceği en fazla varyasyon.
 *  Web oturumu her görseli ayrı sohbette üretir (15-60 sn); dört, bekleme
 *  süresini dakikalar mertebesinde tutan üst sınırdır. */
export const MAX_ADET = 4;

export const ISLEM_TURLERI: readonly Islem[] = ["uret", "varyasyon", "buyut", "duzenle"];

export const DUGUM_ETIKETI: Record<DugumTuru, string> = {
  metin: "Metin",
  gorsel: "Görsel",
  uret: "Üret",
  varyasyon: "Varyasyon",
  buyut: "Büyüt",
  duzenle: "Düzenle",
  cikti: "Çıktı",
};

/** Her düğüm türünün hangi girdileri kabul ettiği ve hangilerinin zorunlu olduğu. */
const GIRDI_KURALI: Record<DugumTuru, { metin: "yok" | "istege" | "zorunlu"; gorsel: "yok" | "istege" | "zorunlu" }> = {
  metin: { metin: "yok", gorsel: "yok" },
  gorsel: { metin: "yok", gorsel: "yok" },
  uret: { metin: "zorunlu", gorsel: "istege" },
  varyasyon: { metin: "istege", gorsel: "zorunlu" },
  buyut: { metin: "yok", gorsel: "zorunlu" },
  duzenle: { metin: "zorunlu", gorsel: "zorunlu" },
  cikti: { metin: "yok", gorsel: "zorunlu" },
};

/** Düğüm hangi tür çıktı verir? Çıktı düğümü zincirin sonudur. */
export function ciktiTuru(tur: DugumTuru): "metin" | "gorsel" | null {
  if (tur === "metin") return "metin";
  if (tur === "cikti") return null;
  return "gorsel";
}

export function islemMi(tur: DugumTuru): tur is Islem {
  return (ISLEM_TURLERI as readonly string[]).includes(tur);
}

/** Bağlantı kurulabilir mi? Hedef bu tür girdiyi kabul etmeli ve aynı türden ikinci girdi olmamalı. */
export function baglanabilir(akis: Akis, kaynakId: string, hedefId: string): boolean {
  if (kaynakId === hedefId) return false;
  const kaynak = akis.dugumler.find((dugum) => dugum.id === kaynakId);
  const hedef = akis.dugumler.find((dugum) => dugum.id === hedefId);
  if (!kaynak || !hedef) return false;
  const tur = ciktiTuru(kaynak.tur);
  if (!tur || GIRDI_KURALI[hedef.tur][tur] === "yok") return false;
  const ayniTurGirdi = akis.baglantilar.some((baglanti) => {
    if (baglanti.hedef !== hedefId) return false;
    const mevcut = akis.dugumler.find((dugum) => dugum.id === baglanti.kaynak);
    return mevcut !== undefined && ciktiTuru(mevcut.tur) === tur;
  });
  if (ayniTurGirdi) return false;
  // Döngü oluşturacak bağlantı reddedilir: hedeften kaynağa yol varsa kapanır.
  return !ulasilabilir(akis.baglantilar, hedefId, kaynakId);
}

function ulasilabilir(baglantilar: Baglanti[], baslangic: string, aranan: string): boolean {
  const ziyaret = new Set<string>();
  const yigin = [baslangic];
  while (yigin.length) {
    const simdiki = yigin.pop() as string;
    if (simdiki === aranan) return true;
    if (ziyaret.has(simdiki)) continue;
    ziyaret.add(simdiki);
    for (const baglanti of baglantilar) if (baglanti.kaynak === simdiki) yigin.push(baglanti.hedef);
  }
  return false;
}

/** Düğümün bağlı girdileri: metin girdisi ve görsel girdisinin kaynak düğümü. */
export function girdiler(akis: Akis, dugumId: string): { metin?: Dugum; gorsel?: Dugum } {
  const sonuc: { metin?: Dugum; gorsel?: Dugum } = {};
  for (const baglanti of akis.baglantilar) {
    if (baglanti.hedef !== dugumId) continue;
    const kaynak = akis.dugumler.find((dugum) => dugum.id === baglanti.kaynak);
    const tur = kaynak ? ciktiTuru(kaynak.tur) : null;
    if (kaynak && tur) sonuc[tur] = kaynak;
  }
  return sonuc;
}

/** Akışı çalıştırmadan önce bulunan sorunlar; boş dizi çalıştırılabilir demektir. */
export function akisSorunlari(akis: Akis): string[] {
  const sorunlar: string[] = [];
  const islemler = akis.dugumler.filter((dugum) => islemMi(dugum.tur));
  if (!islemler.length) sorunlar.push("Akışta en az bir işlem düğümü (Üret, Varyasyon, Büyüt, Düzenle) olmalı.");
  for (const dugum of akis.dugumler) {
    const kural = GIRDI_KURALI[dugum.tur];
    const bagli = girdiler(akis, dugum.id);
    const ad = DUGUM_ETIKETI[dugum.tur];
    if (kural.metin === "zorunlu" && !bagli.metin) sorunlar.push(`${ad} düğümüne bir Metin bağla.`);
    if (kural.gorsel === "zorunlu" && !bagli.gorsel) sorunlar.push(`${ad} düğümüne bir görsel girdisi bağla.`);
    if (dugum.tur === "metin" && !dugum.istem?.trim()) sorunlar.push("Metin düğümü boş.");
    if (dugum.tur === "gorsel" && !dugum.yol) sorunlar.push("Görsel düğümüne bir görsel seç.");
    if (islemMi(dugum.tur) && !dugum.saglayici) sorunlar.push(`${ad} düğümü için sağlayıcı seç.`);
  }
  return [...new Set(sorunlar)];
}

/** İşlem düğümlerinin bağımlılık sırası (Kahn algoritması). */
export function calismaSirasi(akis: Akis): Dugum[] {
  const giris = new Map(akis.dugumler.map((dugum) => [dugum.id, 0]));
  for (const baglanti of akis.baglantilar) giris.set(baglanti.hedef, (giris.get(baglanti.hedef) ?? 0) + 1);
  const kuyruk = akis.dugumler.filter((dugum) => (giris.get(dugum.id) ?? 0) === 0);
  const sira: Dugum[] = [];
  while (kuyruk.length) {
    const dugum = kuyruk.shift() as Dugum;
    sira.push(dugum);
    for (const baglanti of akis.baglantilar) {
      if (baglanti.kaynak !== dugum.id) continue;
      const kalan = (giris.get(baglanti.hedef) ?? 0) - 1;
      giris.set(baglanti.hedef, kalan);
      if (kalan === 0) {
        const hedef = akis.dugumler.find((item) => item.id === baglanti.hedef);
        if (hedef) kuyruk.push(hedef);
      }
    }
  }
  return sira.filter((dugum) => islemMi(dugum.tur));
}

/** Tek düğümü değiştirilmiş YENİ akış döndürür; girdi akış değişmez. */
export function dugumGuncelle(akis: Akis, id: string, degisim: Partial<Dugum>): Akis {
  return { ...akis, dugumler: akis.dugumler.map((dugum) => (dugum.id === id ? { ...dugum, ...degisim } : dugum)) };
}

/** Düğümü ve ona bağlı bağlantıları kaldırılmış YENİ akış. */
export function dugumSil(akis: Akis, id: string): Akis {
  return {
    ...akis,
    dugumler: akis.dugumler.filter((dugum) => dugum.id !== id),
    baglantilar: akis.baglantilar.filter((baglanti) => baglanti.kaynak !== id && baglanti.hedef !== id),
  };
}

/** Kaydetmeye uygun biçim: çalışma durumu ve hata metni kalıcı değildir. */
export function kaydedilebilir(akis: Akis): Akis {
  return {
    ...akis,
    dugumler: akis.dugumler.map(({ durum: _durum, hata: _hata, ...dugum }) => dugum),
  };
}

/** Yeni sayfada hazır gelen başlangıç akışı: Metin → Üret → Çıktı. */
export function baslangicAkisi(saglayici = ""): Akis {
  return {
    ad: "Yeni akış",
    dugumler: [
      { id: "metin-1", tur: "metin", x: 40, y: 80, istem: "" },
      { id: "uret-1", tur: "uret", x: 320, y: 80, saglayici },
      { id: "cikti-1", tur: "cikti", x: 600, y: 80 },
    ],
    baglantilar: [
      { kaynak: "metin-1", hedef: "uret-1" },
      { kaynak: "uret-1", hedef: "cikti-1" },
    ],
  };
}
