import { describe, expect, it, vi } from "vitest";
import { SCHEDULER_SESSION_ID, openSchedulerCore } from "./schedulerCore";
import type { SessionClosedEvent, SessionLineEvent, SessionTransport } from "../sessions/types";

/** Çekirdeği taklit eden taşıma: gelen isteklere `cevap` ile sonuç satırı döner. */
function fakeTransport(cevap: (ad: string, veri: Record<string, unknown>) => Record<string, unknown> | null = () => ({ ok: true })) {
  let line: (event: SessionLineEvent) => void = () => undefined;
  let closed: (event: SessionClosedEvent) => void = () => undefined;
  const transport = {
    create: vi.fn(async (id: string) => ({ oturum_id: id, kok: "/home", pid: 1, durum: "calisiyor" as const, kapanis_nedeni: null })),
    send: vi.fn(async (id: string, satir: string) => {
      const istek = JSON.parse(satir) as { id: string; ad: string; veri: Record<string, unknown> };
      const sonuc = cevap(istek.ad, istek.veri);
      if (sonuc) line({ oturum_id: id, satir: JSON.stringify({ tip: "sonuc", id: istek.id, veri: sonuc }) });
    }),
    close: vi.fn(async () => undefined),
    list: vi.fn(async () => []),
    onLine: vi.fn(async (handler: (event: SessionLineEvent) => void) => { line = handler; return vi.fn(); }),
    onClosed: vi.fn(async (handler: (event: SessionClosedEvent) => void) => { closed = handler; return vi.fn(); }),
  } satisfies SessionTransport;
  return { transport, emitLine: (event: SessionLineEvent) => line(event), emitClosed: (event: SessionClosedEvent) => closed(event) };
}

describe("openSchedulerCore (görünmez zamanlayıcı çekirdeği)", () => {
  it("ayrılmış kimlikle çekirdek açar ve zamanlama isteklerine yanıt alır", async () => {
    const { transport } = fakeTransport((ad) => (ad === "zamanlama.vadesi_gelenler" ? { ok: true, gorevler: [] } : { ok: false }));
    const core = await openSchedulerCore(transport, () => undefined);

    expect(transport.create).toHaveBeenCalledWith(SCHEDULER_SESSION_ID, undefined);
    await expect(core.client.request("zamanlama.vadesi_gelenler", {})).resolves.toEqual({ ok: true, gorevler: [] });
    expect(SCHEDULER_SESSION_ID).toBe("zamanlayici");
  });

  it("başka oturumun satırlarını yok sayar", async () => {
    const { transport, emitLine } = fakeTransport(() => null);
    const core = await openSchedulerCore(transport, () => undefined);
    const bekleyen = core.client.request("zamanlama.liste", {}, );
    emitLine({ oturum_id: "baska", satir: JSON.stringify({ tip: "sonuc", id: "1", veri: { ok: true, yanlis: true } }) });
    emitLine({ oturum_id: SCHEDULER_SESSION_ID, satir: JSON.stringify({ tip: "sonuc", id: "1", veri: { ok: true } }) });

    await expect(bekleyen).resolves.toEqual({ ok: true });
  });

  it("çekirdek beklenmedik kapanırsa bildirir ve bekleyen istek reddedilir", async () => {
    const { transport, emitClosed } = fakeTransport(() => null);
    const onClosed = vi.fn();
    const core = await openSchedulerCore(transport, onClosed);
    const bekleyen = core.client.request("zamanlama.liste", {});

    emitClosed({ oturum_id: SCHEDULER_SESSION_ID, neden: "süreç kapandı" });

    await expect(bekleyen).rejects.toThrow();
    expect(onClosed).toHaveBeenCalledWith("süreç kapandı");
  });

  it("close() çekirdeği kapatır, dinleyicileri bırakır ve kapanış bildirimi vermez", async () => {
    const { transport } = fakeTransport();
    const onClosed = vi.fn();
    const core = await openSchedulerCore(transport, onClosed);

    await core.close();

    expect(transport.close).toHaveBeenCalledWith(SCHEDULER_SESSION_ID);
    expect(onClosed).not.toHaveBeenCalled();
  });

  it("çekirdek açılamazsa hata verir ve dinleyicileri bırakır", async () => {
    const { transport } = fakeTransport();
    transport.create.mockRejectedValueOnce(new Error("çalışma zamanı hazır değil"));

    await expect(openSchedulerCore(transport, () => undefined)).rejects.toThrow("çalışma zamanı hazır değil");
  });

  it("yanıt vermeyen çekirdek isteği sonsuza dek asılı bırakmaz", async () => {
    vi.useFakeTimers();
    try {
      const { transport } = fakeTransport(() => null);
      const core = await openSchedulerCore(transport, () => undefined);
      const bekleyen = core.client.request("zamanlama.vadesi_gelenler", {});
      const sonuc = expect(bekleyen).rejects.toThrow();
      await vi.advanceTimersByTimeAsync(60_000);
      await sonuc;
    } finally {
      vi.useRealTimers();
    }
  });
});
