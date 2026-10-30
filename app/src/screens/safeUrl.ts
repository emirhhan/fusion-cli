/**
 * Araç/web çıktısından ya da ajandan gelen adresin dış dünyaya açılmasına izin verilip
 * verilmediği. Yalnız `http:` ve `https:` — `javascript:`, `file:`, `data:` ve kimlik
 * bilgili/şemasız dizgiler reddedilir (U1-38, U1-39).
 */
export function httpAdresiMi(adres: string | undefined | null): adres is string {
  if (!adres) return false;
  try {
    const ayrisan = new URL(adres);
    return ayrisan.protocol === "http:" || ayrisan.protocol === "https:";
  } catch {
    return false;
  }
}
