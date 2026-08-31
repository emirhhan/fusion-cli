export type RecognitionEvent = {
  tur: "hazir" | "ses-basladi" | "kismi" | "son" | "ses-bitti" | "hata";
  metin: string;
  guven: number | null;
  speech_ms: number;
  segment: number;
};

export type VoicePhase =
  | "idle"
  | "calibrating"
  | "listening"
  | "hearing"
  | "transcribing"
  | "thinking"
  | "talking"
  | "approval"
  | "interrupted"
  | "error";

export interface VoiceMachineState {
  autoListen: boolean;
  candidate: RecognitionEvent | null;
  candidateRevision: number;
  error: string | null;
  finalizedSession: number | null;
  finalRevision: number;
  finalText: string | null;
  lastFinal: string | null;
  partial: string;
  phase: VoicePhase;
  phaseBeforeAsk: VoicePhase | null;
  session: number;
  transcript: string;
}

export interface RecognitionTurn {
  activeSession: number;
  candidateRevision: number;
  event: RecognitionEvent;
  requestedRevision: number;
  session: number;
  timedOut: boolean;
}

export type RecognitionDecision = "wait" | "accept" | "reject";

const MINIMUM_CONFIDENCE = 0.2;
const MINIMUM_SPEECH_MS = 250;

/** Native kapıdan bağımsız, tur sonlandırmayı belirleyen saf React kapısı. */
export function evaluateRecognitionTurn(turn: RecognitionTurn): RecognitionDecision {
  if (turn.session !== turn.activeSession) return "reject";
  if (turn.requestedRevision !== turn.candidateRevision) return "wait";
  const { event } = turn;
  const text = event.metin.trim();
  if (event.tur !== "son" && !(turn.timedOut && event.tur === "kismi")) return "wait";
  if (event.speech_ms <= 0) return "wait";
  if (!text || event.speech_ms < MINIMUM_SPEECH_MS || event.guven === null || event.guven < MINIMUM_CONFIDENCE) {
    return event.tur === "son" ? "reject" : "wait";
  }
  if (turn.timedOut && text.split(/\s+/u).length < 2) return "wait";
  return "accept";
}

export type VoiceMachineEvent =
  | { type: "START_LISTENING"; session?: number }
  | { type: "RECOGNITION"; session: number; event: RecognitionEvent }
  | { type: "EVALUATE_TIMEOUT"; session: number; candidateRevision: number }
  | { type: "ASSISTANT_STARTED"; text?: string }
  | { type: "ASSISTANT_FINISHED" }
  | { type: "ASK_OPENED" }
  | { type: "ASK_CLOSED" }
  | { type: "FAILED"; text: string }
  | { type: "STOPPED" };

export const initialVoiceMachine: VoiceMachineState = {
  autoListen: false,
  candidate: null,
  candidateRevision: 0,
  error: null,
  finalizedSession: null,
  finalRevision: 0,
  finalText: null,
  lastFinal: null,
  partial: "",
  phase: "idle",
  phaseBeforeAsk: null,
  session: 0,
  transcript: "",
};

function accept(state: VoiceMachineState, text: string): VoiceMachineState {
  if (state.finalizedSession === state.session) return state;
  return {
    ...state,
    candidate: null,
    error: null,
    finalizedSession: state.session,
    finalRevision: state.finalRevision + 1,
    finalText: text,
    lastFinal: text,
    partial: "",
    phase: "thinking",
    transcript: text,
  };
}

export function voiceMachine(state: VoiceMachineState, event: VoiceMachineEvent): VoiceMachineState {
  switch (event.type) {
    case "START_LISTENING":
      return {
        ...state,
        autoListen: true,
        candidate: null,
        candidateRevision: 0,
        error: null,
        finalizedSession: null,
        finalText: null,
        lastFinal: null,
        partial: "",
        phase: "calibrating",
        session: event.session ?? state.session + 1,
        transcript: "",
      };
    case "RECOGNITION": {
      if (event.session !== state.session || state.finalizedSession === state.session) return state;
      const recognition = event.event;
      if (recognition.tur === "hazir") return { ...state, phase: "listening" };
      if (recognition.tur === "ses-basladi") return { ...state, phase: "hearing" };
      if (recognition.tur === "hata") return { ...state, error: recognition.metin, phase: "error" };
      if (recognition.tur === "ses-bitti") {
        return state.candidate ? state : { ...state, phase: "listening", transcript: "" };
      }
      const candidateRevision = state.candidateRevision + 1;
      const decision = evaluateRecognitionTurn({
        activeSession: state.session,
        candidateRevision,
        event: recognition,
        requestedRevision: candidateRevision,
        session: event.session,
        timedOut: false,
      });
      if (decision === "accept") return accept({ ...state, candidateRevision }, recognition.metin.trim());
      if (decision === "reject") {
        return {
          ...state,
          candidate: null,
          candidateRevision,
          partial: "",
          phase: "interrupted",
          transcript: "Anlayamadım, tekrar söyle",
        };
      }
      if (recognition.tur !== "kismi" || recognition.speech_ms < MINIMUM_SPEECH_MS
        || recognition.guven === null || recognition.guven < MINIMUM_CONFIDENCE) {
        return state.phase === "calibrating" ? { ...state, phase: "listening" } : state;
      }
      const text = recognition.metin.trim();
      if (!text) return state;
      return {
        ...state,
        candidate: { ...recognition, metin: text },
        candidateRevision,
        error: null,
        partial: text,
        phase: "transcribing",
        transcript: text,
      };
    }
    case "EVALUATE_TIMEOUT": {
      if (event.session !== state.session || !state.candidate || state.finalizedSession === state.session) return state;
      const decision = evaluateRecognitionTurn({
        activeSession: state.session,
        candidateRevision: state.candidateRevision,
        event: state.candidate,
        requestedRevision: event.candidateRevision,
        session: event.session,
        timedOut: true,
      });
      return decision === "accept" ? accept(state, state.candidate.metin) : state;
    }
    case "ASSISTANT_STARTED":
      return { ...state, candidate: null, error: null, partial: "", phase: "talking", transcript: event.text?.trim() || state.transcript };
    case "ASSISTANT_FINISHED":
      return { ...state, lastFinal: null, phase: state.autoListen ? "listening" : "idle" };
    case "ASK_OPENED":
      return state.phase === "approval" ? state : { ...state, phase: "approval", phaseBeforeAsk: state.phase };
    case "ASK_CLOSED":
      return state.phase !== "approval" ? state : { ...state, phase: state.phaseBeforeAsk ?? (state.autoListen ? "listening" : "idle"), phaseBeforeAsk: null };
    case "FAILED":
      return { ...state, candidate: null, error: event.text, partial: "", phase: "error" };
    case "STOPPED":
      return { ...state, autoListen: false, candidate: null, lastFinal: null, partial: "", phase: "idle" };
  }
}
