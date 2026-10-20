import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { VoiceWindow } from "./voice/VoiceWindow";
import { isVoiceWindow } from "./voice/windowBridge";
import { isMacOS } from "./platform/os";
import "./theme/tokens.css";
import "./brand/brand.css";
import "./App.css";
import { applyTheme, readThemePreference } from "./theme/theme";

applyTheme(readThemePreference());
const nativeMainWindow = "__TAURI_INTERNALS__" in window && !isVoiceWindow();
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
    {isVoiceWindow() ? <VoiceWindow /> : <App />}
  </React.StrictMode>,
);
