/**
 * Web sağlayıcı işaretleri.
 *
 * Dört sağlayıcı da kullanıcının KENDİ aboneliğiyle çalışır; kontrol panelinde
 * ayırt edilebilir olmaları gerekir. İşaretler tek renkle (`currentColor`)
 * çizilir: her markanın kurumsal rengini taklit etmek yerine Fusion'ın kendi
 * yüzeyine uyarlar ve iki temada da okunur kalırlar.
 */
export type ProviderId = "chatgpt_web" | "claude_web" | "gemini_web" | "copilot_web";

const PATHS: Record<ProviderId, string> = {
  // OpenAI: iç içe geçmiş altıgen düğüm.
  chatgpt_web:
    "M12 2 20 6.6 20 15.4 12 20 4 15.4 4 6.6Z M12 6.2 16.4 8.7 16.4 13.7 12 16.2 7.6 13.7 7.6 8.7Z",
  // Anthropic: yükselen iki eğik kol.
  claude_web: "M7.6 19 12.6 4h2.9l5 15h-3l-1.1-3.4H11.6L10.5 19Zm4.8-6h3.2l-1.6-5Z",
  // Gemini: dört uçlu ışıma.
  gemini_web: "M12 2c.6 5.2 4.2 8.8 9.4 9.4-5.2.6-8.8 4.2-9.4 9.4-.6-5.2-4.2-8.8-9.4-9.4C7.8 10.8 11.4 7.2 12 2Z",
  // Copilot: kapalı halka ve merkez.
  copilot_web:
    "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 2.4a6.6 6.6 0 1 1 0 13.2 6.6 6.6 0 0 1 0-13.2Zm0 3.2a3.4 3.4 0 1 0 0 6.8 3.4 3.4 0 0 0 0-6.8Z",
};

export function ProviderLogo({ id, size = 20 }: { id: ProviderId; size?: number }) {
  return (
    <svg
      aria-hidden="true"
      className="provider-logo"
      fill="currentColor"
      height={size}
      viewBox="0 0 24 24"
      width={size}
      xmlns="http://www.w3.org/2000/svg"
    >
      <path d={PATHS[id]} fillRule="evenodd" />
    </svg>
  );
}
