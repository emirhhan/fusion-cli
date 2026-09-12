import type { ThemePreference } from "../../theme/theme";
import { setShowSteps } from "../preferences";
import { useShowSteps } from "../useShowSteps";

/**
 * Genel — kullanıcının günlük tercihleri.
 *
 * Burada yalnız TERCİH durur; sistem durumu ("şu kadar bağlantı var") değil.
 * Eskiden ikisi aynı kartlarda karışıyordu ve kullanıcı değiştirebileceği şeyle
 * yalnız okuyabileceği şeyi ayırt edemiyordu.
 */

/** Kenar çubuğundaki geçmiş bölümünün açık başlayıp başlamayacağı. */
export const HISTORY_KEY = "fusion.sidebar.history-open.v1";

export function readHistoryOpen(): boolean {
  try {
    return localStorage.getItem(HISTORY_KEY) !== "false";
  } catch {
    // Özel pencerede depo erişilemez olabilir; varsayılan açıktır.
    return true;
  }
}

export function General({
  historyOpen,
  onHistoryChange,
  onThemeChange,
  themePreference,
}: {
  historyOpen: boolean;
  onHistoryChange: (open: boolean) => void;
  onThemeChange: (preference: ThemePreference) => void;
  themePreference: ThemePreference;
}) {
  const showSteps = useShowSteps();
  return (
    <>
      <article className="settings__card">
        <h3>Görünüm</h3>
        <label className="settings__row" htmlFor="settings-theme">
          <span>Tema</span>
          <select
            id="settings-theme"
            onChange={(event) => onThemeChange(event.target.value as ThemePreference)}
            value={themePreference}
          >
            <option value="system">Sistemi izle</option>
            <option value="light">Açık</option>
            <option value="dark">Koyu</option>
          </select>
        </label>
        <label className="settings__row" htmlFor="settings-language">
          <span>Dil</span>
          <select disabled id="settings-language" value="tr">
            <option value="tr">Türkçe</option>
          </select>
        </label>
        <p className="settings__hint">
          Fusion şimdilik yalnız Türkçe. Diğer diller sonraki sürümlerde eklenecek.
        </p>
      </article>

      <article className="settings__card">
        <h3>Arayüz</h3>
        <label className="settings__row settings__row--check">
          <input
            checked={historyOpen}
            id="settings-history"
            onChange={(event) => onHistoryChange(event.target.checked)}
            type="checkbox"
          />
          <span>Geçmiş bölümünü açık başlat</span>
        </label>
        {/* Varsayılan KAPALI: adım dökümü teşhis içindir, günlük kullanımda her
            cevabın üstünü dolduruyordu. */}
        <label className="settings__row settings__row--check">
          <input
            checked={showSteps}
            id="settings-steps"
            onChange={(event) => setShowSteps(event.target.checked)}
            type="checkbox"
          />
          <span>Fusion'ın attığı adımları göster</span>
        </label>
      </article>
    </>
  );
}
