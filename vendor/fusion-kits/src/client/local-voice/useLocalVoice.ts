import { useCallback, useEffect, useRef, useState } from 'react';
import { api, authHeaders, errorText } from '../api';
import type { VoiceEngine } from './engine';
import { detectVoiceEngine } from './detect';
import { spokenText, splitSentences } from './speech-text';

type Status = 'idle' | 'connecting' | 'active' | 'ending';
type Phase = 'listening' | 'speaking' | 'thinking';
const MIN_UTTERANCE_CHARS = 2;
const TRANSCRIPT_LIMIT = 20_000;

/** Anahtarsız sesli konuşma döngüsü: dinle → sözü sohbetin normal turuna ver →
 * cevabı cümle cümle seslendir → yeniden dinle. Kit konuşurken mikrofon
 * kapalıdır (yarım çift yönlü); kendi sesini kullanıcı sözü sanmaz.
 * Dönüş biçimi `useVoice` ile aynıdır; `CallView` ikisini de çizer. */
export function useLocalVoice(
  threadId: string,
  onSaved: () => void,
  detect: () => Promise<VoiceEngine> = detectVoiceEngine,
) {
  const [status, setStatus] = useState<Status>('idle');
  const [phase, setPhase] = useState<Phase>('listening');
  const [error, setError] = useState('');
  const [muted, setMuted] = useState(false);
  const [speakerMuted, setSpeakerMuted] = useState(false);
  const [startedAt, setStartedAt] = useState<number>();
  const [caption, setCaption] = useState('');
  const [userCaption, setUserCaption] = useState('');
  const [engineKind, setEngineKind] = useState<VoiceEngine['kind']>();
  const epoch = useRef(0);
  const starting = useRef(false);
  const session = useRef<
    | {
        engine: VoiceEngine;
        id: string;
        transcript: string[];
        cancelled: boolean;
        busy: boolean;
        speechEpoch: number;
        listenEpoch: number;
        response?: AbortController;
      }
    | undefined
  >(undefined);
  // Dinleyici her sözde en güncel işleyiciyi çağırır (eski kapanış yakalanmaz).
  const onFinal = useRef<(text: string) => void>(() => {});
  const flags = useRef({ muted: false, speakerMuted: false });

  const listen = async () => {
    const current = session.current;
    if (!current || current.cancelled || flags.current.muted) return;
    const listening = ++current.listenEpoch;
    const owned = () =>
      session.current === current &&
      !current.cancelled &&
      !flags.current.muted &&
      current.listenEpoch === listening;
    setPhase('listening');
    try {
      await current.engine.listen({
        onPartial: (text) => {
          if (owned()) setUserCaption(text);
        },
        onFinal: (text) => {
          if (owned()) onFinal.current(text);
        },
        onError: (message) => {
          if (owned()) setError(message);
        },
      });
    } catch (e) {
      if (owned()) setError(errorText(e, 'Mikrofon açılamadı.'));
    }
  };

  const speak = async (text: string) => {
    const current = session.current;
    if (!current) return;
    const speaking = current.speechEpoch;
    setPhase('speaking');
    for (const sentence of splitSentences(spokenText(text))) {
      if (
        session.current !== current ||
        current.cancelled ||
        current.speechEpoch !== speaking ||
        flags.current.speakerMuted
      )
        break;
      await current.engine.speak(sentence);
    }
  };

  const handleFinal = async (raw: string) => {
    const current = session.current;
    const text = raw.trim();
    if (!current || current.cancelled || current.busy) return;
    if (text.length < MIN_UTTERANCE_CHARS) return;
    current.busy = true;
    try {
      ++current.listenEpoch;
      await current.engine.stopListening();
      if (session.current !== current || current.cancelled) return;
      setUserCaption(text);
      setCaption('');
      setPhase('thinking');
      current.transcript.push(`Sen: ${text}`);
      current.response = new AbortController();
      const answer = await api<{ text: string }>(
        `/voice/calls/${current.id}/utterance`,
        'POST',
        { text },
        current.response.signal,
      );
      if (session.current !== current || current.cancelled) return;
      current.transcript.push(`Kit: ${answer.text}`);
      setCaption(spokenText(answer.text));
      onSaved();
      await speak(answer.text);
    } catch (e) {
      if (session.current === current && !current.cancelled)
        setError(errorText(e, 'Kit bu söze yanıt veremedi.'));
    } finally {
      current.busy = false;
      current.response = undefined;
    }
    if (session.current === current && !current.cancelled) await listen();
  };
  onFinal.current = (text) => void handleFinal(text);

  const finish = useCallback(async (keepalive = false) => {
    const current = session.current;
    session.current = undefined;
    if (!current) return;
    current.cancelled = true;
    ++current.listenEpoch;
    ++current.speechEpoch;
    current.response?.abort();
    current.engine.close();
    const body = JSON.stringify({
      transcript: current.transcript.join('\n').slice(0, TRANSCRIPT_LIMIT),
    });
    if (keepalive) {
      void fetch(`/api/voice/calls/${current.id}/end`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body,
        keepalive: true,
      }).catch(() => {});
      return;
    }
    await api(`/voice/calls/${current.id}/end`, 'POST', JSON.parse(body));
  }, []);

  const start = async () => {
    if (session.current || starting.current) return;
    starting.current = true;
    const generation = ++epoch.current;
    setStatus('connecting');
    setError('');
    setCaption('');
    setUserCaption('');
    setStartedAt(undefined);
    flags.current = { muted: false, speakerMuted: false };
    setMuted(false);
    setSpeakerMuted(false);
    let engine: VoiceEngine | undefined;
    try {
      engine = await detect();
      if (generation !== epoch.current) {
        engine.close();
        return;
      }
      setEngineKind(engine.kind);
      const call = await api<{ id: string }>('/voice/calls/local', 'POST', {
        threadId,
      });
      if (generation !== epoch.current) {
        engine.close();
        void api(`/voice/calls/${call.id}/end`, 'POST', {
          transcript: '',
        }).catch(() => {});
        return;
      }
      session.current = {
        engine,
        id: call.id,
        transcript: [],
        cancelled: false,
        busy: false,
        speechEpoch: 0,
        listenEpoch: 0,
      };
      setStatus('active');
      setStartedAt(Date.now());
      await listen();
    } catch (e) {
      engine?.close();
      if (generation !== epoch.current) return;
      session.current = undefined;
      setStatus('idle');
      setError(errorText(e, 'Sesli konuşma başlatılamadı.'));
    } finally {
      if (generation === epoch.current) starting.current = false;
    }
  };

  const end = async () => {
    if (!session.current && !starting.current) return;
    const generation = ++epoch.current;
    starting.current = false;
    setStatus('ending');
    try {
      await finish();
      if (generation === epoch.current) onSaved();
    } catch (e) {
      if (generation === epoch.current)
        setError(errorText(e, 'Arama bitti ancak kaydedilemedi.'));
    } finally {
      if (generation === epoch.current) setStatus('idle');
    }
  };

  /** Kit konuşurken sözünü kes ve hemen dinlemeye dön. */
  const interrupt = async () => {
    const current = session.current;
    if (!current) return;
    ++current.speechEpoch;
    await current.engine.stopSpeaking();
  };

  const toggleMute = () => {
    const next = !flags.current.muted;
    flags.current.muted = next;
    setMuted(next);
    const current = session.current;
    if (!current || current.busy) return;
    if (next) {
      ++current.listenEpoch;
      void current.engine.stopListening();
    } else void listen();
  };

  const toggleSpeaker = () => {
    const next = !flags.current.speakerMuted;
    flags.current.speakerMuted = next;
    setSpeakerMuted(next);
    if (next) {
      if (session.current) ++session.current.speechEpoch;
      void session.current?.engine.stopSpeaking();
    }
  };

  useEffect(
    () => () => {
      ++epoch.current;
      starting.current = false;
      void finish(true);
    },
    [finish, threadId],
  );

  return {
    status,
    error,
    start,
    end,
    interrupt,
    muted,
    speakerMuted,
    startedAt,
    phase,
    caption,
    userCaption,
    engineKind,
    toggleMute,
    toggleSpeaker,
  };
}
