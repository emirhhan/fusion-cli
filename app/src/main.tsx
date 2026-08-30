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

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    {isVoiceWindow() ? <VoiceWindow /> : <App />}
  </React.StrictMode>,
);
