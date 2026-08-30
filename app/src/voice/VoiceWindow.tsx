import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import {
  answerVoiceAsk,
  emitVoiceMessage,
  onVoiceAsk,
  onVoicePrefsState,
  requestVoicePrefs,
  type VoiceAsk,
} from "./bridge";
import { cuesEnabled, playCue } from "./cues";
import { VoiceMode, type VoiceState } from "./VoiceMode";
import type { VoicePrefs } from "./VoiceSettings";
import { closeVoiceWindow, setVoiceWindowOnTop, setVoiceWindowWide } from "./windowBridge";
import { selectVoiceModel } from "../platform/dialog";

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
  const [wide, setWide] = useState(true);
  const [onTop, setOnTop] = useState(true);
  const [prefs, setPrefs] = useState<VoicePrefs>({ hiz: 1, model: null, robotik: 0.5 });
  const [ask, setAsk] = useState<VoiceAsk | null>(null);

  // Onay sorusu panelde görünür: konuşurken ana pencereye dönmek gerekmesin.
  useEffect(() => {
    const cikar = onVoiceAsk((gelen) => setAsk(gelen?.acik ? gelen : null));
    return () => void cikar.then((f) => f()).catch(() => undefined);
  }, []);

  // Dinleme KENDİLİĞİNDEN başlar: kullanıcı mikrofona basarak paneli zaten
  // açtı, bir kez daha basmasını istemek fazladan adımdı.
  useEffect(() => {
    setState("listening");
    if (cuesEnabled()) playCue("listen-start");
    void invoke("tanima_baslat").catch((reason) => {
      setError(String(reason));
      setState("idle");
    });
  }, []);

  // Geçerli tercihleri ana pencereden iste ve gelenleri izle.
  useEffect(() => {
    const cikar = onVoicePrefsState((gelen) => setPrefs(gelen));
    void requestVoicePrefs(null);
    return () => void cikar.then((f) => f()).catch(() => undefined);
  }, []);

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
      ask={ask}
      onAnswer={(cevap) => {
        setAsk(null);
        void answerVoiceAsk(cevap);
      }}
      onClose={() => void closeVoiceWindow()}
      onPickModel={() => {
        // Piper modelinin YOLU tercihlere yazılır, dosya kopyalanmaz: büyük bir
        // modeli çoğaltmak ve kullanıcının dizinine dokunmak gereksiz. Geçerlilik
        // (uzantı ve yanındaki yapılandırma) çekirdekte denetlenir.
        void selectVoiceModel()
          .then((yol) => {
            if (!yol) return;
            const next = { ...prefs, model: yol };
            setPrefs(next);
            return requestVoicePrefs(next);
          })
          .catch(() => undefined);
      }}
      onPrefsChange={(next) => {
        setPrefs(next);
        void requestVoicePrefs(next);
      }}
      onTop={onTop}
      onTopChange={(next) => {
        setOnTop(next);
        void setVoiceWindowOnTop(next).catch(() => undefined);
      }}
      onWideChange={(next) => {
        setWide(next);
        void setVoiceWindowWide(next).catch(() => undefined);
      }}
      prefs={prefs}
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
      wide={wide}
    />
  );
}
