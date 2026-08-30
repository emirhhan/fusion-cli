import { useEffect, useState } from "react";
import { FusionAvatar, type AvatarState } from "./FusionAvatar";
import { MicIcon } from "./MicIcon";
import type { VoiceAsk } from "./bridge";
import type { VoicePhase } from "./voiceMachine";
import { VoiceSettings, type VoicePrefs } from "./VoiceSettings";
import { Waveform } from "./Waveform";
import "./VoiceMode.css";

export type VoiceState = VoicePhase;

const DURUM_METNI: Record<VoiceState, string> = {
  approval: "Onayın bekleniyor",
  error: "Bir sorun oluştu",
  idle: "Konuşmak için dokun",
  listening: "Dinliyorum…",
  talking: "Konuşuyorum",
  thinking: "Düşünüyorum…",
  transcribing: "Seni yazıya çeviriyorum…",
};

const AVATAR: Record<VoiceState, AvatarState> = {
  approval: "approval",
  error: "idle",
  idle: "idle",
  listening: "listening",
  talking: "talking",
  thinking: "thinking",
  transcribing: "listening",
};

interface VoiceModeProps {
  ask?: VoiceAsk | null;
  onAnswer?: (answer: string) => void;
  onClose: () => void;
  onPickModel?: () => void;
  onPrefsChange?: (next: VoicePrefs) => void;
  onToggleListen: () => void;
  onTop?: boolean;
  onTopChange?: (next: boolean) => void;
  onWideChange?: (next: boolean) => void;
  prefs?: VoicePrefs;
  state: VoiceState;
  transcript?: string;
  wide?: boolean;
}

const VARSAYILAN_TERCIH: VoicePrefs = { hiz: 1, model: null, robotik: 0.5 };

export function VoiceMode({
  ask = null,
  onAnswer,
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
  const [settingsOpen, setSettingsOpen] = useState(false);
  const hearing = state === "listening" || state === "transcribing";

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    if (!wide) setSettingsOpen(false);
  }, [wide]);

  return (
    <section
      aria-label="Fusion Talk"
      className="voice-panel"
      data-mode={wide ? "normal" : "mini"}
      data-state={state}
      role="region"
    >
      <header className="voice-panel__head" data-tauri-drag-region>
        <span aria-hidden="true" className="voice-panel__traffic"><i /><i /><i /></span>
        <strong className="voice-panel__title">Fusion Talk</strong>
        <span className="voice-panel__window-actions">
          {onWideChange && (
            <button
              aria-label={wide ? "Paneli küçült" : "Paneli büyüt"}
              aria-pressed={wide}
              className="voice-panel__size"
              onClick={() => onWideChange(!wide)}
              type="button"
            >
              {wide ? "↙" : "↗"}
            </button>
          )}
          <button aria-label="Konuşma kipini kapat" className="voice-panel__close" onClick={onClose} type="button">×</button>
        </span>
      </header>

      <div className="voice-panel__stage">
        <FusionAvatar scale={wide ? 1.42 : 0.48} state={AVATAR[state]} />
        <div className="voice-panel__content">
          <Waveform active={hearing} />
          {ask && onAnswer && (
            <div aria-label="Onay" className="voice-ask" role="group">
              <p className="voice-ask__text">{ask.metin}</p>
              <div className="voice-ask__buttons">
                {ask.secenekler.map((secenek) => (
                  <button key={secenek.deger} onClick={() => onAnswer(secenek.deger)} type="button">
                    {secenek.etiket}
                  </button>
                ))}
              </div>
            </div>
          )}
          <p aria-live="polite" className="voice-panel__status">{DURUM_METNI[state]}</p>
          {wide && transcript && <p className="voice-panel__transcript">{transcript}</p>}
        </div>
      </div>

      {wide && (
        <footer className="voice-panel__foot">
          <button
            aria-label={hearing ? "Dinlemeyi durdur" : "Konuşmaya başla"}
            aria-pressed={hearing}
            className="voice-panel__mic"
            onClick={onToggleListen}
            type="button"
          >
            <MicIcon size={22} />
          </button>
          <p className="voice-panel__hint">Konuştukların aynı sohbete yazılır.</p>
          {onPrefsChange && onTopChange && (
            <button
              aria-expanded={settingsOpen}
              aria-label="Ses ayarları"
              className="voice-panel__settings-toggle"
              onClick={() => setSettingsOpen((open) => !open)}
              type="button"
            >
              ⚙
            </button>
          )}
        </footer>
      )}

      {wide && settingsOpen && onPrefsChange && onTopChange && (
        <div className="voice-panel__settings-popover">
          <VoiceSettings
            onChange={onPrefsChange}
            onPickModel={onPickModel}
            onTop={onTop}
            onTopChange={onTopChange}
            prefs={prefs}
          />
        </div>
      )}
    </section>
  );
}
