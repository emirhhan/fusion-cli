export type VoicePhase =
  | "idle"
  | "listening"
  | "transcribing"
  | "thinking"
  | "talking"
  | "approval"
  | "error";

export interface VoiceMachineState {
  autoListen: boolean;
  error: string | null;
  finalRevision: number;
  finalText: string | null;
  lastFinal: string | null;
  partial: string;
  phase: VoicePhase;
  phaseBeforeAsk: VoicePhase | null;
  transcript: string;
}

export type VoiceMachineEvent =
  | { type: "START_LISTENING" }
  | { type: "PARTIAL"; text: string }
  | { type: "FINAL"; text: string }
  | { type: "ASSISTANT_STARTED"; text?: string }
  | { type: "ASSISTANT_FINISHED" }
  | { type: "ASK_OPENED" }
  | { type: "ASK_CLOSED" }
  | { type: "FAILED"; text: string }
  | { type: "STOPPED" };

export const initialVoiceMachine: VoiceMachineState = {
  autoListen: false,
  error: null,
  finalRevision: 0,
  finalText: null,
  lastFinal: null,
  partial: "",
  phase: "idle",
  phaseBeforeAsk: null,
  transcript: "",
};

export function voiceMachine(state: VoiceMachineState, event: VoiceMachineEvent): VoiceMachineState {
  switch (event.type) {
    case "START_LISTENING":
      return {
        ...state,
        autoListen: true,
        error: null,
        lastFinal: null,
        partial: "",
        phase: "listening",
      };
    case "PARTIAL": {
      const text = event.text.trim();
      if (!text) return state;
      return { ...state, error: null, partial: text, phase: "transcribing", transcript: text };
    }
    case "FINAL": {
      const text = event.text.trim();
      if (!text || text === state.lastFinal) return state;
      return {
        ...state,
        error: null,
        finalRevision: state.finalRevision + 1,
        finalText: text,
        lastFinal: text,
        partial: "",
        phase: "thinking",
        transcript: text,
      };
    }
    case "ASSISTANT_STARTED":
      return {
        ...state,
        error: null,
        partial: "",
        phase: "talking",
        transcript: event.text?.trim() || state.transcript,
      };
    case "ASSISTANT_FINISHED":
      return {
        ...state,
        lastFinal: null,
        phase: state.autoListen ? "listening" : "idle",
      };
    case "ASK_OPENED":
      return state.phase === "approval"
        ? state
        : { ...state, phase: "approval", phaseBeforeAsk: state.phase };
    case "ASK_CLOSED":
      return state.phase !== "approval"
        ? state
        : {
            ...state,
            phase: state.phaseBeforeAsk ?? (state.autoListen ? "listening" : "idle"),
            phaseBeforeAsk: null,
          };
    case "FAILED":
      return { ...state, error: event.text, partial: "", phase: "error" };
    case "STOPPED":
      return { ...state, autoListen: false, lastFinal: null, partial: "", phase: "idle" };
  }
}
