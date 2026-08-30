import { useEffect, useRef } from "react";
import { FusionAvatar, type AvatarState } from "./FusionAvatar";
import { MicIcon } from "./MicIcon";
import { VoiceSettings, type VoicePrefs } from "./VoiceSettings";
import { Waveform } from "./Waveform";
import "./VoiceMode.css";

/**
 * Konuşma kipi — ChatGPT'deki sesli sohbetin karşılığı.
 *
 * TAM EKRAN DEĞİLDİR: ortada küçük bir panel açılır, uygulama arkasında
 * durmaya devam eder ve kararır. Kullanıcı nerede olduğunu kaybetmez.
 *
 * Konuşulan her şey aynı sohbete mesaj olarak yazılır: panel kapandığında
 * kullanıcı yazışmış gibi tam dökümü görür. Ayrı bir "ses geçmişi" tutmak,
 * aynı konuşmayı iki yere bölmek olurdu.
 */

export type VoiceState = "idle" | "listening" | "thinking" | "talking";

const DURUM_METNI: Record<VoiceState, string> = {
  idle: "Konuşmak için dokun",
  listening: "Dinliyorum…",
  thinking: "Düşünüyorum…",
  talking: "Konuşuyorum",
};

const AVATAR: Record<VoiceState, AvatarState> = {
  idle: "idle",
  listening: "listening",
  thinking: "thinking",
  talking: "talking",
};

interface VoiceModeProps {
  /** Kipi kapat. Sohbet olduğu gibi kalır. */
  onClose: () => void;
  /** Ayar değişimi; verilmezse ayar bölümü hiç çizilmez. */
  onPrefsChange?: (next: VoicePrefs) => void;
  /** Kendi ses dosyasını seç. */
  onPickModel?: () => void;
  /** Dinlemeyi başlat/durdur. */
  onToggleListen: () => void;
  /** Hep üstte kalma tercihi. */
  onTop?: boolean;
  onTopChange?: (next: boolean) => void;
  prefs?: VoicePrefs;
  /** O anda duyulan/üretilen metin; boşsa gösterilmez. */
  transcript?: string;
  state: VoiceState;
  /** Geniş kip: döküm ve ayarlar görünür. Dar kip yalnız karakter ve mikrofon. */
  wide?: boolean;
  onWideChange?: (next: boolean) => void;
}

const VARSAYILAN_TERCIH: VoicePrefs = { hiz: 1, model: null, robotik: 0.5 };

export function VoiceMode({
  onClose,
  onPickModel,
  onPrefsChange,
  onToggleListen,
  onTop = true,
  onTopChange,
  onWideChange,
  prefs = VARSAYILAN_TERCIH,
  state,
  transcript,
  wide = true,
}: VoiceModeProps) {
  const closeRef = useRef<HTMLButtonElement>(null);

  // Escape kipi kapatır: tam ekran bir yüzeyden çıkışın klavye yolu olmalı.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    closeRef.current?.focus();
  }, []);

  return (
    <div className="voice-backdrop" onClick={onClose} role="presentation">
      <section
        aria-label="Konuşma kipi"
        aria-modal="true"
        className="voice-panel"
        data-state={state}
        data-wide={wide}
        onClick={(event) => event.stopPropagation()}
        role="dialog"
      >
        <header className="voice-panel__head">
          <span className="voice-panel__title">Fusion ile konuş</span>
          {onWideChange && (
            <button
              aria-label={wide ? "Paneli küçült" : "Paneli büyüt"}
              aria-pressed={wide}
              className="voice-panel__size"
              onClick={() => onWideChange(!wide)}
              type="button"
            >
              {wide ? "⤡" : "⤢"}
            </button>
          )}
          <button
            aria-label="Konuşma kipini kapat"
            className="voice-panel__close"
            onClick={onClose}
            ref={closeRef}
            type="button"
          >
            ✕
          </button>
        </header>

        <div className="voice-panel__stage">
          <FusionAvatar scale={wide ? 2 : 1.2} state={AVATAR[state]} />
          <Waveform active={state === "listening"} />
          <p aria-live="polite" className="voice-panel__status">{DURUM_METNI[state]}</p>
          {wide && transcript && <p className="voice-panel__transcript">{transcript}</p>}
        </div>

        <footer className="voice-panel__foot">
          <button
            aria-label={state === "listening" ? "Dinlemeyi durdur" : "Konuşmaya başla"}
            aria-pressed={state === "listening"}
            className="voice-panel__mic"
            onClick={onToggleListen}
            type="button"
          >
            <MicIcon size={26} />
          </button>
          {wide && <p className="voice-panel__hint">Konuştukların sohbete yazılır.</p>}
          {wide && onPrefsChange && onTopChange && (
            <VoiceSettings
              onChange={onPrefsChange}
              onPickModel={onPickModel}
              onTop={onTop}
              onTopChange={onTopChange}
              prefs={prefs}
            />
          )}
        </footer>
      </section>
    </div>
  );
}
