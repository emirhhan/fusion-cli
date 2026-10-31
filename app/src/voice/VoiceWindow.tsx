import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { PermissionPrompt } from "../permissions/PermissionPrompt";
import { usePermissions } from "../permissions/usePermissions";
import { hasSettingsLink, type PermissionBridge } from "../permissions/types";
import { nativePermissionBridge } from "../platform/permissions";
import { listen } from "@tauri-apps/api/event";
import {
  answerVoiceAsk,
  emitVoiceMessage,
  interruptVoiceSpeech,
  onVoiceAsk,
  onVoicePrefsState,
  onVoiceRuntimeState,
  requestVoicePrefs,
  type VoiceAsk,
  type VoiceMessage,
  type VoicePrefsPayload,
  type VoiceRuntimeState,
} from "./bridge";
import { acknowledgeWake, cancelThinkingCue, diktePasifMi, routeWakeSpeech, speakThinkingCue, speechFailureText } from "./wake";
import { cevapYankisiMi, yankiMi } from "./echo";
import { cuesEnabled, playCue } from "./cues";
import { VoiceMode } from "./VoiceMode";
import {
  evaluateRecognitionTurn,
  reconcileRecognition,
  initialVoiceMachine,
  voiceMachine,
  type RecognitionEvent,
} from "./voiceMachine";
import type { VoicePrefs } from "./VoiceSettings";
import { mergeVoiceSnapshot, readVoiceGeometry, saveVoiceGeometry } from "./geometry";
import {
  applyVoiceWindowGeometry,
  closeVoiceWindow,
  minimizeVoiceWindow,
  onVoiceWindowGeometryChanged,
  startSpeechRecognition,
  stopSpeechRecognition,
  type VoiceWindowGeometry,
  type VoiceWindowSnapshot,
} from "./windowBridge";

type Unlisten = () => void;
interface RecognitionPayload { session: number; line: string; }
interface RecognitionEndedPayload { session: number; reason: string | null; }
type PendingRecognitionEvent =
  | { type: "output"; payload: RecognitionPayload }
  | { type: "ended"; payload: RecognitionEndedPayload };

// Yavaş konuşanı kesmemek için yardımcının kendi bitiş süresinden (2,2 sn) uzun.
const PARTIAL_FINAL_DELAY_MS = 2_600;

export interface VoiceWindowRuntime {
  applyGeometry(geometry: VoiceWindowGeometry): Promise<void>;
  answerAsk(answer: string, question?: VoiceAsk): Promise<void>;
  close(): Promise<void>;
  interruptSpeech(): Promise<void>;
  emitMessage(message: VoiceMessage): Promise<void>;
  onAsk(handler: (ask: VoiceAsk | null) => void): Promise<Unlisten>;
  onPrefs(handler: (prefs: VoicePrefsPayload) => void): Promise<Unlisten>;
  onRecognition(handler: (payload: RecognitionPayload) => void): Promise<Unlisten>;
  onRecognitionEnded(handler: (payload: RecognitionEndedPayload) => void): Promise<Unlisten>;
  onRuntimeState(handler: (state: VoiceRuntimeState) => void): Promise<Unlisten>;
  onWindowGeometry(handler: (snapshot: VoiceWindowSnapshot) => void): Promise<Unlisten>;
  /** PermissionCenter için dar, enjekte edilebilir ön denetim noktası. */
  preflightRecognition(): Promise<boolean>;
  requestPrefs(prefs: VoicePrefsPayload | null): Promise<void>;
  startRecognition(): Promise<number | void>;
  stopRecognition(): Promise<void>;
}

const DEFAULT_RUNTIME: VoiceWindowRuntime = {
  applyGeometry: applyVoiceWindowGeometry,
  answerAsk: (answer, question) => answerVoiceAsk(answer, undefined,
    question?.sessionId && question.questionId
      ? { sessionId: question.sessionId, questionId: question.questionId } : undefined),
  close: closeVoiceWindow,
  interruptSpeech: interruptVoiceSpeech,
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
  preflightRecognition: async () => true,
  requestPrefs: requestVoicePrefs,
  startRecognition: startSpeechRecognition,
  stopRecognition: stopSpeechRecognition,
};

/** Beklenmedik çökme sonrası ilk yeniden deneme gecikmesi. */
const YENIDEN_BASLATMA_TABANI_MS = 800;
/** Mikrofon açıkken bu kadar süre kimse konuşmazsa kendiliğinden kapanır. */
const OTURUM_BOSTA_BITIS_MS = 15_000;
const OTURUM_KONTROL_ARALIGI_MS = 2_000;
/** Düşünme bu kadar sürerse "Hmm" denir, sürerse aralıklarla tekrarlanır. */
const DUSUNME_IPUCU_GECIKME_MS = 1_200;
const DUSUNME_IPUCU_TEKRAR_MS = 7_000;
/**
 * Düşünme bu kadar sürüp ana pencereden hiçbir durum gelmezse (boş yanıt, çekirdek takılması, yayın
 * hatası) Talk "Düşünüyorum…"da sonsuza kadar kalmaz; kullanıcıya söylenir ve tekrar denenebilir.
 */
const DUSUNME_ZAMAN_ASIMI_MS = 90_000;
/** Talk açılışında tercih isteği cevaplanmazsa kaç kez, hangi aralıkla yeniden istenir. */
const TERCIH_ISTEK_DENEME = 4;
const TERCIH_ISTEK_ARALIGI_MS = 1_000;
/** Bu kadar ardışık verimsiz oturumdan sonra dinleme bırakılır; mikrofon sonsuz açılıp kapanmaz. */
const ARDARDA_COKME_TAVANI = 5;

/** Açık onay sorusu bu süreden sonra sesle cevaplanamaz; eski soruya geç gelen "evet" işlem onaylamaz. */
const ONAY_SORUSU_OMRU_MS = 120_000;

/** Geri çekilmenin tavanı; kullanıcı sonsuza kadar sessiz kalmamalı. */
const YENIDEN_BASLATMA_TAVANI_MS = 8_000;

/**
 * Ardışık verimsiz oturum sayısından yeniden başlatma kararı: vazgeç ya da kaç ms sonra dene.
 * Ölçüldü (29 Ekim, U2-09): tavan 8 sn'ydi ve vazgeçme eşiği yoktu; kalıcı hatada (ağ yok, dil
 * paketi eksik) mikrofon sonsuza dek açılıp kapanıyordu.
 */
export function yenidenBaslatmaKarari(
  ardArdaCokme: number, tabanMs = YENIDEN_BASLATMA_TABANI_MS,
): { vazgec: boolean; gecikmeMs: number } {
  if (ardArdaCokme >= ARDARDA_COKME_TAVANI) return { vazgec: true, gecikmeMs: 0 };
  return { vazgec: false, gecikmeMs: ardArdaCokme === 0 ? 0 : Math.min(tabanMs * ardArdaCokme, YENIDEN_BASLATMA_TAVANI_MS) };
}

const ACCEPT_WORDS = new Set(["evet", "onayla", "kabul", "tamam", "olur"]);
const REJECT_WORDS = new Set(["hayir", "reddet", "ret", "iptal", "olmaz"]);

/** Çekirdeğin onay kartı seçenek değerleri (bkz. dialogs/Approval.tsx): "once"/"session" olumlu, "deny" olumsuz. */
const ACCEPT_OPTION_VALUES = new Set(["once", "session", "allow"]);
const REJECT_OPTION_VALUES = new Set(["deny"]);

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
  const values = family === ACCEPT_WORDS ? ACCEPT_OPTION_VALUES : REJECT_OPTION_VALUES;
  const semantic = ask.secenekler.filter((option) =>
    [option.deger, option.etiket].some((value) => family.has(normalizeSpeech(value)))
    || values.has(normalizeSpeech(option.deger)),
  );
  if (semantic.length === 1) return semantic[0].deger;
  // Çekirdek izin kartı "once" (bir kez) ve "session" (bu oturumda) sunar; kalıcı genişlikteki izin
  // sesli "evet"ten çıkmaz: yalnızca en dar olumlu seçenek ("once") seçilir. (U2-15)
  if (family === ACCEPT_WORDS) {
    const once = semantic.filter((option) => normalizeSpeech(option.deger) === "once");
    if (once.length === 1) return once[0].deger;
  }
  return null;
}

interface VoiceWindowProps {
  /** Kabul koşularında eski sürekli konuşma senaryolarını ayrıca sınamak için. */
  wakeEnabled?: boolean;
  /** Sürekli dinleme: istek gönderilince mikrofon kapanmaz. Varsayılan kapalı (tek komut, tek basış). */
  continuous?: boolean;
  /** Mikrofon açıkken sessizlikte kendiliğinden kapanma süresi (ms); testler kısaltır. */
  idleEndMs?: number;
  /** Boşta bitiş denetim aralığı (ms). */
  idleCheckMs?: number;
  /** Düşünme zaman aşımı (ms); testler kısaltır. */
  thinkingTimeoutMs?: number;
  /** Tercih isteğini yeniden deneme aralığı (ms); testler kısaltır. */
  prefsRetryMs?: number;
  /** Beklenmedik çökme sonrası yeniden deneme tabanı (ms); testler kısaltır. */
  restartBaseMs?: number;
  permissionBridge?: PermissionBridge;
  runtime?: VoiceWindowRuntime;
}

const INJECTED_RUNTIME_PERMISSION_BRIDGE: PermissionBridge = {
  request: async () => "granted",
  openSettings: async () => undefined,
};

/** Ayrı, hafif Talk penceresi; ana pencerenin aynı aktif sohbetini kullanır. */
export function VoiceWindow(props: VoiceWindowProps = {}) {
  const awakeUntil = useRef(0);
  const wakeAcknowledgedTurn = useRef<string | null>(null);
  const systemRecognitionBlocked = useRef(false);
  const wakeEnabled = props.wakeEnabled ?? true;
  const baseRuntime = props.runtime ?? DEFAULT_RUNTIME;
  const permissionBridge = props.permissionBridge
    ?? (props.runtime ? INJECTED_RUNTIME_PERMISSION_BRIDGE : nativePermissionBridge);
  const permissions = usePermissions(permissionBridge);
  const permissionAwareRuntime = useMemo<VoiceWindowRuntime>(() => ({
    ...baseRuntime,
    preflightRecognition: async () => {
      if (!(await permissions.ensure("microphone"))) return false;
      if (!(await permissions.ensure("speech"))) return false;
      return baseRuntime.preflightRecognition();
    },
  }), [baseRuntime, permissions.ensure]);
  const runtime = permissionAwareRuntime;
  const [machine, dispatch] = useReducer(voiceMachine, initialVoiceMachine);
  const initialGeometry = useRef(readVoiceGeometry(window.localStorage));
  const geometryRef = useRef(initialGeometry.current);
  const [wide, setWide] = useState(initialGeometry.current.wide);
  const [onTop, setOnTop] = useState(initialGeometry.current.onTop);
  const [prefs, setPrefs] = useState<VoicePrefs>({ hiz: 1 });
  // OTURUM: kullanıcı başlatana kadar mikrofon kapalıdır. Varsayılan (tek komut) modda söz
  // gönderilince oturum kapanır; `continuous` modda oturum açıkken sürekli dinlenir.
  const [sessionOpen, setSessionOpen] = useState(false);
  const sessionOpenRef = useRef(false);
  const lastActivity = useRef(Date.now());
  // Tanı izi: konuşma sorun çıkarırsa kullanıcı sağ tık → "Tanı bilgisi"nden son adımları görür.
  const traceLines = useRef<string[]>([]);
  const [traceVersion, setTraceVersion] = useState(0);
  const trace = useCallback((text: string) => {
    const stamp = new Date().toLocaleTimeString("tr-TR");
    traceLines.current = [...traceLines.current.slice(-39), `${stamp} ${text}`];
    setTraceVersion((value) => value + 1);
  }, []);
  const [ask, setAsk] = useState<VoiceAsk | null>(null);
  const [recognitionOwned, setRecognitionOwned] = useState(false);
  const machineRef = useRef(machine);
  const askRef = useRef(ask);
  const answering = useRef<VoiceAsk | null>(null);
  /** Açık sorunun pencereye ulaştığı an; sesli cevabın ömrü buradan sayılır. */
  const askOpenedAt = useRef(0);
  const [answerPending, setAnswerPending] = useState(false);
  const spokenQuestion = useRef<{ session: number; segment: number; question: VoiceAsk | null } | null>(null);
  const sentRevision = useRef(0);
  const activeSession = useRef(0);
  const nextSession = useRef(0);
  const recognitionIntent = useRef(0);
  const startingIntent = useRef<number | null>(null);
  const pendingRecognitionEvents = useRef<PendingRecognitionEvent[]>([]);
  const bargeInPending = useRef(false);
  /** Kullanıcı sözü kestiğinde Fusion'ın o ana kadar söylediği metin. */
  const kesilenCevap = useRef<string | null>(null);
  const bargeInEvents = useRef<RecognitionPayload[]>([]);
  const replayRecognitionEvent = useRef<((event: PendingRecognitionEvent) => void) | null>(null);
  /** TTS iptali doğrulanamadığında (hata durumu ya da `interruptSpeech` reddi) tamponu atıp dinlemeyi geri getirir. */
  const bargeInBasarisiz = useRef<(() => void) | null>(null);
  const finalizedSession = useRef<number | null>(null);
  const finalizedSegment = useRef(0);
  const latestRecognitionSegment = useRef(0);
  const expectedRecognitionEnd = useRef<number | null>(null);
  const restartAfterRecognitionEndSession = useRef<number | null>(null);
  /** Ard arda beklenmedik çökme sayısı; geri çekilme buna göre büyür. */
  const ardArdaCokme = useRef(0);
  /** Bu oturum bir final üretti mi? Geri çekilme kararı buna bakar. */
  const oturumVerimliydi = useRef(false);
  /** Talk kapanıyor mu? Kapanışta yeniden başlatma yapılmaz. */
  const kapaniyor = useRef(false);
  const yenidenBaslatmaZamani = useRef<number | null>(null);
  const syntheticRestartSession = useRef<number | null>(null);
  const partialFinalTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const recognitionQueue = useRef<Promise<void>>(Promise.resolve());
  machineRef.current = machine;
  askRef.current = ask;

  const sendAnswer = useCallback((answer: string, question: VoiceAsk | null) => {
    if (!question || answering.current === question || askRef.current !== question) return;
    // Cevap yalnız kimliği belli ve taze soruya gider; aksi halde çekirdek zaten yok sayardı,
    // kullanıcı ise "cevap gitti" sanırdı.
    if (!question.sessionId || !question.questionId) {
      dispatch({ type: "FAILED", text: "Bu soru sesle cevaplanamaz. Karttan seç." });
      return;
    }
    if (Date.now() - askOpenedAt.current > ONAY_SORUSU_OMRU_MS) {
      dispatch({ type: "FAILED", text: "Soru çok eskidi. Karttan seç." });
      return;
    }
    answering.current = question;
    setAnswerPending(true);
    void runtime.answerAsk(answer, question).catch(() => {
      if (askRef.current !== question) return;
      answering.current = null;
      setAnswerPending(false);
      dispatch({ type: "FAILED", text: "Cevap gönderilemedi. Karttan yeniden deneyebilirsin." });
    });
  }, [runtime]);

  const queueRecognition = useCallback(<T,>(operation: () => Promise<T>) => {
    const queued = recognitionQueue.current.then(operation, operation);
    recognitionQueue.current = queued.then(() => undefined, () => undefined);
    return queued;
  }, []);

  const acknowledgeListening = useCallback((session: number, segment: number) => {
    awakeUntil.current = Date.now() + 30_000;
    const turn = `${session}:${segment}`;
    if (wakeAcknowledgedTurn.current === turn) return;
    wakeAcknowledgedTurn.current = turn;
    // Uyandırma "Hm"i yalnız bir geri bildirimdir: çalınamazsa kullanıcının konuşmasını (aday sözü)
    // silen hata kartı ÇIKMAZ, yalnız tanı izine yazılır. (Ölçüldü, 29 Ekim, U2-16.)
    try { acknowledgeWake((text) => { if (!kapaniyor.current) trace(text); }); }
    catch (error) { trace(String(error)); }
  }, [trace]);

  const clearPartialFinalTimer = useCallback(() => {
    if (partialFinalTimer.current !== null) clearTimeout(partialFinalTimer.current);
    partialFinalTimer.current = null;
  }, []);

  const startListening = useCallback(async () => {
    systemRecognitionBlocked.current = false;
    spokenQuestion.current = null;
    clearPartialFinalTimer();
    syntheticRestartSession.current = null;
    restartAfterRecognitionEndSession.current = null;
    setRecognitionOwned(true);
    const previousSession = activeSession.current;
    activeSession.current = 0;
    finalizedSession.current = null;
    finalizedSegment.current = 0;
    latestRecognitionSegment.current = 0;
    expectedRecognitionEnd.current = previousSession || null;
    const intent = recognitionIntent.current + 1;
    recognitionIntent.current = intent;
    const requestedSession = nextSession.current + 1;
    const keepOpen = (sessionOpenRef.current ) || askRef.current !== null;
    dispatch({ type: "START_LISTENING", session: requestedSession, continuous: keepOpen });
    try {
      const permitted = await runtime.preflightRecognition();
      trace(`izin denetimi: ${permitted ? "tamam" : "verilmedi"}`);
      if (recognitionIntent.current !== intent) return;
      if (!permitted) {
        setRecognitionOwned(false);
        sessionOpenRef.current = false;
        setSessionOpen(false);
        dispatch({ type: "FAILED", text: "Mikrofon izni verilmedi. İzin verdikten sonra yeniden deneyin." });
        return;
      }
      const session = await queueRecognition(async () => {
        if (recognitionIntent.current !== intent) return null;
        if (previousSession) await runtime.stopRecognition();
        if (recognitionIntent.current !== intent) return null;
        startingIntent.current = intent;
        const started = await runtime.startRecognition();
        return typeof started === "number" ? started : requestedSession;
      });
      if (startingIntent.current === intent) startingIntent.current = null;
      trace(`tanıma başlatıldı (oturum ${String(session)})`);
      if (session === null || recognitionIntent.current !== intent) return;
      nextSession.current = Math.max(nextSession.current, session);
      activeSession.current = session;
      finalizedSession.current = null;
      finalizedSegment.current = 0;
      latestRecognitionSegment.current = 0;
      expectedRecognitionEnd.current = null;
      dispatch({ type: "START_LISTENING", session, continuous: keepOpen });
      const pending = pendingRecognitionEvents.current;
      pendingRecognitionEvents.current = [];
      pending.forEach((event) => {
        if (event.payload.session === session) replayRecognitionEvent.current?.(event);
      });
      if (cuesEnabled()) playCue("listen-start");
    } catch (reason) {
      setRecognitionOwned(false);
      // Ölçüldü (29 Ekim, U2-08): başlatma hatasında oturum "açık" kalıyor, karakter "Mikrofon açık"
      // diyor ve bir sonraki tık oturumu KAPATIYORDU; bayat başlatma niyeti de olay biriktiriyordu.
      if (recognitionIntent.current === intent) {
        sessionOpenRef.current = false;
        setSessionOpen(false);
        if (startingIntent.current === intent) startingIntent.current = null;
        pendingRecognitionEvents.current = [];
      }
      trace(`başlatma hatası: ${String(reason)}`);
      dispatch({ type: "FAILED", text: `Konuşma tanıma başlatılamadı: ${String(reason)}` });
    }
  }, [clearPartialFinalTimer, queueRecognition, runtime]);

  /**
   * Dinlemeyi yeniden başlat — TEK yol.
   *
   * Sürekli dinlemede her oturum bitişi yeniden başlatma gerektirir, ama bunu
   * koşulsuz yapmak sıkı bir döngü üretir: süreç açılır açılmaz biterse
   * uygulama sonsuza kadar yeniden başlatır (ölçüldü: testlerde bellek
   * tükendi). Ard arda HIZLI bitişte gecikme büyür; sağlıklı bir oturumdan
   * sonraki bitiş ise anında toparlanır.
   */
  const dinlemeyiSurdur = useCallback(() => {
    if (kapaniyor.current) return;
    const oturumDinliyor = sessionOpenRef.current ;
    if (!oturumDinliyor && askRef.current === null) {
      // Oturum yok ya da sessizde: mikrofon kendiliğinden geri açılmaz.
      setRecognitionOwned(false);
      dispatch({ type: "STOPPED" });
      return;
    }
    // Geri çekilme SÜREYE değil VERİMLİLİĞE bakar. Final üretmiş bir oturum
    // sağlıklıdır, milisaniyeler sürmüş olsa bile; onu "hızlı çöküş" saymak
    // sağlıklı konuşma turlarını da geciktirirdi.
    const verimliydi = oturumVerimliydi.current;
    oturumVerimliydi.current = false;
    ardArdaCokme.current = verimliydi ? 0 : ardArdaCokme.current + 1;
    const karar = yenidenBaslatmaKarari(ardArdaCokme.current, props.restartBaseMs);
    if (karar.vazgec) {
      ardArdaCokme.current = 0;
      sessionOpenRef.current = false;
      setSessionOpen(false);
      setRecognitionOwned(false);
      dispatch({ type: "FAILED", text: "Konuşma tanıma çalışmıyor. Sistem ayarlarını ve bağlantını kontrol edip karaktere yeniden dokun." });
      return;
    }
    const gecikme = karar.gecikmeMs;
    window.clearTimeout(yenidenBaslatmaZamani.current ?? undefined);
    yenidenBaslatmaZamani.current = window.setTimeout(() => {
      if (activeSession.current === 0 && !kapaniyor.current) void startListening();
    }, gecikme);
  }, [props.restartBaseMs, startListening]);

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
      const current = askRef.current;
      if (open?.sessionId && open.questionId && current?.sessionId === open.sessionId
        && current.questionId === open.questionId) return;
      clearPartialFinalTimer();
      askRef.current = open;
      askOpenedAt.current = Date.now();
      answering.current = null;
      setAnswerPending(false);
      setAsk(open);
      dispatch({ type: open ? "ASK_OPENED" : "ASK_CLOSED" });
      if (open && activeSession.current === 0) {
        void startListening();
      }
    });
    return () => { void remove.then((unlisten) => unlisten()).catch(() => undefined); };
  }, [clearPartialFinalTimer, runtime, startListening]);

  useEffect(() => {
    // Ana pencere dinleyicisi henüz kurulmamışsa ilk istek cevapsız kalır; Talk varsayılan hızla açık
    // kalıp ilk değişiklikte gerçek tercihin üzerine yazardı. Cevap gelene dek sınırlı yeniden denenir (U2-47).
    let received = false;
    let tries = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const remove = runtime.onPrefs((incoming) => { received = true; setPrefs(incoming); });
    const ask = () => {
      void runtime.requestPrefs(null).catch(() => undefined);
      tries += 1;
      if (tries < TERCIH_ISTEK_DENEME) timer = setTimeout(() => { if (!received) ask(); }, props.prefsRetryMs ?? TERCIH_ISTEK_ARALIGI_MS);
    };
    ask();
    return () => { clearTimeout(timer); void remove.then((unlisten) => unlisten()).catch(() => undefined); };
  }, [props.prefsRetryMs, runtime]);

  useEffect(() => {
    // StrictMode ya da bağımlılık değişimiyle efekt yeniden kurulurken önceki temizlikte kalan bayrak
    // `dinlemeyiSurdur`u sonsuza dek devre dışı bırakıyordu (U2-18).
    kapaniyor.current = false;
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
      let line: RecognitionEvent;
      try {
        line = JSON.parse(payload.line) as RecognitionEvent;
      } catch {
        return;
      }
      trace(`olay ${String(line?.tur)} "${String(line?.metin ?? "").slice(0, 24)}"`);
      if (!line || typeof line.metin !== "string" || typeof line.speech_ms !== "number"
        || typeof line.segment !== "number" || (line.guven !== null && typeof line.guven !== "number")) return;
      if (line.tur === "kismi" || line.tur === "son") {
        lastActivity.current = Date.now();
        if (line.segment <= finalizedSegment.current || line.segment < latestRecognitionSegment.current) return;
        latestRecognitionSegment.current = line.segment;
      }
      if (line.tur === "hata" && diktePasifMi(line)) {
        systemRecognitionBlocked.current = true;
        // Mikrofon çalışamıyorsa oturum "açık" görünmemeli; kullanıcı düzeltince yeniden başlatır.
        sessionOpenRef.current = false;
        setSessionOpen(false);
        dispatch({ type: "FAILED", text: speechFailureText(line.metin, line.kod) });
        return;
      }
      if (line.tur === "ses-basladi" || line.tur === "kismi") {
        const previous = spokenQuestion.current;
        if (!previous || previous.session !== payload.session || previous.segment !== line.segment) {
          spokenQuestion.current = { session: payload.session, segment: line.segment, question: askRef.current };
        }
      }
      if ((line.tur === "son" || line.tur === "kismi") && spokenQuestion.current?.session === payload.session
        && spokenQuestion.current.segment === line.segment && spokenQuestion.current.question !== askRef.current) {
        restartAfterRecognitionEndSession.current = payload.session;
        return;
      }
      // Yankı ayıklama: mikrofon sürekli açık olduğu için Fusion konuşurken
      // kendi sesini duyar. macOS'un ses işleme motoru büyük kısmını siler
      // ama hoparlörün akustik kuyruğu geçebiliyor; seslendirilen metinle
      // örtüşen söz kullanıcının sözü sayılmaz.
      if (
        (line.tur === "kismi" || line.tur === "son")
        && machineRef.current.speaking
        && (yankiMi(line.metin, machineRef.current.transcript)
          || (askRef.current !== null
            && cevapYankisiMi(line.metin, `${machineRef.current.transcript ?? ""} ${askRef.current.metin}`)))
      ) {
        return;
      }
      const textual = line.tur === "kismi" || line.tur === "son";
      const interruptWord = normalizeSpeech(line.metin);
      const hasInterruptMeaning = textual && (line.metin.trim().split(/\s+/u).length >= 2
        || ["dur", "sus", "bekle"].includes(interruptWord)
        || routeWakeSpeech(line.metin, false).acknowledge
        || (askRef.current && matchSpokenAnswer(line.metin, askRef.current) !== null));
      const trustedInterrupt = hasInterruptMeaning && evaluateRecognitionTurn({
        activeSession: activeSession.current, candidateRevision: 0, requestedRevision: 0,
        event: { ...line, tur: "son" }, session: payload.session, timedOut: false,
      }) === "accept";
      const mayInterrupt = trustedInterrupt && (!wakeEnabled || Date.now() < awakeUntil.current
        || routeWakeSpeech(line.metin, false).awake);
      if (machineRef.current.speaking && !mayInterrupt
        && (line.tur === "ses-basladi" || textual)) return;
      if (!bargeInPending.current && machineRef.current.speaking && mayInterrupt) {
        bargeInPending.current = true;
        // Fusion'ın yarım kalan cevabı SAKLANIR: modele "sözüm burada kesildi"
        // bilgisi gitmezse kullanıcının düzeltmesi bağlamsız kalır.
        // `talking` evresinde `transcript`, Fusion'ın seslendirdiği metindir.
        kesilenCevap.current = machineRef.current.transcript?.trim() || null;
        bargeInEvents.current.push(payload);
        // Reddedilen iptal durum olayı üretmez; kilit sonsuza kalmasın.
        void runtime.interruptSpeech().catch(() => bargeInBasarisiz.current?.());
        return;
      }
      if (bargeInPending.current) {
        bargeInEvents.current.push(payload);
        return;
      }
      if (line.tur === "hata") {
        expectedRecognitionEnd.current = payload.session;
        dispatch({ type: "FAILED", text: line.metin });
      } else if (line.tur === "kismi") {
        const wake = routeWakeSpeech(line.metin, false);
        if (wakeEnabled && wake.acknowledge && !wake.message && evaluateRecognitionTurn({
          activeSession: activeSession.current, candidateRevision: 0, requestedRevision: 0,
          event: { ...line, tur: "son" }, session: payload.session, timedOut: false,
        }) === "accept") acknowledgeListening(payload.session, line.segment);
        const candidateRevision = machineRef.current.candidateRevision + 1;
        if (!askRef.current) dispatch({ type: "RECOGNITION", session: payload.session, event: line });
        clearPartialFinalTimer();
        const askAtPartial = askRef.current;
        partialFinalTimer.current = setTimeout(() => {
          partialFinalTimer.current = null;
          if (payload.session !== activeSession.current || (finalizedSession.current === payload.session && line.segment <= finalizedSegment.current)) return;
          if (askRef.current !== askAtPartial) return;
          const decision = evaluateRecognitionTurn({
            activeSession: activeSession.current,
            candidateRevision: askAtPartial ? candidateRevision : machineRef.current.candidateRevision,
            event: line,
            requestedRevision: candidateRevision,
            session: payload.session,
            timedOut: true,
          });
          if (decision !== "accept") return;
          finalizedSession.current = payload.session;
          finalizedSegment.current = line.segment;
          expectedRecognitionEnd.current = payload.session;
          const openAsk = askAtPartial;
          const answer = openAsk ? matchSpokenAnswer(line.metin, openAsk) : null;
          if (answer) {
            sendAnswer(answer, openAsk);
          } else if (openAsk) {
            restartAfterRecognitionEndSession.current = null;
            syntheticRestartSession.current = payload.session;
          } else {
            dispatch({ type: "EVALUATE_TIMEOUT", session: payload.session, candidateRevision });
          }
          void queueRecognition(() => runtime.stopRecognition())
            .then(() => {
              if (syntheticRestartSession.current !== payload.session) return;
              syntheticRestartSession.current = null;
              activeSession.current = 0;
              expectedRecognitionEnd.current = null;
              void startListening();
            })
            .catch((reason) => {
              dispatch({ type: "FAILED", text: `Konuşma tanıma durdurulamadı: ${String(reason)}` });
            });
        }, PARTIAL_FINAL_DELAY_MS);
      } else if (line.tur === "son") {
        if (!askRef.current) line = reconcileRecognition(machineRef.current.candidate, line);
        clearPartialFinalTimer();
        if (finalizedSession.current === payload.session && line.segment <= finalizedSegment.current) return;
        const candidateRevision = machineRef.current.candidateRevision + 1;
        const decision = evaluateRecognitionTurn({
          activeSession: activeSession.current,
          candidateRevision,
          event: line,
          requestedRevision: candidateRevision,
          session: payload.session,
          timedOut: false,
        });
        if (decision !== "accept") {
          if (decision === "reject") {
            // Reddedilen (düşük güvenli/kısa) final de beklenen bitiştir: yardımcı finalden sonra çıkar,
            // "beklenmedik kapandı" hatası çıkmasın ve tanıyıcı çalıştığı için geri çekilme büyümesin (U2-11).
            expectedRecognitionEnd.current = payload.session;
            oturumVerimliydi.current = true;
          }
          if (!askRef.current) dispatch({ type: "RECOGNITION", session: payload.session, event: line });
          return;
        }
        finalizedSession.current = payload.session;
        finalizedSegment.current = line.segment;
        expectedRecognitionEnd.current = payload.session;
        const openAsk = askRef.current;
        const answer = openAsk ? matchSpokenAnswer(line.metin, openAsk) : null;
        if (answer) {
          sendAnswer(answer, openAsk);
        } else if (openAsk) {
          // Fail-closed: belirsiz söz ne onaydır ne de yeni sohbet turu.
          // Yardımcı finalden sonra çıktığı için bitiş olayında yeniden dinle.
          restartAfterRecognitionEndSession.current = payload.session;
        } else {
          dispatch({ type: "RECOGNITION", session: payload.session, event: line });
        }
      } else {
        dispatch({ type: "RECOGNITION", session: payload.session, event: line });
      }
    };
    const handleEnded = ({ session, reason }: RecognitionEndedPayload) => {
      trace(`tanıma bitti (oturum ${session}) ${reason ?? ""}`);
      if (session !== activeSession.current) {
        if (activeSession.current === 0 && startingIntent.current !== null) {
          pendingRecognitionEvents.current.push({ type: "ended", payload: { session, reason } });
        }
        return;
      }
      clearPartialFinalTimer();
      if (systemRecognitionBlocked.current) {
        activeSession.current = 0;
        expectedRecognitionEnd.current = null;
        setRecognitionOwned(false);
        return;
      }
      if (syntheticRestartSession.current === session) {
        syntheticRestartSession.current = null;
        activeSession.current = 0;
        expectedRecognitionEnd.current = null;
        void startListening();
        return;
      }
      if (restartAfterRecognitionEndSession.current === session) {
        restartAfterRecognitionEndSession.current = null;
        setRecognitionOwned(false);
        activeSession.current = 0;
        expectedRecognitionEnd.current = null;
        void startListening();
        return;
      }
      if (expectedRecognitionEnd.current === session) {
        expectedRecognitionEnd.current = null;
        setRecognitionOwned(false);
        activeSession.current = 0;
        // Beklenen bitiş de dinlemeyi SONLANDIRMAZ. Talk açıkken mikrofon
        // sürekli açıktır; eskiden kullanıcı tuşa basarak yeniden başlatıyordu,
        // tuş kaldırıldığı için bunu uygulama yapar.
        dinlemeyiSurdur();
        return;
      }
      activeSession.current = 0;
      setRecognitionOwned(false);
      dispatch({
        type: "FAILED",
        text: reason || "Konuşma tanıma beklenmedik şekilde kapandı.",
      });
      // Mikrofon tuşu KALDIRILDI: kullanıcı elle yeniden başlatamaz. Beklenmedik
      // çıkışta dinleme kendiliğinden toparlanmalı, yoksa Talk sessizce ölür.
      // Ard arda çökmede geri çekilme uygulanır; sıkı döngü hem işlemciyi hem
      // günlüğü boğardı.
      dinlemeyiSurdur();
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
      // Dinleyiciler yeniden kurulduysa (izin/çalışma zamanı değişti) açık oturumun dinlemesini
      // geri getir; oturum yoksa mikrofon KAPALI kalır.
      if (sessionOpenRef.current ) void startListening();
    }).catch((reason) => {
      if (alive) dispatch({ type: "FAILED", text: String(reason) });
    });
    return () => {
      alive = false;
      recognitionIntent.current += 1;
      startingIntent.current = null;
      pendingRecognitionEvents.current = [];
      bargeInPending.current = false;
      bargeInEvents.current = [];
      clearPartialFinalTimer();
      syntheticRestartSession.current = null;
      restartAfterRecognitionEndSession.current = null;
      replayRecognitionEvent.current = null;
      removeRecognition?.();
      removeEnded?.();
      kapaniyor.current = true;
      window.clearTimeout(yenidenBaslatmaZamani.current ?? undefined);
      expectedRecognitionEnd.current = activeSession.current || null;
      activeSession.current = 0;
      setRecognitionOwned(false);
      void queueRecognition(() => runtime.stopRecognition()).catch(() => undefined);
    };
  }, [acknowledgeListening, clearPartialFinalTimer, queueRecognition, runtime, startListening, wakeEnabled]);

  const closeMic = useCallback(() => {
    clearPartialFinalTimer();
    window.clearTimeout(yenidenBaslatmaZamani.current ?? undefined);
    recognitionIntent.current += 1;
    startingIntent.current = null;
    pendingRecognitionEvents.current = [];
    expectedRecognitionEnd.current = activeSession.current || null;
    activeSession.current = 0;
    setRecognitionOwned(false);
    return queueRecognition(() => runtime.stopRecognition()).catch(() => undefined);
  }, [clearPartialFinalTimer, queueRecognition, runtime]);

  /**
   * İstek tam algılandı ve gönderildi: mikrofon kapanır (Fusion'ın kendi sesini dinlemesin),
   * düşünme/cevap akışı sürer. Yeni komut için karaktere yeniden basılır.
   */
  const finishRequest = useCallback(() => {
    if (props.continuous === true) return;
    sessionOpenRef.current = false;
    setSessionOpen(false);
    dispatch({ type: "REQUEST_SENT" });
    void closeMic();
  }, [closeMic, props.continuous]);

  useEffect(() => {
    if (machine.finalRevision <= sentRevision.current || !machine.finalText) return;
    sentRevision.current = machine.finalRevision;
    oturumVerimliydi.current = true;
    // Oturumu kullanıcı başlattıysa söz doğrudan sohbet turudur; ad ("Fusion") şartı yalnız oturum dışında/uyku sınırında aranır.
    const routed = routeWakeSpeech(machine.finalText, !wakeEnabled || sessionOpenRef.current || Date.now() < awakeUntil.current);
    if (routed.acknowledge) acknowledgeListening(machine.session, machine.finalizedSegment ?? 0);
    if (!routed.message) { dispatch({ type: "ASSISTANT_FINISHED" }); return; }
    awakeUntil.current = Date.now() + 30_000;
    if (cuesEnabled()) playCue("thinking");
    const kesilen = kesilenCevap.current;
    kesilenCevap.current = null;
    // Gönderim reddedilirse söz sessizce kaybolmaz: hata gösterilir (U2-06).
    void Promise.resolve(runtime.emitMessage({
      kaynak: "kullanici",
      metin: routed.message,
      ...(kesilen ? { kesilen } : {}),
    })).catch(() => dispatch({ type: "FAILED", text: "Söz ana pencereye iletilemedi. Karaktere dokunup yeniden söyle." }));
    finishRequest();
  }, [finishRequest, acknowledgeListening, machine.finalRevision, machine.finalText, machine.finalizedSegment, machine.session, runtime, wakeEnabled]);

  useEffect(() => {
    bargeInBasarisiz.current = () => {
      if (!bargeInPending.current) return;
      // Tampon BİLEREK atılır: TTS iptali doğrulanmadan yakalanan ses
      // Fusion'ın kendi sesini içerebilir ve onu kullanıcının sözü sanmak
      // daha kötüdür. Kullanıcı tekrar konuşunca taze tur kabul edilir.
      bargeInPending.current = false;
      bargeInEvents.current = [];
      kesilenCevap.current = null;
      recognitionIntent.current += 1;
      startingIntent.current = null;
      pendingRecognitionEvents.current = [];
      expectedRecognitionEnd.current = activeSession.current || null;
      activeSession.current = 0;
      setRecognitionOwned(false);
      void queueRecognition(() => runtime.stopRecognition())
        // Bayat tampon atıldıktan sonra dinleme GERİ GELMELİ; sürekli
        // dinlemede kullanıcının basacağı bir tuş yok.
        .then(() => dinlemeyiSurdur())
        .catch(() => undefined);
    };
    const remove = runtime.onRuntimeState((incoming) => {
      if (incoming.durum === "error") {
        answering.current = null;
        setAnswerPending(false);
      }
      if (incoming.durum === "talking") {
        bargeInPending.current = false;
        bargeInEvents.current = [];
        // Yavaş modelde düşünme+sentez 30 sn'yi aşabilir; konuşma başlarken uyanıklık tazelenir (U2-13).
        if (awakeUntil.current > 0) awakeUntil.current = Date.now() + 30_000;
        dispatch({ type: "ASSISTANT_STARTED", text: incoming.metin });
        return;
      }
      if (incoming.durum === "interrupted") {
        const buffered = bargeInEvents.current;
        bargeInEvents.current = [];
        bargeInPending.current = false;
        dispatch({ type: "ASSISTANT_FINISHED" });
        setTimeout(() => buffered.forEach((payload) => {
          replayRecognitionEvent.current?.({ type: "output", payload });
        }), 0);
        return;
      }
      if (incoming.durum === "listening" || incoming.durum === "idle") {
        // Ölçüldü (29 Ekim, U2-01): iptal onayı (`interrupted`) gelmeden TTS doğal biterse bayrak
        // açık kalır ve sonraki tüm tanıma olayları yutulurdu. Cevap kesilmeden bittiği için
        // `kesilen` bağlamı yanlış olur; tamponlanan söz kullanıcının sözüdür, yeniden oynatılır.
        const bekleyen = bargeInPending.current ? bargeInEvents.current : null;
        bargeInPending.current = false;
        bargeInEvents.current = [];
        if (bekleyen) {
          kesilenCevap.current = null;
          setTimeout(() => bekleyen.forEach((payload) => {
            replayRecognitionEvent.current?.({ type: "output", payload });
          }), 0);
        }
        if (awakeUntil.current > 0) awakeUntil.current = Date.now() + 30_000;
        lastActivity.current = Date.now();
        const shouldResume = machineRef.current.autoListen
          && ((sessionOpenRef.current ) || askRef.current !== null);
        dispatch({ type: "ASSISTANT_FINISHED" });
        if (shouldResume && activeSession.current === 0) void startListening();
      } else if (incoming.durum === "error") {
        bargeInBasarisiz.current?.();
        dispatch({ type: "FAILED", text: incoming.metin ?? "Sesli yanıt tamamlanamadı." });
      }
    });
    return () => { void remove.then((unlisten) => unlisten()).catch(() => undefined); };
  }, [dinlemeyiSurdur, queueRecognition, runtime, startListening]);

  useEffect(() => {
    document.body.style.background = "transparent";
    document.body.style.overflow = "hidden";
  }, []);

  const startSession = useCallback(() => {
    sessionOpenRef.current = true;
    setSessionOpen(true);
    lastActivity.current = Date.now();
    void startListening();
  }, [startListening]);

  /** Mikrofonu kapat ve oturumu bitir. `silence=true` ise Fusion'ın konuşması da kesilir. */
  const endSession = useCallback((silence = true) => {
    sessionOpenRef.current = false;
    setSessionOpen(false);
    if (silence) void runtime.interruptSpeech().catch(() => undefined);
    void closeMic();
    dispatch({ type: "STOPPED" });
  }, [closeMic, runtime]);

  /** Karaktere basış: konuşuyorsa söz keser; mikrofon açıksa kapatır; kapalıysa açar. */
  const toggleListening = useCallback(() => {
    if (machineRef.current.speaking) {
      void runtime.interruptSpeech().catch(() => undefined);
      return;
    }
    if (sessionOpenRef.current) endSession(false);
    else startSession();
  }, [endSession, runtime, startSession]);

  // Model düşünürken kullanıcı "takıldı mı?" diye merak etmesin: kısa bir "Hmm" duyulur.
  // Ölçüldü (29 Ekim, U2-03): koşul `sessionOpen`e de bağlıydı; tek komut modunda istek gidince oturum
  // kapandığı için ipucu hiç çalmıyordu. Düşünme fazı oturumdan bağımsızdır.
  useEffect(() => {
    if (machine.phase !== "thinking") return;
    let stopped = false;
    let timer: number | undefined;
    const cue = () => {
      if (stopped) return;
      try { speakThinkingCue(); } catch { /* ipucu sesi isteğe bağlıdır; cevabı engellemez */ }
      timer = window.setTimeout(cue, DUSUNME_IPUCU_TEKRAR_MS);
    };
    timer = window.setTimeout(cue, DUSUNME_IPUCU_GECIKME_MS);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      cancelThinkingCue();
    };
  }, [machine.phase]);

  // Düşünme fazı sonsuza kadar sürmesin (U2-05): ana pencere hiç durum yayınlamazsa kullanıcıya söyle.
  useEffect(() => {
    if (machine.phase !== "thinking") return;
    const timer = window.setTimeout(
      () => dispatch({ type: "FAILED", text: "Yanıt gelmedi. Karaktere dokunup yeniden dene." }),
      props.thinkingTimeoutMs ?? DUSUNME_ZAMAN_ASIMI_MS,
    );
    return () => window.clearTimeout(timer);
  }, [machine.phase, props.thinkingTimeoutMs]);

  // Uzun sessizlikte oturum kendiliğinden biter; mikrofon sonsuza dek açık kalmaz.
  useEffect(() => {
    const limit = props.idleEndMs ?? OTURUM_BOSTA_BITIS_MS;
    const timer = window.setInterval(() => {
      if (!sessionOpenRef.current || askRef.current !== null) return;
      if (Date.now() - lastActivity.current > limit) endSession(false);
    }, props.idleCheckMs ?? OTURUM_KONTROL_ARALIGI_MS);
    return () => window.clearInterval(timer);
  }, [endSession, props.idleCheckMs, props.idleEndMs]);

  const visibleTranscript = machine.error
    ? speechFailureText(machine.error)
    : machine.partial || machine.transcript;
  return (
    <>
    <VoiceMode
      ask={ask}
      listening={recognitionOwned}
      onListen={toggleListening}
      onInterrupt={() => void runtime.interruptSpeech().catch(() => undefined)}
      diagnostics={traceVersion >= 0 ? traceLines.current : []}
      sessionOpen={sessionOpen}
      answerPending={answerPending}
      onAnswer={(answer) => sendAnswer(answer, ask)}
      onClose={() => void runtime.close()}
      onMinimize={() => void minimizeVoiceWindow()}
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
      state={machine.phase}
      transcript={visibleTranscript}
      wide={wide}
    />
    {permissions.activeKind && (
      <PermissionPrompt
        canOpenSettings={hasSettingsLink(permissions.activeKind)}
        error={permissions.error}
        isRequesting={permissions.isRequesting}
        kind={permissions.activeKind}
        phase={permissions.phase}
        onContinue={() => void permissions.continue()}
        onContinueToNext={permissions.hasQueuedPermission ? permissions.continueToNext : undefined}
        onDismiss={permissions.dismiss}
        onOpenSettings={() => void permissions.openSettings(permissions.activeKind!)}
        onRetry={() => void permissions.retry()}
      />
    )}
    </>
  );
}
