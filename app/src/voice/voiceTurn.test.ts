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

  it("TTS tur kimligini hemen verir ve gercek bitisten sonra listening yayinlar", async () => {
    const publish = vi.fn(async () => undefined);
    let finish!: (value: Record<string, unknown>) => void;
    const waiting = new Promise<Record<string, unknown>>((resolve) => { finish = resolve; });
    const request = vi.fn(async (name: string) => {
      if (name === "ses.konus") return { ok: true, tur_id: "turn-1" };
      return waiting;
    });

    const handle = await speakVoiceAnswer({ request }, "Merhaba", publish);

    expect(handle.id).toBe("turn-1");
    expect(request).toHaveBeenNthCalledWith(1, "ses.konus", { metin: "Merhaba" });
    expect(request).toHaveBeenNthCalledWith(2, "ses.bekle", { tur_id: "turn-1" });
    expect(publish.mock.calls).toEqual([[{ durum: "talking", metin: "Merhaba" }]]);

    finish({ ok: true, tamamlandi: true });
    await handle.finished;
    expect(publish.mock.calls).toEqual([
      [{ durum: "talking", metin: "Merhaba" }],
      [{ durum: "listening" }],
    ]);
  });

  it("barge-in iptal onayini recognition baslamadan once tamamlar ve tekrar iptal idempotenttir", async () => {
    const order: string[] = [];
    let finish!: (value: Record<string, unknown>) => void;
    const waiting = new Promise<Record<string, unknown>>((resolve) => { finish = resolve; });
    const request = vi.fn(async (name: string) => {
      if (name === "ses.konus") {
        order.push("tts:start");
        return { ok: true, tur_id: "turn-barge" };
      }
      if (name === "ses.bekle") return waiting;
      order.push("tts:cancel");
      await Promise.resolve();
      order.push("tts:cancelled");
      finish({ ok: true, tamamlandi: false });
      return { ok: true, durduruldu: true, tur_id: "turn-barge" };
    });
    const publish = vi.fn(async (state) => {
      if (state.durum === "interrupted") order.push("speech:detected");
      if (state.durum === "listening") order.push("recognition:start");
    });

    const handle = await speakVoiceAnswer({ request }, "Uzun yanit", publish);
    await handle.cancel();
    await handle.cancel();
    await handle.finished;

    expect(order).toEqual([
      "tts:start",
      "tts:cancel",
      "tts:cancelled",
      "speech:detected",
      "recognition:start",
    ]);
    expect(request.mock.calls.filter(([name]) => name === "ses.durdur")).toEqual([
      ["ses.durdur", { tur_id: "turn-barge" }],
    ]);
  });

  it("ses motoru reddederse mikrofonu açmak yerine görünür hata yayınlar", async () => {
    const publish = vi.fn(async () => undefined);
    await expect(speakVoiceAnswer(
      { request: vi.fn(async () => ({ ok: false, metin: "Türkçe ses yok" })) },
      "Merhaba",
      publish,
    )).rejects.toThrow("Türkçe ses yok");
    expect(publish.mock.calls.at(-1)?.[0]).toEqual({ durum: "error", metin: "Türkçe ses yok" });
  });
});
