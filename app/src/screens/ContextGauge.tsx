import type { BaglamOlcusu } from "../protocol/types";
import "./ContextGauge.css";

/**
 * Bu doluluktan sonra gösterge uyarı rengine geçer ve kalan payı yazar.
 *
 * Gerekçe: web oturumunun özetleme eşiği 24.000 karakter; tek bir dosya okuması ya da
 * uzun bir cevap 5–7 bin karakter (≈%25–30) ekleyebiliyor. %70'te kullanıcının
 * bir-iki turluk payı kalır — konuyu bölmeye ya da yeni sohbet açmaya karar
 * verebileceği son rahat an.
 */
export const BAGLAM_UYARI_ESIGI = 70;

/**
 * Bu doluluktan sonra "yakında özetlenecek" ipucu çıkar.
 *
 * Gerekçe: çekirdek geçmişi tur SONUNDA, eşik aşıldıysa özetler
 * (`loop._maybe_compress`). %90'da sıradaki sıradan bir tur bile eşiği aşar;
 * yani bir sonraki cevaptan sonra eski mesajlar büyük olasılıkla özetlenecek.
 */
export const BAGLAM_KRITIK_ESIGI = 90;

/** Halkanın çevresi (r = 6): dolu yay bu uzunluğun doluluk kadarıdır. */
const HALKA_YARICAP = 6;
const HALKA_CEVRE = 2 * Math.PI * HALKA_YARICAP;

export type BaglamSeviyesi = "normal" | "uyari" | "kritik";

/** Doluluğun hangi görsel seviyeye düştüğü. Saf; eşikler tek yerde. */
export function baglamSeviyesi(yuzde: number): BaglamSeviyesi {
  if (yuzde >= BAGLAM_KRITIK_ESIGI) return "kritik";
  if (yuzde >= BAGLAM_UYARI_ESIGI) return "uyari";
  return "normal";
}

/** Görünür kısa metin. Normal seviyede metin yok; yalnız halka çizilir. */
export function baglamEtiketi(yuzde: number): string | null {
  const seviye = baglamSeviyesi(yuzde);
  if (seviye === "kritik") return "Yakında özetlenecek";
  if (seviye === "uyari") return `Özetlemeye %${100 - yuzde} kaldı`;
  return null;
}

/**
 * Kalan bağlam göstergesi — mesaj kutusunun yanında, Claude'daki gibi sade.
 *
 * Neden var — ölçüldü (17 Eylül denetimi): uzun bir turda geçmiş 91 mesajdan
 * 13'e özetlendi ve kullanıcı bunu ancak modelin unutmasından anladı.
 * Ölçü yoksa (eski çekirdek, henüz okunmadı) hiçbir şey çizilmez: yanlış bir
 * "%0" göstermek, göstermemekten kötüdür.
 */
export function ContextGauge({ olcu }: { olcu: BaglamOlcusu | null }) {
  if (!olcu) return null;
  const yuzde = Math.round(olcu.yuzde);
  const seviye = baglamSeviyesi(yuzde);
  const etiket = baglamEtiketi(yuzde);
  const pencere = olcu.model_siniri_token
    ? `${olcu.model ?? "Seçili model"} girdi penceresi: ${olcu.model_siniri_token.toLocaleString("tr-TR")} token.`
    : "Modelin token penceresi doğrulanamadı.";
  const sonGirdi = olcu.son_girdi_token != null
    ? `Son başarılı ajan çağrısı: ${olcu.son_girdi_token.toLocaleString("tr-TR")} girdi tokenı (${olcu.son_girdi_model ?? "model bilinmiyor"}).`
    : "Son ajan çağrısının gerçek token ölçümü henüz yok.";
  const aciklama = `Geçmişin özetleme eşiğine doluluğu: %${yuzde} (${olcu.kullanilan.toLocaleString("tr-TR")}/${olcu.sinir.toLocaleString("tr-TR")} karakter). ${pencere} ${sonGirdi} Bu yüzde model penceresinin doluluğu değildir.`;
  return (
    <span
      aria-label={aciklama}
      aria-valuemax={100}
      aria-valuemin={0}
      aria-valuenow={yuzde}
      className="context-gauge"
      data-seviye={seviye}
      role="meter"
      title={aciklama}
    >
      <svg aria-hidden="true" className="context-gauge__ring" height="16" viewBox="0 0 16 16" width="16">
        <circle className="context-gauge__track" cx="8" cy="8" r={HALKA_YARICAP} />
        <circle
          className="context-gauge__fill"
          cx="8"
          cy="8"
          r={HALKA_YARICAP}
          strokeDasharray={`${(HALKA_CEVRE * yuzde) / 100} ${HALKA_CEVRE}`}
        />
      </svg>
      {etiket && <span className="context-gauge__label">{etiket}</span>}
    </span>
  );
}
