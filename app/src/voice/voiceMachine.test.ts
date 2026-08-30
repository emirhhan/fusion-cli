import { describe, expect, it } from "vitest";
import { initialVoiceMachine, voiceMachine } from "./voiceMachine";

describe("voiceMachine", () => {
  it("kısmi metni yalnız ekranda tutar, finali tek bir gönderim revizyonuna çevirir", () => {
    const listening = voiceMachine(initialVoiceMachine, { type: "START_LISTENING" });
    const partial = voiceMachine(listening, { type: "PARTIAL", text: "merha" });
    const final = voiceMachine(partial, { type: "FINAL", text: "merhaba" });
    const duplicate = voiceMachine(final, { type: "FINAL", text: "merhaba" });

    expect(partial.phase).toBe("transcribing");
    expect(partial.finalRevision).toBe(0);
    expect(final).toMatchObject({ phase: "thinking", transcript: "merhaba", finalText: "merhaba", finalRevision: 1 });
    expect(duplicate).toBe(final);
  });

  it("TTS başında dinlemeyi kapatır, bitince açık kullanıcı niyetine geri döner", () => {
    const listening = voiceMachine(initialVoiceMachine, { type: "START_LISTENING" });
    const talking = voiceMachine(listening, { type: "ASSISTANT_STARTED", text: "Yanıt" });
    const resumed = voiceMachine(talking, { type: "ASSISTANT_FINISHED" });

    expect(talking.phase).toBe("talking");
    expect(resumed.phase).toBe("listening");
  });

  it("onay açılıp kapanırken transkripti korur ve onay varsaymaz", () => {
    const final = voiceMachine(
      voiceMachine(initialVoiceMachine, { type: "START_LISTENING" }),
      { type: "FINAL", text: "dosyayı düzenle" },
    );
    const approval = voiceMachine(final, { type: "ASK_OPENED" });
    const closed = voiceMachine(approval, { type: "ASK_CLOSED" });

    expect(approval).toMatchObject({ phase: "approval", transcript: "dosyayı düzenle" });
    expect(closed).toMatchObject({ phase: "thinking", transcript: "dosyayı düzenle" });
  });

  it("STOPPED otomatik yeniden dinlemeyi kapatır; hata metnini görünür tutar", () => {
    const stopped = voiceMachine(
      voiceMachine(initialVoiceMachine, { type: "START_LISTENING" }),
      { type: "STOPPED" },
    );
    expect(voiceMachine(stopped, { type: "ASSISTANT_FINISHED" }).phase).toBe("idle");
    expect(voiceMachine(stopped, { type: "FAILED", text: "Mikrofon yok" })).toMatchObject({
      error: "Mikrofon yok",
      phase: "error",
    });
  });
});
