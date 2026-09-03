import { getCurrentWindow } from "@tauri-apps/api/window";
import { type PointerEvent, useEffect, useState } from "react";
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
  calibrating: "Ortamı dinliyorum…",
  error: "Bir sorun oluştu",
  hearing: "Seni duyuyorum…",
  idle: "Konuşmak için dokun",
  interrupted: "Anlayamadım, tekrar söyle",
  listening: "Dinliyorum…",
  talking: "Konuşuyorum",
  thinking: "Düşünüyorum…",
  transcribing: "Seni yazıya çeviriyorum…",
};

const AVATAR: Record<VoiceState, AvatarState> = {
  approval: "approval",
  calibrating: "listening",
  error: "idle",
  hearing: "listening",
  idle: "idle",
  interrupted: "listening",
  listening: "listening",
  talking: "talking",
  thinking: "thinking",
  transcribing: "listening",
};

interface VoiceModeProps {
  ask?: VoiceAsk | null;
  listening: boolean;
  onAnswer?: (answer: string) => void;
  onClose: () => void;
  onMinimize: () => void;
  onPickModel?: () => void;
  onPrefsChange?: (next: VoicePrefs) => void;
  onTop?: boolean;
  onTopChange?: (next: boolean) => void;
  onWideChange?: (next: boolean) => void;
  prefs?: VoicePrefs;
  state: VoiceState;
  transcript?: string;
  wide?: boolean;
}

const VARSAYILAN_TERCIH: VoicePrefs = { hiz: 1, model: null, robotik: 0.5 };

function TrafficGlyph({ kind }: { kind: "close" | "minimize" | "size" }) {
  return (
    <svg aria-hidden="true" className="voice-panel__traffic-glyph" data-glyph={kind === "size" ? "zoom" : kind} viewBox="0 0 8 8">
      {kind === "close" && <path d="M1.75 1.75 6.25 6.25M6.25 1.75 1.75 6.25" />}
      {kind === "minimize" && <path d="M1.5 4h5" />}
      {kind === "size" && <path d="M1.25 3.5V1.25H3.5L1.25 3.5Zm5.5 1v2.25H4.5L6.75 4.5Z" />}
    </svg>
  );
}

export function VoiceMode({
  ask = null,
  listening,
  onAnswer,
  onClose,
  onMinimize,
  onPickModel,
  onPrefsChange,
  onTop = true,
  onTopChange,
  onWideChange,
  prefs = VARSAYILAN_TERCIH,
  state,
  transcript,
  wide = true,
}: VoiceModeProps) {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const startWindowDrag = (event: PointerEvent<HTMLElement>) => {
    if (event.button !== 0) return;
    event.preventDefault();
    void getCurrentWindow().startDragging().catch(() => undefined);
  };

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

  useEffect(() => {
    const root = document.getElementById("root");
    document.documentElement.dataset.talkSurface = "true";
    document.body.dataset.talkSurface = "true";
    if (root) root.dataset.talkSurface = "true";
    return () => {
      delete document.documentElement.dataset.talkSurface;
      delete document.body.dataset.talkSurface;
      if (root) delete root.dataset.talkSurface;
    };
  }, []);

  return (
    <section
      aria-label="Fusion Talk"
      className="voice-panel"
      data-mode={wide ? "normal" : "mini"}
      data-state={state}
      role="region"
    >
      <header className="voice-panel__head">
        <span aria-label="Pencere denetimleri" className="voice-panel__window-controls">
          <button aria-label="Konuşma kipini kapat" className="voice-panel__close" onClick={onClose} type="button"><TrafficGlyph kind="close" /></button>
          <button aria-label="Pencereyi simge durumuna küçült" className="voice-panel__minimize" onClick={onMinimize} type="button"><TrafficGlyph kind="minimize" /></button>
          {onWideChange && (
            <button
              aria-label={wide ? "Paneli küçült" : "Paneli büyüt"}
              aria-pressed={wide}
              className="voice-panel__size"
              onClick={() => onWideChange(!wide)}
              type="button"
            >
              <TrafficGlyph kind="size" />
            </button>
          )}
        </span>
        <span className="voice-panel__drag voice-panel__drag--left" data-tauri-drag-region onPointerDown={startWindowDrag} />
        <span className="voice-panel__drag voice-panel__drag--center" data-tauri-drag-region onPointerDown={startWindowDrag}>
          <strong className="voice-panel__title" data-tauri-drag-region>Fusion Talk</strong>
        </span>
        <span className="voice-panel__drag voice-panel__drag--right" data-tauri-drag-region onPointerDown={startWindowDrag} />
      </header>

      <div className="voice-panel__stage">
        <FusionAvatar scale={wide ? (state === "approval" ? 1.08 : 1.42) : 0.48} state={AVATAR[state]} />
        <div className="voice-panel__content">
          <Waveform active={listening} />
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
          {!ask && <p aria-live="polite" className="voice-panel__status">{DURUM_METNI[state]}</p>}
          {wide && transcript && <p className="voice-panel__transcript">{transcript}</p>}
        </div>
      </div>

      <footer className="voice-panel__foot">
        {/* Tuş DEĞİL, gösterge. Dinleme Talk açıkken sürekli açıktır;
            konuşmak için hiçbir şeye basılmaz. */}
        <span
          aria-label={listening ? "Dinliyor" : "Dinleme hazırlanıyor"}
          className="voice-panel__mic"
          data-dinliyor={listening}
          role="status"
        >
          <MicIcon size={wide ? 22 : 18} />
        </span>
        {wide && <>
          <p className="voice-panel__hint">Konuş; sözümü kesebilirsin.</p>
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
        </>}
      </footer>

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
