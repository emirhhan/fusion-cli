import { dragVoiceWindow } from "./windowBridge";
import { VoiceQuestion } from "./VoiceQuestion";
import { useEffect, useRef, useState } from "react";
import { FusionAvatar, type AvatarState } from "./FusionAvatar";
import type { VoiceAsk } from "./bridge";
import type { VoicePhase } from "./voiceMachine";
import { VoiceSettings, type VoicePrefs } from "./VoiceSettings";
import "./VoiceMode.css";
import "./VoicePet.css";

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
  answerPending?: boolean;
  listening: boolean;
  onAnswer?: (answer: string) => void;
  onClose: () => void;
  onDrag?: () => Promise<void>;
  onMinimize: () => void;
  onListen?: () => void;
  onInterrupt?: () => void;
  /** Son adımların kısa izi; sağ tık menüsünden "Tanı bilgisi" ile açılır. */
  diagnostics?: readonly string[];
  sessionOpen?: boolean;
  onPrefsChange?: (next: VoicePrefs) => void;
  onTop?: boolean;
  onTopChange?: (next: boolean) => void;
  onWideChange?: (next: boolean) => void;
  prefs?: VoicePrefs;
  state: VoiceState;
  transcript?: string;
  wide?: boolean;
}

const VARSAYILAN_TERCIH: VoicePrefs = { hiz: 1 };

export function VoiceMode({
  ask = null,
  answerPending = false,
  listening,
  onAnswer,
  onClose,
  onDrag = dragVoiceWindow,
  onMinimize,
  onListen,
  onInterrupt,
  diagnostics = [],
  sessionOpen = false,
  onPrefsChange,
  onTop = true,
  onTopChange,
  prefs = VARSAYILAN_TERCIH,
  state,
  transcript,
  wide = true,
}: VoiceModeProps) {
  const dragOrigin = useRef<{ x: number; y: number } | null>(null);
  const dragged = useRef(false);
  const [dragError, setDragError] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (menuOpen) setMenuOpen(false);
        else if (settingsOpen) setSettingsOpen(false);
        else onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen, settingsOpen, onClose]);

  // Açılır menü ve ayar paneli dışarıya basınca kapanır; yalnız Esc'e güvenmek
  // pencere odakta değilken paneli açık bırakıyordu.
  useEffect(() => {
    if (!menuOpen && !settingsOpen) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target instanceof Element ? event.target : null;
      if (target?.closest(".voice-panel__menu, .voice-panel__settings-popover")) return;
      setMenuOpen(false);
      setSettingsOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown, true);
    return () => document.removeEventListener("pointerdown", onPointerDown, true);
  }, [menuOpen, settingsOpen]);

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
      <div className="voice-panel__stage">
        <button type="button" className="voice-panel__character"
          aria-label={`Fusion. ${sessionOpen ? "Mikrofon açık, dinleme sürüyor; kapatmak için tıkla." : "Mikrofon kapalı; dinlemeyi başlatmak için tıkla."} ${listening ? "Mikrofon açık." : "Mikrofon kapalı."} ${DURUM_METNI[state]}`}
          aria-haspopup="menu" aria-expanded={menuOpen}
          title={sessionOpen ? "Dinliyorum — kapatmak için tıkla" : "Konuşmak için tıkla, taşımak için sürükle"}
          onPointerDown={(event) => {
            if (event.button !== 0) return;
            dragged.current = false;
            dragOrigin.current = { x: event.clientX, y: event.clientY };
            event.currentTarget.setPointerCapture?.(event.pointerId);
          }}
          onPointerMove={(event) => {
            const origin = dragOrigin.current;
            // Ufak el titremesi normal sol tıklamayı pencere taşımasına dönüştürmez.
            if (!origin || dragged.current || !(event.buttons & 1)
              || Math.hypot(event.clientX - origin.x, event.clientY - origin.y) < 6) return;
            dragged.current = true;
            dragOrigin.current = null;
            if (event.currentTarget.hasPointerCapture?.(event.pointerId)) {
              event.currentTarget.releasePointerCapture(event.pointerId);
            }
            setMenuOpen(false);
            setDragError(null);
            void onDrag().catch(() => setDragError("Taşıma başlatılamadı. Karakteri yeniden sürükle."));
          }}
          onPointerUp={() => { dragOrigin.current = null; }}
          onPointerCancel={() => { dragOrigin.current = null; }}
          onClick={(event) => {
            if (dragged.current && event.detail > 0) { dragged.current = false; event.preventDefault(); return; }
            dragged.current = false;
            setMenuOpen(false);
            // Fusion konuşurken tıklamak sözünü keser; oturum yoksa tıklamak oturumu başlatır.
            if (state === "talking") onInterrupt?.();
            else onListen?.();
          }}
          onContextMenu={(event) => { event.preventDefault(); setMenuOpen((open) => !open); }}
          onKeyDown={(event) => { if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) { event.preventDefault(); setMenuOpen(true); } }}>
          <FusionAvatar scale={wide ? (state === "approval" ? 1.08 : 1.42) : 0.9} state={AVATAR[state]} />
        </button>
        <div className="voice-panel__content">
          {dragError && <p role="alert" className="voice-panel__error">{dragError}</p>}
          {state !== "error" && <span className="voice-panel__sr" role="status" aria-label={listening ? "Dinliyor" : "Dinleme hazırlanıyor"}>{DURUM_METNI[state]}</span>}
          {state === "thinking" && <span className="voice-panel__thinking" aria-hidden="true">Hmm…</span>}
          {/* Ne olduğu GÖRÜNÜR olsun: ne duyuldu, dinliyor mu, düşünüyor mu. */}
          {state !== "error" && state !== "thinking" && (
            <span className="voice-panel__caption" aria-hidden="true">{transcript || DURUM_METNI[state]}</span>
          )}
          {state !== "error" && transcript && <span className="voice-panel__sr">{transcript}</span>}
          {ask && onAnswer && (
            <VoiceQuestion ask={ask} answerPending={answerPending} key={`${ask.sessionId ?? ""}:${ask.questionId ?? ""}:${ask.metin}`} onAnswer={onAnswer} />
          )}
          {state === "error" && transcript && <p role="alert" className="voice-panel__error">{transcript}</p>}
        </div>
      </div>

      {menuOpen && <div aria-label="Konuşma menüsü" className="voice-panel__menu" role="menu">
        {onPrefsChange && onTopChange && <button onClick={() => { setMenuOpen(false); setSettingsOpen(true); }} role="menuitem" type="button">Ses ayarları</button>}
        <button onClick={() => { setMenuOpen(false); setDiagnosticsOpen(true); }} role="menuitem" type="button">Tanı bilgisi</button>
        <button onClick={() => { setMenuOpen(false); onMinimize(); }} role="menuitem" type="button">Simge durumuna küçült</button>
        <button onClick={() => { setMenuOpen(false); onClose(); }} role="menuitem" type="button">Konuşmayı kapat</button>
      </div>}
      {diagnosticsOpen && (
        <div aria-label="Tanı bilgisi" className="voice-panel__diagnostics" role="dialog">
          <button onClick={() => setDiagnosticsOpen(false)} type="button">Kapat</button>
          <pre>{diagnostics.length ? diagnostics.join("\n") : "Henüz kayıt yok."}</pre>
        </div>
      )}
      {settingsOpen && onPrefsChange && onTopChange && (
        <div className="voice-panel__settings-popover">
          <button aria-label="Ses ayarlarını kapat" className="voice-panel__settings-close" onClick={() => setSettingsOpen(false)} type="button">Kapat</button>
          <VoiceSettings
            onChange={onPrefsChange}
            onTop={onTop}
            onTopChange={onTopChange}
            prefs={prefs}
          />
        </div>
      )}
    </section>
  );
}
