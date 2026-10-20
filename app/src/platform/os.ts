/**
 * Pencere kabuğunun (Tauri) çalıştığı işletim sistemini algılar.
 *
 * `@tauri-apps/plugin-os` bağımlılığı eklemeden, tarayıcının kendi
 * `navigator` bilgisinden çıkarım yapılır: macOS başlık çubuğu (trafik
 * ışıkları) yalnızca macOS'ta anlamlıdır, Windows'ta pencere zaten kendi
 * sistem başlık çubuğunu çizer.
 */
export function isMacOS(): boolean {
  if (typeof navigator === "undefined") return false;
  const withUserAgentData = navigator as Navigator & { userAgentData?: { platform?: string } };
  const platform = withUserAgentData.userAgentData?.platform || navigator.platform || navigator.userAgent;
  return /mac/i.test(platform);
}
