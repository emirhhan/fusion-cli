import { useCallback, useEffect, useRef, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import { startSpeechRecognition, stopSpeechRecognition } from "./windowBridge";

interface RecognitionLine { session: number; line: string }
interface RecognitionEnded { session: number; stderr_summary?: { message?: string } | null }
interface Spoken { tur?: string; metin?: string }

export interface DictationRuntime {
  onLine: (handler: (event: RecognitionLine) => void) => Promise<() => void>;
  onEnded: (handler: (event: RecognitionEnded) => void) => Promise<() => void>;
  start: () => Promise<number>;
  stop: () => Promise<void>;
}

const runtimeDefault: DictationRuntime = {
  onLine: (handler) => listen<RecognitionLine>("ses://tanima", (event) => handler(event.payload)),
  onEnded: (handler) => listen<RecognitionEnded>("ses://tanima-sonlandi", (event) => handler(event.payload)),
  start: startSpeechRecognition,
  stop: stopSpeechRecognition,
};

/** Dikte metni composer'a yazar; mesajı kendi başına göndermez. */
export function useDictation(
  onText: (conversationId: string, text: string) => void,
  runtime: DictationRuntime = runtimeDefault,
) {
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const onTextRef = useRef(onText);
  onTextRef.current = onText;
  const active = useRef<{ conversationId: string; session: number; base: string } | null>(null);
  const unlisten = useRef<(() => void)[]>([]);
  const starting = useRef(false);
  const generation = useRef(0);

  const cleanup = useCallback(() => {
    unlisten.current.forEach((remove) => remove());
    unlisten.current = [];
    active.current = null;
    starting.current = false;
    generation.current += 1;
    setListening(false);
  }, []);
  const stop = useCallback(async () => {
    if (!active.current && !starting.current) return;
    cleanup();
    try { await runtime.stop(); } catch { setError("Dikte durdurulamadı."); }
  }, [cleanup, runtime]);
  useEffect(() => () => { void stop(); }, [stop]);

  const start = useCallback(async (conversationId: string, base: string) => {
    if (active.current || starting.current) return;
    const run = ++generation.current;
    starting.current = true;
    setError(null);
    let removeLine: (() => void) | null = null;
    let removeEnded: (() => void) | null = null;
    const pending: RecognitionLine[] = [];
    let endedEarly: RecognitionEnded | null = null;
    try {
      const applyLine = (payload: RecognitionLine) => {
        const current = active.current;
        if (!current) {
          if (generation.current === run) pending.push(payload);
          return;
        }
        if (current.session !== payload.session) return;
        let spoken: Spoken;
        try { spoken = JSON.parse(payload.line) as Spoken; } catch { return; }
        if (spoken.tur !== "kismi" && spoken.tur !== "son") return;
        const words = spoken.metin?.trim();
        if (!words) return;
        onTextRef.current(current.conversationId, `${current.base}${current.base.trim() ? " " : ""}${words}`);
        if (spoken.tur === "son") void stop();
      };
      removeLine = await runtime.onLine(applyLine);
      removeEnded = await runtime.onEnded((payload) => {
        if (!active.current && generation.current === run) {
          endedEarly = payload;
          return;
        }
        if (active.current?.session !== payload.session) return;
        if (payload.stderr_summary?.message) setError(payload.stderr_summary.message);
        cleanup();
      });
      const session = await runtime.start();
      if (generation.current !== run) {
        removeLine();
        removeEnded();
        await runtime.stop();
        return;
      }
      active.current = { conversationId, session, base };
      unlisten.current = [removeLine, removeEnded];
      starting.current = false;
      setListening(true);
      for (const event of pending) applyLine(event);
      if ((endedEarly as RecognitionEnded | null)?.session === session) {
        cleanup();
      }
    } catch {
      removeLine?.();
      removeEnded?.();
      cleanup();
      setError("Dikte başlatılamadı. Mikrofon ve konuşma izinlerini kontrol et.");
    }
  }, [cleanup, runtime, stop]);

  return { error, listening, start, stop };
}
