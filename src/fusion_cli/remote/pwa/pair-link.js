// Terminal QR'ındaki eşleştirme bağlantısı: `https://<tünel>/?kod=ABCD2345`.
// Ölçüldü (31 Ekim): PWA kodu yalnız elle alıyordu; QR'dan gelen kod okunmuyor, kullanıcı yazıyordu.
const PAIRING_CODE_PATTERN = /^[A-Z2-9]{8}$/; // sunucu alfabesi (0/1/I/O yok), 8 karakter
export const PAIRING_CODE_PARAM = "kod";

/** `?kod=` değerini büyük harfe çevirip doğrular; yoksa ya da bozuksa boş metin. */
export function pairingCodeFromSearch(search) {
  const raw = new URLSearchParams(search || "").get(PAIRING_CODE_PARAM) || "";
  const code = raw.trim().toUpperCase();
  return PAIRING_CODE_PATTERN.test(code) ? code : "";
}

/** Kod adreste kalmasın (geçmiş, paylaşım, ekran görüntüsü): parametre düşürülmüş adres. */
export function stripPairingCode(href) {
  const url = new URL(href);
  url.searchParams.delete(PAIRING_CODE_PARAM);
  return url.toString();
}
