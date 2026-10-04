/** Kits servis adresinden iframe adresini üretir.
 *
 * Adres yalnız yerel döngüdeki HTTP servisi olabilir; token, kullanıcı adı ya da
 * sorgu taşımaz (Kits kendi owner token'ını kendi origin'inde tutar). */
export type KitsTheme = "dark" | "light";

/** Kits iframe'ine tema değişikliğini bildiren mesajın türü (Kits `host-theme.ts`). */
export const KITS_THEME_MESSAGE = "fusion-kits-theme";

export function kitsFrameUrl(serviceUrl: string, theme: KitsTheme = "light"): string {
  const url = new URL(serviceUrl);
  const loopback = ["127.0.0.1", "localhost", "[::1]"].includes(url.hostname);
  if (url.protocol !== "http:" || !loopback) throw new Error("Kits adresi yerel bir HTTP adresi olmalı.");
  if (url.username || url.password || url.search || url.hash) {
    throw new Error("Kits adresinde kimlik bilgisi, sorgu ya da parça olmamalı.");
  }
  url.searchParams.set("surface", "kits");
  url.searchParams.set("theme", theme);
  return url.toString();
}
