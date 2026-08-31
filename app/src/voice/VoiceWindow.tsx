import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import { invoke } from "@tauri-apps/api/core";
import {
  answerVoiceAsk,
  emitVoiceMessage,
  onVoiceAsk,
  onVoicePrefsState,
  onVoiceRuntimeState,
  requestVoicePrefs,
  type VoiceAsk,
  type VoiceMessage,
  type VoicePrefsPayload,
  type VoiceRuntimeState,
} from "./bridge";
import { cuesEnabled, playCue } from "./cues";
import { VoiceMode } from "./VoiceMode";
import { initialVoiceMachine, voiceMachine } from "./voiceMachine";
import type { VoicePrefs } from "./VoiceSettings";
import { mergeVoiceSnapshot, readVoiceGeometry, saveVoiceGeometry } from "./geometry";
import {
  applyVoiceWindowGeometry,
  closeVoiceWindow,
  minimizeVoiceWindow,
  onVoiceWindowGeometryChanged,
  stopSpeechRecognition,
  type VoiceWindowGeometry,
  type VoiceWindowSnapshot,
} from "./windowBridge";
import { selectVoiceModel } from "../platform/dialog";

interface RecognitionLine {
  metin: string;
  tur: "hazir" | "kismi" | "son" | "hata";
}

type Unlisten = () => void;
interface RecognitionPayload { session: number; line: string; }
interface RecognitionEndedPayload { session: number; reason: string | null; }
type PendingRecognitionEvent =
  | { type: "output"; payload: RecognitionPayload }
  | { type: "ended"; payload: RecognitionEndedPayload };

export interface VoiceWindowRuntime {
  applyGeometry(geometry: VoiceWindowGeometry): Promise<void>;
  answerAsk(answer: string): Promise<void>;
  close(): Promise<void>;
  emitMessage(message: VoiceMessage): Promise<void>;
  onAsk(handler: (ask: VoiceAsk | null) => void): Promise<Unlisten>;
  onPrefs(handler: (prefs: VoicePrefsPayload) => void): Promise<Unlisten>;
  onRecognition(handler: (payload: RecognitionPayload) => void): Promise<Unlisten>;
  onRecognitionEnded(handler: (payload: RecognitionEndedPayload) => void): Promise<Unlisten>;
  onRuntimeState(handler: (state: VoiceRuntimeState) => void): Promise<Unlisten>;
  onWindowGeometry(handler: (snapshot: VoiceWindowSnapshot) => void): Promise<Unlisten>;
  pickModel(): Promise<string | null>;
  /** PermissionCenter için dar, enjekte edilebilir ön denetim noktası. */
  preflightRecognition(): Promise<boolean>;
  requestPrefs(prefs: VoicePrefsPayload | null): Promise<void>;
  startRecognition(): Promise<number | void>;
  stopRecognition(): Promise<void>;
}

const DEFAULT_RUNTIME: VoiceWindowRuntime = {
  applyGeometry: applyVoiceWindowGeometry,
  answerAsk: answerVoiceAsk,
  close: closeVoiceWindow,
  emitMessage: emitVoiceMessage,
  onAsk: onVoiceAsk,
  onPrefs: onVoicePrefsState,
  onRecognition: (handler) => listen<RecognitionPayload>("ses://tanima", (event) => handler(event.payload)),
  onRecognitionEnded: (handler) => listen<{ session: number; stderr_summary?: { message?: string } | null }>(
    "ses://tanima-sonlandi",
    (event) => handler({ session: event.payload.session, reason: event.payload.stderr_summary?.message ?? null }),
  ),
  onRuntimeState: onVoiceRuntimeState,
  onWindowGeometry: onVoiceWindowGeometryChanged,
  pickModel: selectVoiceModel,
  preflightRecognition: async () => true,
  requestPrefs: requestVoicePrefs,
  startRecognition: () => invoke<number>("tanima_baslat"),
  stopRecognition: stopSpeechRecognition,
};

const ACCEPT_WORDS = new Set(["evet", "onayla", "kabul", "tamam", "olur"]);
const REJECT_WORDS = new Set(["hayir", "reddet", "ret", "iptal", "olmaz"]);

function normalizeSpeech(value: string): string {
  return value
    .trim()
    .toLocaleLowerCase("tr-TR")
    .replace(/ı/g, "i")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

/** Belirsiz konuşma hiçbir zaman varsayılan onaya dönüşmez. */
export function matchSpokenAnswer(text: string, ask: VoiceAsk): string | null {
  const spoken = normalizeSpeech(text);
  if (!spoken) return null;
  const exact = ask.secenekler.filter((option) =>
    [option.deger, option.etiket].some((value) => normalizeSpeech(value) === spoken),
  );
  if (exact.length === 1) return exact[0].deger;
  if (spoken.includes(" ")) return null;

  const family = ACCEPT_WORDS.has(spoken) ? ACCEPT_WORDS : REJECT_WORDS.has(spoken) ? REJECT_WORDS : null;
  if (!family) return null;
  const semantic = ask.secenekler.filter((option) =>
    [option.deger, option.etiket].some((value) => family.has(normalizeSpeech(value))),
  );
  return semantic.length === 1 ? semantic[0].deger : null;
}

interface VoiceWindowProps {
  runtime?: VoiceWindowRuntime;
}

/** Ayrı, hafif Talk penceresi; ana pencerenin aynı aktif sohbetini kullanır. */
export function VoiceWindow({ runtime = DEFAULT_RUNTIME }: VoiceWindowProps = {}) {
  const [machine, dispatch] = useReducer(voiceMachine, initialVoiceMachine);
  const initialGeometry = useRef(readVoiceGeometry(window.localStorage));
  const geometryRef = useRef(initialGeometry.current);
  const [wide, setWide] = useState(initialGeometry.current.wide);
  const [onTop, setOnTop] = useState(initialGeometry.current.onTop);
  const [prefs, setPrefs] = useState<VoicePrefs>({ hiz: 1, model: null, robotik: 0.5 });
  const [ask, setAsk] = useState<VoiceAsk | null>(null);
  const machineRef = useRef(machine);
  const askRef = useRef(ask);
  const sentRevision = useRef(0);
  const activeSession = useRef(0);
  const nextSession = useRef(0);
  const recognitionIntent = useRef(0);
  const startingIntent = useRef<number | null>(null);
  const pendingRecognitionEvents = useRef<PendingRecognitionEvent[]>([]);
  const replayRecognitionEvent = useRef<((event: PendingRecognitionEvent) => void) | null>(null);
  const finalizedSession = useRef<number | null>(null);
  const expectedRecognitionEnd = useRef<number | null>(null);
  const restartAfterRecognitionEnd = useRef(false);
  const recognitionQueue = useRef<Promise<void>>(Promise.resolve());
  machineRef.current = machine;
  askRef.current = ask;

  const queueRecognition = useCallback(<T,>(operation: () => Promise<T>) => {
    const queued = recognitionQueue.current.then(operation, operation);
    recognitionQueue.current = queued.then(() => undefined, () => undefined);
    return queued;
  }, []);

  const startListening = useCallback(async () => {
    const intent = recognitionIntent.current + 1;
    recognitionIntent.current = intent;
    const requestedSession = nextSession.current + 1;
    dispatch({ type: "START_LISTENING", session: requestedSession });
    try {
      const permitted = await runtime.preflightRecognition();
      if (recognitionIntent.current !== intent) return;
      if (!permitted) {
        dispatch({ type: "FAILED", text: "Mikrofon izni verilmedi. İzin verdikten sonra yeniden deneyin." });
        return;
      }
      const session = await queueRecognition(async () => {
        if (recognitionIntent.current !== intent) return null;
        startingIntent.current = intent;
        const started = await runtime.startRecognition();
        return typeof started === "number" ? started : requestedSession;
      });
      if (startingIntent.current === intent) startingIntent.current = null;
      if (session === null || recognitionIntent.current !== intent) return;
      nextSession.current = Math.max(nextSession.current, session);
      activeSession.current = session;
      finalizedSession.current = null;
      expectedRecognitionEnd.current = null;
      dispatch({ type: "START_LISTENING", session });
      const pending = pendingRecognitionEvents.current;
      pendingRecognitionEvents.current = [];
      pending.forEach((event) => {
        if (event.payload.session === session) replayRecognitionEvent.current?.(event);
      });
      if (cuesEnabled()) playCue("listen-start");
    } catch (reason) {
      dispatch({ type: "FAILED", text: `Konuşma tanıma başlatılamadı: ${String(reason)}` });
    }
  }, [queueRecognition, runtime]);

  const stopListening = useCallback(async () => {
    recognitionIntent.current += 1;
    startingIntent.current = null;
    pendingRecognitionEvents.current = [];
    dispatch({ type: "STOPPED" });
    if (cuesEnabled()) playCue("listen-stop");
    expectedRecognitionEnd.current = activeSession.current || null;
    activeSession.current = 0;
    try {
      await queueRecognition(() => runtime.stopRecognition());
    } catch (reason) {
      dispatch({ type: "FAILED", text: `Konuşma tanıma durdurulamadı: ${String(reason)}` });
    }
  }, [queueRecognition, runtime]);

  useEffect(() => {
    void runtime.applyGeometry(geometryRef.current).catch(() => undefined);
    const remove = runtime.onWindowGeometry((snapshot) => {
      geometryRef.current = mergeVoiceSnapshot(geometryRef.current, snapshot);
      saveVoiceGeometry(window.localStorage, geometryRef.current);
    });
    return () => { void remove.then((unlisten) => unlisten()).catch(() => undefined); };
  }, [runtime]);

  useEffect(() => {
    const remove = runtime.onAsk((incoming) => {
      const open = incoming?.acik === true ? incoming : null;
      setAsk(open);
      dispatch({ type: open ? "ASK_OPENED" : "ASK_CLOSED" });
      if (open && activeSession.current === 0) {
        void startListening();
      }
    });
    return () => { void remove.then((unlisten) => unlisten()).catch(() => undefined); };
  }, [runtime, startListening]);

  useEffect(() => {
    const remove = runtime.onPrefs((incoming) => setPrefs(incoming));
    void runtime.requestPrefs(null);
    return () => { void remove.then((unlisten) => unlisten()).catch(() => undefined); };
  }, [runtime]);

  useEffect(() => {
    let alive = true;
    let removeRecognition: Unlisten | null = null;
    let removeEnded: Unlisten | null = null;
    const handleRecognition = (payload: RecognitionPayload) => {
      if (payload.session !== activeSession.current) {
        if (activeSession.current === 0 && startingIntent.current !== null) {
          pendingRecognitionEvents.current.push({ type: "output", payload });
        }
        return;
      }
      let line: RecognitionLine;
      try {
        line = JSON.parse(payload.line) as RecognitionLine;
      } catch {
        return;
      }
      if (line.tur === "hata") {
        expectedRecognitionEnd.current = payload.session;
        dispatch({ type: "FAILED", text: line.metin });
      } else if (line.tur === "kismi") {
        if (!askRef.current) dispatch({ type: "PARTIAL", session: payload.session, text: line.metin });
      } else if (line.tur === "son") {
        if (finalizedSession.current === payload.session) return;
        finalizedSession.current = payload.session;
        expectedRecognitionEnd.current = payload.session;
        const openAsk = askRef.current;
        const answer = openAsk ? matchSpokenAnswer(line.metin, openAsk) : null;
        if (answer) {
          askRef.current = null;
          setAsk(null);
          dispatch({ type: "ASK_CLOSED" });
          void runtime.answerAsk(answer);
        } else if (openAsk) {
          // Fail-closed: belirsiz söz ne onaydır ne de yeni sohbet turu.
          // Yardımcı finalden sonra çıktığı için bitiş olayında yeniden dinle.
          restartAfterRecognitionEnd.current = true;
        } else {
          dispatch({ type: "FINAL", session: payload.session, text: line.metin });
        }
      }
    };
    const handleEnded = ({ session, reason }: RecognitionEndedPayload) => {
      if (session !== activeSession.current) {
        if (activeSession.current === 0 && startingIntent.current !== null) {
          pendingRecognitionEvents.current.push({ type: "ended", payload: { session, reason } });
        }
        return;
      }
      if (restartAfterRecognitionEnd.current) {
        restartAfterRecognitionEnd.current = false;
        activeSession.current = 0;
        expectedRecognitionEnd.current = null;
        void startListening();
        return;
      }
      if (expectedRecognitionEnd.current === session) {
        expectedRecognitionEnd.current = null;
        activeSession.current = 0;
        return;
      }
      activeSession.current = 0;
      dispatch({
        type: "FAILED",
        text: reason || "Konuşma tanıma beklenmedik şekilde kapandı.",
      });
    };
    replayRecognitionEvent.current = (event) => {
      if (event.type === "output") handleRecognition(event.payload);
      else handleEnded(event.payload);
    };
    void Promise.all([
      runtime.onRecognition(handleRecognition),
      runtime.onRecognitionEnded(handleEnded),
    ]).then(([recognition, ended]) => {
      if (!alive) {
        recognition();
        ended();
        return;
      }
      removeRecognition = recognition;
      removeEnded = ended;
      void startListening();
    }).catch((reason) => {
      if (alive) dispatch({ type: "FAILED", text: String(reason) });
    });
    return () => {
      alive = false;
      recognitionIntent.current += 1;
      startingIntent.current = null;
      pendingRecognitionEvents.current = [];
      replayRecognitionEvent.current = null;
      removeRecognition?.();
      removeEnded?.();
      expectedRecognitionEnd.current = activeSession.current || null;
      activeSession.current = 0;
      void queueRecognition(() => runtime.stopRecognition()).catch(() => undefined);
    };
  }, [queueRecognition, runtime, startListening]);

  useEffect(() => {
    if (machine.finalRevision <= sentRevision.current || !machine.finalText) return;
    sentRevision.current = machine.finalRevision;
    if (cuesEnabled()) playCue("thinking");
    void runtime.emitMessage({ kaynak: "kullanici", metin: machine.finalText });
  }, [machine.finalRevision, machine.finalText, runtime]);

  useEffect(() => {
    const remove = runtime.onRuntimeState((incoming) => {
      if (incoming.durum === "talking") {
        recognitionIntent.current += 1;
        startingIntent.current = null;
        pendingRecognitionEvents.current = [];
        expectedRecognitionEnd.current = activeSession.current || null;
        activeSession.current = 0;
        void queueRecognition(() => runtime.stopRecognition()).catch(() => undefined);
        dispatch({ type: "ASSISTANT_STARTED", text: incoming.metin });
        return;
      }
      if (incoming.durum === "listening" || incoming.durum === "idle") {
        const shouldResume = machineRef.current.autoListen;
        dispatch({ type: "ASSISTANT_FINISHED" });
        if (shouldResume) void startListening();
      } else if (incoming.durum === "error") {
        dispatch({ type: "FAILED", text: incoming.metin ?? "Sesli yanıt tamamlanamadı." });
      }
    });
    return () => { void remove.then((unlisten) => unlisten()).catch(() => undefined); };
  }, [queueRecognition, runtime, startListening]);

  useEffect(() => {
    document.body.style.background = "transparent";
    document.body.style.overflow = "hidden";
  }, []);

  const visibleTranscript = machine.error ?? machine.transcript;
  const hearing = machine.phase === "listening" || machine.phase === "transcribing";

  return (
    <VoiceMode
      ask={ask}
      onAnswer={(answer) => {
        setAsk(null);
        dispatch({ type: "ASK_CLOSED" });
        void runtime.answerAsk(answer);
      }}
      onClose={() => void runtime.close()}
      onMinimize={() => void minimizeVoiceWindow()}
      onPickModel={() => {
        void runtime.pickModel().then((path) => {
          if (!path) return;
          const next = { ...prefs, model: path };
          setPrefs(next);
          return runtime.requestPrefs(next);
        }).catch(() => undefined);
      }}
      onPrefsChange={(next) => {
        setPrefs(next);
        void runtime.requestPrefs(next);
      }}
      onTop={onTop}
      onTopChange={(next) => {
        setOnTop(next);
        geometryRef.current = { ...geometryRef.current, onTop: next };
        saveVoiceGeometry(window.localStorage, geometryRef.current);
        void runtime.applyGeometry(geometryRef.current).catch(() => undefined);
      }}
      onWideChange={(next) => {
        setWide(next);
        geometryRef.current = { ...geometryRef.current, wide: next };
        saveVoiceGeometry(window.localStorage, geometryRef.current);
        void runtime.applyGeometry(geometryRef.current).catch(() => undefined);
      }}
      prefs={prefs}
      onToggleListen={() => void (hearing ? stopListening() : startListening())}
      state={machine.phase}
      transcript={visibleTranscript}
      wide={wide}
    />
  );
}
