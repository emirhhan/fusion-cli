import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { listen } from "@tauri-apps/api/event";
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
  onVoiceWindowGeometryChanged,
  startSpeechRecognition,
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

export interface VoiceWindowRuntime {
  applyGeometry(geometry: VoiceWindowGeometry): Promise<void>;
  answerAsk(answer: string): Promise<void>;
  close(): Promise<void>;
  emitMessage(message: VoiceMessage): Promise<void>;
  onAsk(handler: (ask: VoiceAsk | null) => void): Promise<Unlisten>;
  onPrefs(handler: (prefs: VoicePrefsPayload) => void): Promise<Unlisten>;
  onRecognition(handler: (payload: string) => void): Promise<Unlisten>;
  onRuntimeState(handler: (state: VoiceRuntimeState) => void): Promise<Unlisten>;
  onWindowGeometry(handler: (snapshot: VoiceWindowSnapshot) => void): Promise<Unlisten>;
  pickModel(): Promise<string | null>;
  requestPrefs(prefs: VoicePrefsPayload | null): Promise<void>;
  startRecognition(): Promise<void>;
  stopRecognition(): Promise<void>;
}

const DEFAULT_RUNTIME: VoiceWindowRuntime = {
  applyGeometry: applyVoiceWindowGeometry,
  answerAsk: answerVoiceAsk,
  close: closeVoiceWindow,
  emitMessage: emitVoiceMessage,
  onAsk: onVoiceAsk,
  onPrefs: onVoicePrefsState,
  onRecognition: (handler) => listen<string>("ses://tanima", (event) => handler(event.payload)),
  onRuntimeState: onVoiceRuntimeState,
  onWindowGeometry: onVoiceWindowGeometryChanged,
  pickModel: selectVoiceModel,
  requestPrefs: requestVoicePrefs,
  startRecognition: startSpeechRecognition,
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
  machineRef.current = machine;
  askRef.current = ask;

  const startListening = useCallback(async () => {
    dispatch({ type: "START_LISTENING" });
    if (cuesEnabled()) playCue("listen-start");
    try {
      await runtime.startRecognition();
    } catch (reason) {
      dispatch({ type: "FAILED", text: String(reason) });
    }
  }, [runtime]);

  const stopListening = useCallback(async () => {
    dispatch({ type: "STOPPED" });
    if (cuesEnabled()) playCue("listen-stop");
    try {
      await runtime.stopRecognition();
    } catch (reason) {
      dispatch({ type: "FAILED", text: String(reason) });
    }
  }, [runtime]);

  useEffect(() => {
    void startListening();
    return () => { void runtime.stopRecognition().catch(() => undefined); };
  }, [runtime, startListening]);

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
    });
    return () => { void remove.then((unlisten) => unlisten()).catch(() => undefined); };
  }, [runtime]);

  useEffect(() => {
    const remove = runtime.onPrefs((incoming) => setPrefs(incoming));
    void runtime.requestPrefs(null);
    return () => { void remove.then((unlisten) => unlisten()).catch(() => undefined); };
  }, [runtime]);

  useEffect(() => {
    const remove = runtime.onRecognition((payload) => {
      let line: RecognitionLine;
      try {
        line = JSON.parse(payload) as RecognitionLine;
      } catch {
        return;
      }
      if (line.tur === "hata") {
        dispatch({ type: "FAILED", text: line.metin });
      } else if (line.tur === "kismi") {
        dispatch({ type: "PARTIAL", text: line.metin });
      } else if (line.tur === "son") {
        const openAsk = askRef.current;
        const answer = openAsk ? matchSpokenAnswer(line.metin, openAsk) : null;
        if (answer) {
          setAsk(null);
          dispatch({ type: "ASK_CLOSED" });
          void runtime.answerAsk(answer);
        } else {
          dispatch({ type: "FINAL", text: line.metin });
        }
      }
    });
    return () => { void remove.then((unlisten) => unlisten()).catch(() => undefined); };
  }, [runtime]);

  useEffect(() => {
    if (machine.finalRevision <= sentRevision.current || !machine.finalText) return;
    sentRevision.current = machine.finalRevision;
    if (cuesEnabled()) playCue("thinking");
    void runtime.emitMessage({ kaynak: "kullanici", metin: machine.finalText });
  }, [machine.finalRevision, machine.finalText, runtime]);

  useEffect(() => {
    const remove = runtime.onRuntimeState((incoming) => {
      if (incoming.durum === "talking") {
        void runtime.stopRecognition().catch(() => undefined);
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
  }, [runtime, startListening]);

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
