import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { VoiceWindow } from "./voice/VoiceWindow";
import { isVoiceWindow } from "./voice/windowBridge";
import "./theme/tokens.css";
import "./brand/brand.css";
import "./App.css";
import { applyTheme, readThemePreference } from "./theme/theme";

applyTheme(readThemePreference());
const nativeMainWindow = "__TAURI_INTERNALS__" in window && !isVoiceWindow();
if (nativeMainWindow) document.documentElement.dataset.fusionNativeMain = "true";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    {nativeMainWindow && <div aria-hidden="true" className="fusion-native-titlebar" data-tauri-drag-region />}
    {isVoiceWindow() ? <VoiceWindow /> : <App />}
  </React.StrictMode>,
);
