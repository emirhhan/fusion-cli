import { describe, expect, it, vi } from "vitest";
import { createVoicePlayback } from "./voicePlayback";
import { speakVoiceAnswerStreamed } from "./voiceTurn";

/**
 * Konuşma NESLİ sahipliği (WP14, madde 1). Ölçüldü (29 Ekim):
 * - `speakVoiceAnswerStreamed.cancel()`, sıradaki cümlenin `ses.konus` isteği uçuştayken çağrılırsa
 *   geç dönen tur durdurulmuyordu: kullanıcı kestikten sonra eski cevap çalmaya devam ediyordu.
 * - `createVoicePlayback` çekirdeğe nesil bildirmiyordu; geç gelen eski nesil isteği, yeni konuşmanın
 *   oynatıcısını ezebiliyordu ve çekirdek `eski_nesil` cevabını genel hata sayıyordu.
 */
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
};

type Reply = Record<string, unknown>;

describe("akışlı TTS iptal yarışı", () => {
  it("sıradaki cümlenin başlatması uçuştayken gelen iptal, geç dönen turu da durdurur", async () => {
    const second = deferred<Reply>();
    const calls: string[] = [];
    const request = vi.fn(async (name: string, data: Record<string, unknown>) => {
      calls.push(`${name}:${String(data.tur_id ?? data.metin ?? "")}`);
      if (name === "ses.konus") return data.metin === "Birinci cümle." ? { ok: true, tur_id: "t1" } : second.promise;
      if (name === "ses.bekle" && data.tur_id === "t1") return { ok: true, tamamlandi: true };
      if (name === "ses.durdur") return { ok: true };
      return new Promise(() => undefined);
    });
    const publish = vi.fn(async () => undefined);
    const handle = await speakVoiceAnswerStreamed({ request }, "Birinci cümle. İkinci cümle. Üçüncü cümle.", publish);
    await vi.waitFor(() => expect(calls).toContain("ses.konus:İkinci cümle."));

    const cancelling = handle.cancel();
    second.resolve({ ok: true, tur_id: "t2" });
    await cancelling;
    await handle.finished;

    expect(request).toHaveBeenCalledWith("ses.durdur", { tur_id: "t2" });
    expect(calls).not.toContain("ses.konus:Üçüncü cümle.");
    expect(publish).toHaveBeenCalledWith({ durum: "interrupted" });
  });
});

describe("hazır ses kuyruğu nesli", () => {
  const client = (script: (name: string, data: Reply) => Promise<Reply> | Reply) => ({
    request: vi.fn(async (name: string, data: Record<string, unknown>) => script(name, data)),
  });

  it("hazırlama ve oynatma istekleri aynı, artan nesil kimliğini taşır", async () => {
    const generations: unknown[] = [];
    const first = client((name, data) => {
      if (name === "ses.hazirla") { generations.push(data.nesil); return { ok: true, hazir_id: "a" }; }
      if (name === "ses.haziri_cal") { generations.push(data.nesil); return { ok: true, tur_id: "ta" }; }
      return { ok: true, tamamlandi: true };
    });
    await createVoicePlayback(first, "Merhaba.", async () => undefined).finished;
    const second = client((name, data) => {
      if (name === "ses.hazirla") { generations.push(data.nesil); return { ok: true, hazir_id: "b" }; }
      if (name === "ses.haziri_cal") { generations.push(data.nesil); return { ok: true, tur_id: "tb" }; }
      return { ok: true, tamamlandi: true };
    });
    await createVoicePlayback(second, "Selam.", async () => undefined).finished;
    expect(generations).toHaveLength(4);
    expect(generations[0]).toBe(generations[1]);
    expect(generations[2]).toBe(generations[3]);
    expect(generations[2] as number).toBeGreaterThan(generations[0] as number);
  });

  it("iptal ACK'i gecikirken yeni nesil hazırlığı önce bitse de eski neslin sıradaki cümlesi çalmaz", async () => {
    const ack = deferred<Reply>();
    const firstEnd = deferred<Reply>();
    const played: string[] = [];
    const old = client((name, data) => {
      if (name === "ses.hazirla") return { ok: true, hazir_id: `old-${played.length + (data.metin ? 1 : 0)}-${String(data.metin).length}` };
      if (name === "ses.haziri_cal") { played.push(`old:${String(data.hazir_id)}`); return { ok: true, tur_id: "old-turn" }; }
      if (name === "ses.bekle") return firstEnd.promise;
      if (name === "ses.durdur") return ack.promise; // ACK gecikiyor
      return { ok: true };
    });
    const fresh = client((name, data) => {
      if (name === "ses.hazirla") return { ok: true, hazir_id: "fresh" };
      if (name === "ses.haziri_cal") { played.push(`fresh:${String(data.hazir_id)}`); return { ok: true, tur_id: "fresh-turn" }; }
      return { ok: true, tamamlandi: true };
    });
    const longText = `İlk cümle ${"uzun ".repeat(32)}. İkinci cümle.`;
    const oldTurn = createVoicePlayback(old, longText, async () => undefined);
    await vi.waitFor(() => expect(played).toHaveLength(1));
    const cancelling = oldTurn.cancel();

    const freshTurn = createVoicePlayback(fresh, "Yeni konuşma.", async () => undefined);
    await freshTurn.finished; // yeni konuşma eski iptalin ACK'ini BEKLEMEZ

    firstEnd.resolve({ ok: true, tamamlandi: false });
    ack.resolve({ ok: true });
    await cancelling;
    await oldTurn.finished;
    expect(played.filter((entry) => entry.startsWith("old:"))).toHaveLength(1);
    expect(played).toContain("fresh:fresh");
  });

  it("yayın sürerken iptal ACK'i gelirse kimliksiz ses.bekle çağrılmaz", async () => {
    const talking = deferred<void>();
    const request = vi.fn(async (name: string) => {
      if (name === "ses.hazirla") return { ok: true, hazir_id: "h" };
      if (name === "ses.haziri_cal") return { ok: true, tur_id: "t" };
      return { ok: true, tamamlandi: true };
    });
    const publish = vi.fn(async (state: { durum: string }) => { if (state.durum === "talking") await talking.promise; });
    const turn = createVoicePlayback({ request }, "Bir cümle. İki cümle.", publish);
    await vi.waitFor(() => expect(publish).toHaveBeenCalledWith(expect.objectContaining({ durum: "talking" })));
    const cancelling = turn.cancel();
    await vi.waitFor(() => expect(request).toHaveBeenCalledWith("ses.durdur", { tur_id: "t" }));
    talking.resolve();
    await cancelling;
    await turn.finished;
    expect(request.mock.calls.filter(([name, data]) => name === "ses.bekle" && !(data as Reply).tur_id)).toEqual([]);
  });

  it("çekirdek eski_nesil derse tur sessizce biter: hata yayınlanmaz, 'dinliyor' denmez", async () => {
    const publish = vi.fn(async () => undefined);
    const stale = client((name) => {
      if (name === "ses.hazirla") return { ok: true, hazir_id: "x" };
      if (name === "ses.haziri_cal") return { ok: false, eski_nesil: true, metin: "Daha yeni bir konuşma başladı." };
      return { ok: true };
    });
    const turn = createVoicePlayback(stale, "Eski cevap.", publish);
    await expect(turn.finished).resolves.toBeUndefined();
    expect(publish).not.toHaveBeenCalledWith(expect.objectContaining({ durum: "error" }));
    expect(publish).not.toHaveBeenCalledWith({ durum: "listening" });
    expect(stale.request).toHaveBeenCalledWith("ses.haziri_sil", { hazir_id: "x" });
  });

  it("hazırlama sırasında eski_nesil dönerse de sessiz biter", async () => {
    const publish = vi.fn(async () => undefined);
    const stale = client((name) => (name === "ses.hazirla"
      ? { ok: false, eski_nesil: true, metin: "Daha yeni bir konuşma başladı." } : { ok: true }));
    await expect(createVoicePlayback(stale, "Eski.", publish).finished).resolves.toBeUndefined();
    expect(publish).not.toHaveBeenCalledWith(expect.objectContaining({ durum: "error" }));
  });
});
