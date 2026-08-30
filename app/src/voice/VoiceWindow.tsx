import { useEffect, useState } from "react";
import { cuesEnabled, playCue } from "./cues";
import { VoiceMode, type VoiceState } from "./VoiceMode";
import { closeVoiceWindow } from "./windowBridge";

/**
 * Konuşma penceresinin kökü.
 *
 * Ayrı bir pencerede çizilir; ana uygulamanın kabuğunu YÜKLEMEZ. Böylece
 * pencere küçük, hafif ve tek amaçlı kalır.
 */
export function VoiceWindow() {
  const [state, setState] = useState<VoiceState>("idle");

  // Pencere çerçevesiz açılır; gövde zemini panelin dışında görünmemeli.
  useEffect(() => {
    document.body.style.background = "transparent";
    document.body.style.overflow = "hidden";
  }, []);

  return (
    <VoiceMode
      onClose={() => void closeVoiceWindow()}
      onToggleListen={() =>
        setState((current) => {
          const next = current === "listening" ? "idle" : "listening";
          if (cuesEnabled()) playCue(next === "listening" ? "listen-start" : "listen-stop");
          return next;
        })
      }
      state={state}
      transcript=""
    />
  );
}
