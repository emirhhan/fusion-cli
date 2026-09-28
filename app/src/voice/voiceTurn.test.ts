import { describe, expect, it, vi } from "vitest";
import { cannedVoiceAnswer, findVoiceAnswer, speakVoiceAnswer, speakVoiceAnswerStreamed } from "./voiceTurn";

describe("hazır Talk yanıtları", () => {
  it("selamlaşmaları doğrudan karşılar", () => {
    expect(cannedVoiceAnswer("Merhaba!" )).toBe("merhabalar abi buyur");
    expect(cannedVoiceAnswer("Nasılsın Fusion?" )).toBe("iyidir çok şükür sen nasılsın yok bir yaramazlık inşallah");
    expect(cannedVoiceAnswer("Nasılsın diye bir şiir yaz")).toBeNull();
  });
});

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

describe("cümle cümle akan Talk yanıtı", () => {
  it("her cümleyi AYRI bir ses.konus turu olarak sırayla gönderir", async () => {
    const konusCagrilari: string[] = [];
    let turSayaci = 0;
    const request = vi.fn(async (name: string, data: Record<string, unknown>) => {
      if (name === "ses.konus") {
        konusCagrilari.push(data.metin as string);
        turSayaci += 1;
        return { ok: true, tur_id: `turn-${turSayaci}` };
      }
      return { ok: true, tamamlandi: true };
    });
    const publish = vi.fn(async () => undefined);

    const handle = await speakVoiceAnswerStreamed(
      { request }, "Birinci cümle. İkinci cümle.", publish,
    );
    await handle.finished;

    expect(konusCagrilari).toEqual(["Birinci cümle.", "İkinci cümle."]);
    expect(publish.mock.calls).toEqual([
      [{ durum: "talking", metin: "Birinci cümle. İkinci cümle." }],
      [{ durum: "listening" }],
    ]);
  });

  it("ikinci cümle başlamadan önce ilk cümlenin bitişini bekler", async () => {
    let ikinciCumleBasladiMi = false;
    let birinciyiBitir!: () => void;
    const birinciBekleme = new Promise<void>((resolve) => { birinciyiBitir = resolve; });
    const request = vi.fn(async (name: string, data: Record<string, unknown>) => {
      if (name === "ses.konus") {
        if (data.metin === "İkinci.") ikinciCumleBasladiMi = true;
        return { ok: true, tur_id: data.metin === "Birinci." ? "turn-1" : "turn-2" };
      }
      if (data.tur_id === "turn-1") {
        await birinciBekleme;
        return { ok: true, tamamlandi: true };
      }
      return { ok: true, tamamlandi: true };
    });
    const publish = vi.fn(async () => undefined);

    const handle = await speakVoiceAnswerStreamed({ request }, "Birinci. İkinci.", publish);
    await Promise.resolve();
    await Promise.resolve();
    expect(ikinciCumleBasladiMi).toBe(false);

    birinciyiBitir();
    await handle.finished;
    expect(ikinciCumleBasladiMi).toBe(true);
  });

  it("iptal, o an çalan cümleyi durdurur ve kalan kuyruğu başlatmaz", async () => {
    const konusCagrilari: string[] = [];
    const request = vi.fn(async (name: string, data: Record<string, unknown>) => {
      if (name === "ses.konus") {
        konusCagrilari.push(data.metin as string);
        return { ok: true, tur_id: "turn-1" };
      }
      if (name === "ses.durdur") {
        return { ok: true, tur_id: "turn-1" };
      }
      return new Promise(() => undefined); // ses.bekle hiç çözülmez: iptal onu keser.
    });
    const publish = vi.fn(async () => undefined);

    const handle = await speakVoiceAnswerStreamed(
      { request }, "Birinci cümle. İkinci cümle. Üçüncü cümle.", publish,
    );
    await handle.cancel();

    expect(konusCagrilari).toEqual(["Birinci cümle."]);
    expect(request.mock.calls.filter(([name]) => name === "ses.durdur")).toEqual([
      ["ses.durdur", { tur_id: "turn-1" }],
    ]);
  });

  it("cümleye bölünemeyen kısa metni tek tur olarak gönderir", async () => {
    const request = vi.fn(async (name: string) => {
      if (name === "ses.konus") return { ok: true, tur_id: "turn-1" };
      return { ok: true, tamamlandi: true };
    });
    const publish = vi.fn(async () => undefined);

    const handle = await speakVoiceAnswerStreamed({ request }, "tamam", publish);
    await handle.finished;

    expect(request).toHaveBeenNthCalledWith(1, "ses.konus", { metin: "tamam" });
  });
});
