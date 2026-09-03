/**
 * Yankı ayıklama — Fusion'ın kendi sesini kullanıcının sözü sanmamak.
 *
 * Mikrofon sürekli açık olduğu için Fusion hoparlörden konuşurken kendi sesini
 * duyar. macOS'un ses işleme motoru (VPIO) bunun büyük kısmını siler ama
 * mükemmel değildir: hoparlörün akustik kuyruğu fiziksel gecikme taşır ve
 * çıkarma yöntemi bunu tam yakalayamaz. Bu yüzden metin seviyesinde ikinci bir
 * savunma gerekir.
 *
 * Karar METİN üzerinden verilir, ses seviyesi üzerinden değil: seviye eşiği
 * yüksek sesle konuşan kullanıcıyı da susturur.
 */

/** Eşleşme sayılması için gereken en düşük ortak kelime oranı. */
const ESIK = 0.6;

/** Bu uzunluğun altındaki söz, tesadüfi eşleşme riski yüzünden ayıklanmaz. */
const EN_KISA_KELIME = 2;

/** Türkçe büyük/küçük farkını koruyarak sadeleştir. */
function sadelestir(metin: string): string {
  return metin
    .replace(/I/gu, "ı")
    .replace(/İ/gu, "i")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/gu, " ")
    .trim();
}

function kelimeler(metin: string): string[] {
  const sade = sadelestir(metin);
  return sade ? sade.split(" ") : [];
}

/**
 * `duyulan`, Fusion'ın seslendirdiği `konusulan` metnin yankısı mı?
 *
 * Yankı, seslendirilen metnin bir PARÇASIDIR: duyulan kelimelerin çoğu
 * konuşulanın içinde geçer. Kullanıcının araya girmesi ise genelde yeni
 * kelimeler taşır.
 */
export function yankiMi(duyulan: string, konusulan: string | null): boolean {
  if (!konusulan) return false;
  const duyulanKelimeler = kelimeler(duyulan);
  if (duyulanKelimeler.length < EN_KISA_KELIME) return false;
  const konusulanKume = new Set(kelimeler(konusulan));
  if (konusulanKume.size === 0) return false;
  const ortak = duyulanKelimeler.filter((kelime) => konusulanKume.has(kelime)).length;
  return ortak / duyulanKelimeler.length >= ESIK;
}
