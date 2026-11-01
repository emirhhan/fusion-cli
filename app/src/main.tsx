import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { VoiceWindow } from "./voice/VoiceWindow";
import { isVoiceWindow } from "./voice/windowBridge";
import { SessionWindow } from "./windowing/SessionWindow";
import { sessionWindowId } from "./windowing/sessionWindowBridge";
import { isMacOS } from "./platform/os";
import "./theme/tokens.css";
import "./theme/accessibility.css";
import "./brand/brand.css";
import "./App.css";
import { applyTheme, readThemePreference } from "./theme/theme";
import { applyAccessibility, readAccessibilityPreferences } from "./theme/accessibility";
import { applyLanguage, readLanguage } from "./i18n/language";
import { RenderErrorBoundary } from "./ui/RenderErrorBoundary";

applyTheme(readThemePreference());
// Yazı ölçeği/kontrast/hareket ve dil ilk boyamadan ÖNCE uygulanır; sonradan sıçrama olmaz (P-065).
applyAccessibility(readAccessibilityPreferences());
applyLanguage(readLanguage());
// Sohbet penceresi (#443) sistem başlık çubuğuyla açılır; ana pencerenin başlık payı ona uygulanmaz.
const sessionWindow = sessionWindowId();
const nativeMainWindow = "__TAURI_INTERNALS__" in window && !isVoiceWindow() && sessionWindow === null;
if (nativeMainWindow) document.documentElement.dataset.fusionNativeMain = "true";
/* macOS'ta pencere `titleBarStyle: "Overlay"` + `hiddenTitle: true` ile açılır:
   trafik ışıkları içeriğin ÜSTÜNE biner, ayrı bir sistem başlık şeridi yoktur.
   Bu yüzden boşluk AYRI bir dolgu şeridiyle değil, kenar çubuğu ve üst çubuğun
   kendi içinde ayrılan bir payla karşılanır (bkz. tokens.css `--titlebar-inset`).
   Windows'ta pencere kendi sistem başlık çubuğunu zaten çizer; orada ekstra
   pay AYRILMAZ, aksi halde çift boşluk oluşur. */
if (nativeMainWindow && isMacOS()) document.documentElement.dataset.fusionTitlebarInset = "true";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <RenderErrorBoundary>
      {isVoiceWindow() ? <VoiceWindow /> : sessionWindow ? <SessionWindow id={sessionWindow} /> : <App />}
    </RenderErrorBoundary>
  </React.StrictMode>,
);
