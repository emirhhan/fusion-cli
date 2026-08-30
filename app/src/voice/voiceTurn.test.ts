import { describe, expect, it, vi } from "vitest";
import { findVoiceAnswer, speakVoiceAnswer } from "./voiceTurn";

describe("Talk yanıt yaşam döngüsü", () => {
  it("yalnız sesli turun ardından eklenen asistan yanıtını seçer", () => {
    const messages = [
      { rol: "asistan" as const, metin: "eski" },
      { rol: "kullanici" as const, metin: "merhaba" },
      { rol: "asistan" as const, metin: "yeni yanıt" },
    ];
    expect(findVoiceAnswer(messages, 1)).toBe("yeni yanıt");
    expect(findVoiceAnswer(messages, 3)).toBeNull();
  });

  it("TTS başında talking, gerçek bitiş yanıtından sonra listening yayınlar", async () => {
    const publish = vi.fn(async () => undefined);
    const request = vi.fn(async () => ({ ok: true, tamamlandi: true }));

    await speakVoiceAnswer({ request }, "Merhaba", publish);

    expect(request).toHaveBeenCalledWith("ses.konus", { bekle: true, metin: "Merhaba" });
    expect(publish.mock.calls).toEqual([
      [{ durum: "talking", metin: "Merhaba" }],
      [{ durum: "listening" }],
    ]);
  });

  it("ses motoru reddederse mikrofonu açmak yerine görünür hata yayınlar", async () => {
    const publish = vi.fn(async () => undefined);
    await speakVoiceAnswer(
      { request: vi.fn(async () => ({ ok: false, metin: "Türkçe ses yok" })) },
      "Merhaba",
      publish,
    );
    expect(publish.mock.calls.at(-1)?.[0]).toEqual({ durum: "error", metin: "Türkçe ses yok" });
  });
});
