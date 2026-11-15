/**
 * Ekrana ve sohbet kaydına giden dış metindeki sırları maskeler.
 *
 * Tek kaynak: kabuk komutu/çıktısı (`olayMetni`) ve kurulum ekranı (`Onboarding`)
 * aynı örüntüleri kullanır. Bu bir savunma katmanıdır, kasa değildir: bilinen anahtar
 * önekleri ve `anahtar=değer` / `Authorization:` kalıpları yakalanır.
 */
const SIR_ORUNTULERI: RegExp[] = [
  /\bsk-(?:ant-)?[A-Za-z0-9_-]{12,}\b/g,
  /\bgh[oprsu]_[A-Za-z0-9]{20,}\b/g,
  /\bgithub_pat_[A-Za-z0-9_]{20,}\b/g,
  /\bAIza[A-Za-z0-9_-]{20,}\b/g,
  /\bAKIA[A-Z0-9]{16}\b/g,
  /\bxox[abprs]-[A-Za-z0-9-]{10,}\b/g,
  // Ücretsiz/üçüncü taraf sağlayıcı anahtarları.
  /\b(?:gsk|csk|xai)[_-][A-Za-z0-9]{16,}\b/g,
  /\bhf_[A-Za-z0-9]{20,}\b/g,
  /\bnvapi-[A-Za-z0-9_-]{16,}\b/g,
  // JWT: üç base64url parça, ilki `eyJ` ile başlar.
  /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g,
  // `Authorization: Bearer x`, `-H "Authorization: …"` ve çıplak `Bearer x`.
  /\bAuthorization\s*[:=]\s*[^\r\n"']+/gi,
  /\bBearer\s+[A-Za-z0-9._~+/=-]{8,}/g,
  /\b(?:api[_-]?key|token|secret|password|passwd|anahtar|parola|şifre)\s*[:=]\s*[^\s,;"']+/gi,
];

export const SIR_MASKESI = "[gizlendi]";

export function sirlariMaskele(deger: string): string {
  return SIR_ORUNTULERI.reduce((guvenli, oruntu) => guvenli.replace(oruntu, SIR_MASKESI), deger);
}
