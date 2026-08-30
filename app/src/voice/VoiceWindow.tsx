import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { emitVoiceMessage } from "./bridge";
import { cuesEnabled, playCue } from "./cues";
import { VoiceMode, type VoiceState } from "./VoiceMode";
import { closeVoiceWindow } from "./windowBridge";

/**
 * Konuşma penceresinin kökü.
 *
 * Ayrı bir pencerede çizilir; ana uygulamanın kabuğunu YÜKLEMEZ. Böylece
 * pencere küçük, hafif ve tek amaçlı kalır.
 */
/** Yardımcının satır biçimi: `{"tur":"hazir|kismi|son|hata","metin":"..."}` */
interface TanimaSatiri {
  metin: string;
  tur: "hazir" | "kismi" | "son" | "hata";
}

export function VoiceWindow() {
  const [state, setState] = useState<VoiceState>("idle");
  const [transcript, setTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Tanıma satırları tek yerden karşılanır. Kısmi sonuç ekranda gösterilir ama
  // sohbete YAZILMAZ: yalnız kesinleşen söz mesaj olur, yoksa yarım cümleler
  // sohbeti kirletir.
  useEffect(() => {
    const cikar = listen<string>("ses://tanima", (event) => {
      let satir: TanimaSatiri;
      try {
        satir = JSON.parse(event.payload) as TanimaSatiri;
      } catch {
        return;
      }
      if (satir.tur === "hata") {
        setError(satir.metin);
        setState("idle");
        return;
      }
      if (satir.tur === "hazir") {
        setError(null);
        return;
      }
      setTranscript(satir.metin);
      if (satir.tur === "son") {
        void emitVoiceMessage({ kaynak: "kullanici", metin: satir.metin });
        setState("thinking");
        if (cuesEnabled()) playCue("thinking");
      }
    });
    return () => void cikar.then((f) => f()).catch(() => undefined);
  }, []);

  // Pencere çerçevesiz açılır; gövde zemini panelin dışında görünmemeli.
  useEffect(() => {
    document.body.style.background = "transparent";
    document.body.style.overflow = "hidden";
  }, []);

  return (
    <VoiceMode
      onClose={() => void closeVoiceWindow()}
      onToggleListen={() => {
        const next = state === "listening" ? "idle" : "listening";
        if (cuesEnabled()) playCue(next === "listening" ? "listen-start" : "listen-stop");
        setState(next);
        if (next === "listening") {
          setTranscript("");
          setError(null);
          void invoke("tanima_baslat").catch((reason) => {
            // Sessizce susmak yanlış olurdu: kullanıcı neden dinlenmediğini görmeli.
            setError(String(reason));
            setState("idle");
          });
        }
      }}
      state={state}
      transcript={error ?? transcript}
    />
  );
}
