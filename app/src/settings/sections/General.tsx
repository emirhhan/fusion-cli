import type { ThemePreference } from "../../theme/theme";
import { setShowSteps } from "../preferences";
import { useShowSteps } from "../useShowSteps";
import { setPlacement, type InspectorPlacement } from "../placement";
import { useInspectorPlacement } from "../useInspectorPlacement";
import { LANGUAGE_NAMES, LANGUAGES, setLanguage } from "../../i18n/language";
import { useLanguage } from "../../i18n/useLanguage";
import {
  FONT_SCALE_FACTORS,
  setAccessibilityPreference,
  type AccentPreference,
  type FontScale,
  type MotionPreference,
} from "../../theme/accessibility";
import { useAccessibility } from "../../theme/useAccessibility";
import { setTrayEnabled, useTrayEnabled } from "../../windowing/tray";

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

const VURGULAR: AccentPreference[] = ["brand", "blue", "violet", "mint"];
const HAREKETLER: MotionPreference[] = ["system", "reduce", "allow"];

export function General({
  historyOpen,
  onHistoryChange,
  onReopenSetup,
  onThemeChange,
  themePreference,
}: {
  historyOpen: boolean;
  onHistoryChange: (open: boolean) => void;
  /** Kurulum sihirbazını baştan açar ("Şimdilik atla"dan dönüş yolu, U5-47). */
  onReopenSetup?: () => void;
  onThemeChange: (preference: ThemePreference) => void;
  themePreference: ThemePreference;
}) {
  const showSteps = useShowSteps();
  const placement = useInspectorPlacement();
  const { language, t } = useLanguage();
  const erisilebilirlik = useAccessibility();
  const trayEnabled = useTrayEnabled();
  return (
    <>
      {/* Çevrilen kartlar kendi dilini taşır; belge dili çeviri tamamlanana dek "tr" (bkz. i18n/language.ts). */}
      <article className="settings__card" lang={language}>
        <h3>{t("gorunum.baslik")}</h3>
        <label className="settings__row" htmlFor="settings-theme">
          <span>{t("gorunum.tema")}</span>
          <select
            id="settings-theme"
            onChange={(event) => onThemeChange(event.target.value as ThemePreference)}
            value={themePreference}
          >
            <option value="system">{t("gorunum.tema.sistem")}</option>
            <option value="light">{t("gorunum.tema.acik")}</option>
            <option value="dark">{t("gorunum.tema.koyu")}</option>
          </select>
        </label>
        {/* Dil bir açılır liste DEĞİL, iki seçenekli bir radyo grubu: seçili dil onay
            işaretiyle görünür ve tıklandığı anda uygulanıp kaydedilir. */}
        <div className="settings__row">
          <span id="settings-language-label">{t("gorunum.dil")}</span>
          <div aria-labelledby="settings-language-label" className="settings__segmented" id="settings-language" role="radiogroup" tabIndex={-1}>
            {LANGUAGES.map((secenek) => (
              <label className="settings__segment-option" data-selected={language === secenek} key={secenek} lang={secenek}>
                <input
                  checked={language === secenek}
                  name="settings-language"
                  onChange={() => setLanguage(secenek)}
                  type="radio"
                  value={secenek}
                />
                <span aria-hidden="true" className="settings__segment-check">{language === secenek ? "✓" : ""}</span>
                <span>{LANGUAGE_NAMES[secenek]}</span>
              </label>
            ))}
          </div>
        </div>
        <p className="settings__hint">{t("gorunum.dil.ipucu")}</p>
      </article>

      {/* Erişilebilirlik (P-065): yazı ölçeği, vurgu, hareket, kontrast. Hepsi belge
          kökünde data-* olarak uygulanır; varsayılan değer öznitelik bırakmaz. */}
      <article className="settings__card" id="settings-accessibility" lang={language}>
        <h3>{t("erisilebilirlik.baslik")}</h3>
        <label className="settings__row" htmlFor="settings-font-scale">
          <span>{t("erisilebilirlik.yazi")}</span>
          <select
            id="settings-font-scale"
            onChange={(event) => setAccessibilityPreference("fontScale", event.target.value as FontScale)}
            value={erisilebilirlik.fontScale}
          >
            {(Object.keys(FONT_SCALE_FACTORS) as FontScale[]).map((olcek) => (
              <option key={olcek} value={olcek}>{t(`erisilebilirlik.yazi.${olcek}`)}</option>
            ))}
          </select>
        </label>
        <label className="settings__row" htmlFor="settings-accent">
          <span>{t("erisilebilirlik.vurgu")}</span>
          <select
            id="settings-accent"
            onChange={(event) => setAccessibilityPreference("accent", event.target.value as AccentPreference)}
            value={erisilebilirlik.accent}
          >
            {VURGULAR.map((vurgu) => (
              <option key={vurgu} value={vurgu}>{t(`erisilebilirlik.vurgu.${vurgu}`)}</option>
            ))}
          </select>
        </label>
        <label className="settings__row" htmlFor="settings-motion">
          <span>{t("erisilebilirlik.hareket")}</span>
          <select
            id="settings-motion"
            onChange={(event) => setAccessibilityPreference("motion", event.target.value as MotionPreference)}
            value={erisilebilirlik.motion}
          >
            {HAREKETLER.map((hareket) => (
              <option key={hareket} value={hareket}>{t(`erisilebilirlik.hareket.${hareket}`)}</option>
            ))}
          </select>
        </label>
        <label className="settings__row settings__row--check">
          <input
            checked={erisilebilirlik.highContrast}
            id="settings-contrast"
            onChange={(event) => setAccessibilityPreference("highContrast", event.target.checked)}
            type="checkbox"
          />
          <span>{t("erisilebilirlik.kontrast")}</span>
        </label>
        <p className="settings__hint">{t("erisilebilirlik.ipucu")}</p>
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
        {/* Sistem tepsisi (P-064): menü çubuğunda hızlı "göster / yeni sohbet"; kapatılabilir. */}
        <label className="settings__row settings__row--check">
          <input
            checked={trayEnabled}
            id="settings-tray"
            onChange={(event) => setTrayEnabled(event.target.checked)}
            type="checkbox"
          />
          <span>Menü çubuğunda Fusion simgesi</span>
        </label>
        <label className="settings__row" htmlFor="settings-placement">
          <span>Çalışma paneli</span>
          <select
            id="settings-placement"
            onChange={(event) => setPlacement(event.target.value as InspectorPlacement)}
            value={placement}
          >
            <option value="right">Sağda</option>
            <option value="bottom">Altta (VS Code gibi)</option>
          </select>
        </label>
        <p className="settings__hint">
          Geniş bir terminal ya da uzun bir diff, alt yerleşimde daha rahat okunur.
        </p>
      </article>

      {onReopenSetup && (
        <article className="settings__card">
          <h3>Kurulum</h3>
          <p className="settings__hint">
            Karşılama sihirbazını atladıysan ya da sağlayıcı, geçmiş ve proje adımlarını yeniden görmek istiyorsan baştan aç.
            Sohbetlerin ve ayarların değişmez.
          </p>
          <button onClick={onReopenSetup} type="button">Kurulumu yeniden aç</button>
        </article>
      )}
    </>
  );
}
