import { useEffect, useState } from 'react';
import {
  ChevronDown,
  Mic,
  MicOff,
  PhoneOff,
  Volume2,
  VolumeX,
  Maximize2,
} from 'lucide-react';
import { Mascot } from './Mascot';
import type { Dot } from '../shared/types';
import type { useVoice } from './useVoice';

/** `useVoice` (OpenAI Realtime) ve `useLocalVoice` ortak yüzü. */
export type CallControls = ReturnType<typeof useVoice> & {
  interrupt?: () => Promise<void>;
  engineKind?: 'fusion' | 'browser';
};

export function CallView({ dot, voice }: { dot: Dot; voice: CallControls }) {
  const [minimized, setMinimized] = useState(false);
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (voice.status !== 'active') return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [voice.status]);
  if (voice.status === 'idle') return null;
  const seconds = voice.startedAt
    ? Math.max(0, Math.floor((now - voice.startedAt) / 1000))
    : 0;
  const duration = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
  const label =
    voice.status === 'connecting'
      ? 'Bağlanıyor…'
      : voice.status === 'ending'
        ? 'Arama kaydediliyor…'
        : voice.muted
          ? 'Mikrofon kapalı'
          : voice.phase === 'speaking'
            ? `${dot.name} konuşuyor`
            : voice.phase === 'thinking'
              ? 'Üzerinde çalışıyor…'
              : 'Dinliyor';
  return (
    <section
      className={`call-view ${minimized ? 'minimized' : ''}`}
      aria-label={`${dot.name} ile sesli arama`}
    >
      <div className="call-heading">
        <span>
          <span className="call-live-dot" /> Sesli arama
        </span>
        <button
          className="call-minimize"
          aria-label={
            minimized ? 'Arama görünümünü genişlet' : 'Arama görünümünü küçült'
          }
          onClick={() => setMinimized(!minimized)}
        >
          {minimized ? <Maximize2 size={18} /> : <ChevronDown size={20} />}
        </button>
      </div>
      <div className={`call-persona ${voice.phase}`}>
        <Mascot identity={dot.id} character={dot.character} name={dot.name} />
        <h2>{dot.name}</h2>
        <span className="call-timer" aria-label="Arama süresi">
          {duration}
        </span>
        <p role="status">{label}</p>
      </div>
      {!minimized && (
        <div className="call-caption" aria-live="polite">
          {voice.userCaption && (
            <p className="call-user-caption">
              <small>Sen</small>
              {voice.userCaption}
            </p>
          )}
          <p>
            <small>{dot.name}</small>
            {voice.caption || 'Doğal konuş. Kit’in seninle.'}
          </p>
        </div>
      )}
      {voice.error && (
        <p className="call-warning" role="alert">
          {voice.error}
        </p>
      )}
      <div className="call-controls">
        <button
          aria-label={
            voice.speakerMuted ? 'Arama sesini aç' : 'Arama sesini kapat'
          }
          aria-pressed={voice.speakerMuted}
          onClick={voice.toggleSpeaker}
          disabled={voice.status !== 'active'}
        >
          <span>{voice.speakerMuted ? <VolumeX /> : <Volume2 />}</span>
          <small>Hoparlör</small>
        </button>
        <button
          className="call-end"
          aria-label="Sesli aramayı bitir"
          onClick={() => void voice.end()}
          disabled={voice.status === 'ending'}
        >
          <span>
            <PhoneOff />
          </span>
          <small>Bitir</small>
        </button>
        <button
          aria-label={voice.muted ? 'Mikrofonu aç' : 'Mikrofonu kapat'}
          aria-pressed={voice.muted}
          onClick={voice.toggleMute}
          disabled={voice.status !== 'active'}
        >
          <span>{voice.muted ? <MicOff /> : <Mic />}</span>
          <small>{voice.muted ? 'Aç' : 'Kapat'}</small>
        </button>
      </div>
      {voice.interrupt && voice.phase === 'speaking' && (
        <button
          className="call-interrupt"
          onClick={() => void voice.interrupt?.()}
        >
          Sözünü kes
        </button>
      )}
      {!minimized && (
        <p className="call-footer">
          Yazı ve ses aynı sohbeti paylaşır
          {voice.engineKind === 'fusion'
            ? ' · Fusion yerel sesi (ücretsiz, çevrimdışı tanıma)'
            : voice.engineKind === 'browser'
              ? ' · Tarayıcı sesi'
              : ''}
        </p>
      )}
    </section>
  );
}
