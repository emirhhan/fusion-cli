import { describe, expect, it } from "vitest";
import { evaluateRecognitionTurn, initialVoiceMachine, voiceMachine, type RecognitionEvent } from "./voiceMachine";

const recognition = (tur: RecognitionEvent["tur"], metin = "", guven: number | null = null, speech_ms = 0, segment = 1): RecognitionEvent => ({ tur, metin, guven, speech_ms, segment });

describe("evaluateRecognitionTurn", () => {
  it("sessiz turu bekletir", () => {
    expect(evaluateRecognitionTurn({ activeSession: 8, candidateRevision: 0, event: recognition("ses-bitti"), requestedRevision: 0, session: 8, timedOut: false })).toBe("wait");
  });

  it("sesli ama düşük güvenli finali reddeder", () => {
    expect(evaluateRecognitionTurn({ activeSession: 8, candidateRevision: 1, event: recognition("son", "Evet", 0.08, 320), requestedRevision: 1, session: 8, timedOut: false })).toBe("reject");
  });

  it("yeterli konuşmalı güvenilir tek sözcük finali kabul eder", () => {
    expect(evaluateRecognitionTurn({ activeSession: 8, candidateRevision: 1, event: recognition("son", "Evet", 0.82, 320), requestedRevision: 1, session: 8, timedOut: false })).toBe("accept");
  });

  it("zaman aşımında kararlı tam cümleyi kabul eder", () => {
    expect(evaluateRecognitionTurn({ activeSession: 8, candidateRevision: 3, event: recognition("kismi", "Fusion projeyi şimdi aç", 0.84, 720), requestedRevision: 3, session: 8, timedOut: true })).toBe("accept");
  });

  it("eski zamanlayıcı revizyonunu bekletir", () => {
    expect(evaluateRecognitionTurn({ activeSession: 8, candidateRevision: 4, event: recognition("kismi", "yeni ve tamamlanmış metin", 0.84, 720), requestedRevision: 3, session: 8, timedOut: true })).toBe("wait");
  });

  it("eski oturumu reddeder", () => {
    expect(evaluateRecognitionTurn({ activeSession: 9, candidateRevision: 1, event: recognition("son", "eski mesaj", 0.91, 500), requestedRevision: 1, session: 8, timedOut: false })).toBe("reject");
  });
});

describe("voiceMachine", () => {
  it("sessiz biten turu boş transkriptle dinlemede tutar", () => {
    const calibrating = voiceMachine(initialVoiceMachine, { type: "START_LISTENING", session: 4 });
    const silent = voiceMachine(calibrating, { type: "RECOGNITION", session: 4, event: recognition("ses-bitti") });
    expect(silent).toMatchObject({ finalRevision: 0, phase: "listening", transcript: "" });
  });

  it("sessizlikte gelen düşük güvenli eveti göndermez", () => {
    const listening = voiceMachine(initialVoiceMachine, { type: "START_LISTENING", session: 8 });
    const result = voiceMachine(listening, { type: "RECOGNITION", session: 8, event: recognition("kismi", "Evet", 0.08, 0) });
    expect(result.finalRevision).toBe(0);
    expect(result.phase).toBe("listening");
    expect(result.transcript).toBe("");
  });

  it("kalibrasyon ve konuşma başlangıcını ayrı aşamalarda gösterir", () => {
    const calibrating = voiceMachine(initialVoiceMachine, { type: "START_LISTENING", session: 3 });
    const hearing = voiceMachine(calibrating, { type: "RECOGNITION", session: 3, event: recognition("ses-basladi", "", null, 80) });
    expect(calibrating.phase).toBe("calibrating");
    expect(hearing.phase).toBe("hearing");
  });

  it("güvenilir finali bir kez sonlandırır ve yinelenen finali yok sayar", () => {
    const listening = voiceMachine(initialVoiceMachine, { type: "START_LISTENING", session: 7 });
    const final = voiceMachine(listening, { type: "RECOGNITION", session: 7, event: recognition("son", "tek mesaj", 0.91, 500) });
    const duplicate = voiceMachine(final, { type: "RECOGNITION", session: 7, event: recognition("son", "ikinci mesaj", 0.95, 700) });
    expect(final).toMatchObject({ finalRevision: 1, finalText: "tek mesaj", phase: "thinking" });
    expect(duplicate).toBe(final);
  });

  it("sesli ama reddedilen finali göndermez ve tekrar isteme durumuna geçer", () => {
    const listening = voiceMachine(initialVoiceMachine, { type: "START_LISTENING", session: 5 });
    const rejected = voiceMachine(listening, { type: "RECOGNITION", session: 5, event: recognition("son", "belirsiz", 0.1, 420) });
    expect(rejected).toMatchObject({ finalRevision: 0, phase: "interrupted", transcript: "Anlayamadım, tekrar söyle" });
  });

  it("eski oturum olayını ve eski zamanlayıcıyı yok sayar", () => {
    const first = voiceMachine(initialVoiceMachine, { type: "START_LISTENING", session: 1 });
    const partial = voiceMachine(first, { type: "RECOGNITION", session: 1, event: recognition("kismi", "ilk uzun aday", 0.8, 500) });
    const second = voiceMachine(partial, { type: "START_LISTENING", session: 2 });
    expect(voiceMachine(second, { type: "RECOGNITION", session: 1, event: recognition("son", "eski", 0.9, 500) })).toBe(second);
    expect(voiceMachine(second, { type: "EVALUATE_TIMEOUT", session: 1, candidateRevision: partial.candidateRevision })).toBe(second);
  });
});
