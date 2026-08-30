import { useEffect, useRef } from "react";
import { FusionAvatar, type AvatarState } from "./FusionAvatar";
import { MicIcon } from "./MicIcon";
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
  /** Dinlemeyi başlat/durdur. */
  onToggleListen: () => void;
  /** O anda duyulan/üretilen metin; boşsa gösterilmez. */
  transcript?: string;
  state: VoiceState;
}

export function VoiceMode({ onClose, onToggleListen, state, transcript }: VoiceModeProps) {
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
        onClick={(event) => event.stopPropagation()}
        role="dialog"
      >
        <header className="voice-panel__head">
          <span className="voice-panel__title">Fusion ile konuş</span>
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
          <FusionAvatar scale={2} state={AVATAR[state]} />
          <p aria-live="polite" className="voice-panel__status">{DURUM_METNI[state]}</p>
          {transcript && <p className="voice-panel__transcript">{transcript}</p>}
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
          <p className="voice-panel__hint">Konuştukların sohbete yazılır.</p>
        </footer>
      </section>
    </div>
  );
}
