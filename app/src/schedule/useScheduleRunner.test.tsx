import { renderHook, cleanup, act } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useScheduleRunner } from "./useScheduleRunner";
import type { ScheduleDelivery, ScheduleReceipt } from "./types";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function delivery(letter: string): ScheduleDelivery {
  return {
    occurrence_id: letter.repeat(64),
    schedule_id: `schedule-${letter}`,
    due_at: 100,
    title: `Görev ${letter}`,
    task: "incele",
    root: "/proje",
    task_id: null,
  };
}
function queued(item: ScheduleDelivery): ScheduleReceipt {
  return { occurrenceId: item.occurrence_id, taskId: `schedule-${item.occurrence_id}`, status: "queued" };
}
function core(items: ScheduleDelivery[], failAck: (id: string) => boolean = () => false) {
  return {
    request: vi.fn(async (name: string, data: Record<string, unknown>) => {
      if (name === "zamanlama.teslim_bekleyenler") return { ok: true, teslimler: items };
      if (name === "zamanlama.teslim_onayla" && failAck(String(data.occurrence_id))) {
        throw new Error("ack yazılamadı");
      }
      return { ok: true };
    }),
  };
}
async function runOnePoll(client: ReturnType<typeof core>, deliver: (item: ScheduleDelivery) => Promise<ScheduleReceipt | null>) {
  renderHook(() =>
    useScheduleRunner({
      client,
      deliveryClient: { deliver },
      create: async () => "x",
      send: () => true,
      sessions: {},
    }),
  );
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
}
const acked = (client: ReturnType<typeof core>) =>
  client.request.mock.calls
    .filter(([name]) => name === "zamanlama.teslim_onayla")
    .map(([, data]) => data.occurrence_id);

describe("useScheduleRunner teslim döngüsü", () => {
  it("ilk teslim istisna fırlatsa da sonraki teslim aynı turda ilerler", async () => {
    const [first, second] = [delivery("a"), delivery("b")];
    const client = core([first, second]);
    const deliver = vi.fn(async (item: ScheduleDelivery) => {
      if (item === first) throw new Error("Kits yanıt vermedi");
      return queued(item);
    });
    await runOnePoll(client, deliver);
    expect(deliver).toHaveBeenCalledTimes(2);
    expect(acked(client)).toEqual([second.occurrence_id]);
  });

  it("ack yazımı başarısız olsa da sonraki teslim ilerler; ack'siz kayıt kuyrukta kalır", async () => {
    const [first, second] = [delivery("a"), delivery("b")];
    const client = core([first, second], (id) => id === first.occurrence_id);
    await runOnePoll(client, async (item) => queued(item));
    expect(acked(client)).toEqual([first.occurrence_id, second.occurrence_id]);
  });

  it("makbuz dönmeyen teslim ack almaz, sonrakini engellemez", async () => {
    const [first, second] = [delivery("a"), delivery("b")];
    const client = core([first, second]);
    await runOnePoll(client, async (item) => (item === first ? null : queued(item)));
    expect(acked(client)).toEqual([second.occurrence_id]);
  });
});

describe("useScheduleRunner gözetimsiz tur güvenliği (U5-57)", () => {
  const TASK = {
    baslik: "Rapor", etkin: true, gorev: "stok raporu", id: "t1", kok: "/proje",
    son_calisma: null, sonraki: null, tur: "gunluk" as const, saat: "09:00",
  };
  function sessionClient(mod: string, durumOk = true) {
    return {
      request: vi.fn(async (name: string) => {
        if (name === "oturum.durum") return durumOk ? { ok: true, mod } : { ok: false };
        return { ok: true };
      }),
    };
  }
  type Props = Parameters<typeof useScheduleRunner>[0];
  async function flush() {
    await act(async () => { for (let i = 0; i < 5; i++) await Promise.resolve(); });
  }
  function setup(sessionClientValue: ReturnType<typeof sessionClient>, extra: Partial<Props> = {}) {
    const send = vi.fn(() => true);
    const onNeedsApproval = vi.fn();
    const onBlocked = vi.fn();
    const initial: Props["sessions"] = { s1: { status: "ready", client: sessionClientValue } };
    const view = renderHook((props: Props["sessions"]) =>
      useScheduleRunner({ client: null, create: async () => "s1", send, sessions: props, onNeedsApproval, onBlocked, ...extra }),
    { initialProps: initial });
    return { view, send, onNeedsApproval, onBlocked, initial };
  }

  it("bypass oturumu yalnız bu oturum için auto'ya çekilir (kalıcı yazılmaz), sonra görev gönderilir", async () => {
    const client = sessionClient("bypass");
    const { view, send } = setup(client);
    await act(async () => { await view.result.current.runNow(TASK); });
    view.rerender({ s1: { status: "ready", client } });
    await flush();
    expect(client.request).toHaveBeenCalledWith("oturum.baslat", { mod: "auto", mod_kalici: false });
    expect(send).toHaveBeenCalledWith("s1", "stok raporu");
    const order = [...client.request.mock.calls.map(([name]) => name)];
    expect(order).toEqual(["oturum.durum", "oturum.baslat"]);
  });

  it("bypass olmayan oturumda mod değiştirilmez", async () => {
    const client = sessionClient("security");
    const { view, send } = setup(client);
    await act(async () => { await view.result.current.runNow(TASK); });
    view.rerender({ s1: { status: "ready", client } });
    await flush();
    expect(client.request).not.toHaveBeenCalledWith("oturum.baslat", expect.anything());
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("izin modu okunamazsa görev GÖNDERİLMEZ ve kullanıcı bilgilendirilir", async () => {
    const client = sessionClient("bypass", false);
    const { view, send, onBlocked } = setup(client);
    await act(async () => { await view.result.current.runNow(TASK); });
    view.rerender({ s1: { status: "ready", client } });
    await flush();
    expect(send).not.toHaveBeenCalled();
    expect(onBlocked).toHaveBeenCalledWith(TASK, expect.stringContaining("izin modu"));
  });

  it("başlayan tur onay isteyen araçta askıda kalır ve her soru için bir kez bildirilir", async () => {
    const client = sessionClient("auto");
    const { view, onNeedsApproval } = setup(client);
    await act(async () => { await view.result.current.runNow(TASK); });
    view.rerender({ s1: { status: "ready", client } });
    await flush();
    const soru = { id: "q1", data: { arac: "run_shell", baslik: "Komut çalıştırılsın mı?" } };
    view.rerender({ s1: { status: "ready", client, running: true, question: soru } });
    view.rerender({ s1: { status: "ready", client, running: true, question: soru } });
    expect(onNeedsApproval).toHaveBeenCalledTimes(1);
    expect(onNeedsApproval).toHaveBeenCalledWith({ task: TASK, sessionId: "s1", tool: "Komut çalıştırılsın mı?" });
    view.rerender({ s1: { status: "ready", client, running: true, question: { id: "q2", data: { arac: "write_file" } } } });
    expect(onNeedsApproval).toHaveBeenCalledTimes(2);
  });

  it("başlayan tur bitince bir kez onFinished çağrılır (çalışma geçmişi, P-038)", async () => {
    const client = sessionClient("auto");
    const onFinished = vi.fn();
    const { view } = setup(client, { onFinished });
    await act(async () => { await view.result.current.runNow(TASK); });
    view.rerender({ s1: { status: "ready", client } });
    await flush();
    view.rerender({ s1: { status: "ready", client, running: true } });
    expect(onFinished).not.toHaveBeenCalled();
    view.rerender({ s1: { status: "ready", client, running: false } });
    view.rerender({ s1: { status: "ready", client, running: false } });
    expect(onFinished).toHaveBeenCalledTimes(1);
    expect(onFinished).toHaveBeenCalledWith(TASK, "s1");
  });
});

describe("useScheduleRunner yoklama sahipliği", () => {
  function leasedCore(lease: Record<string, unknown>, items: ScheduleDelivery[] = [delivery("a")]) {
    return {
      request: vi.fn(async (name: string) => {
        if (name === "zamanlama.sahiplik") return lease;
        if (name === "zamanlama.teslim_bekleyenler") return { ok: true, teslimler: items };
        return { ok: true };
      }),
    };
  }
  const names = (client: ReturnType<typeof leasedCore>) => client.request.mock.calls.map(([name]) => name);

  it("kira başka örnekteyse vade alınmaz ve teslim yapılmaz", async () => {
    const client = leasedCore({ ok: true, sahip: false, bekle_s: 40 });
    const deliver = vi.fn(async (item: ScheduleDelivery) => queued(item));
    await runOnePoll(client, deliver);

    expect(names(client)).toEqual(["zamanlama.sahiplik"]);
    expect(deliver).not.toHaveBeenCalled();
  });

  it("kira alınınca yoklama sürer; sahip kimliği ve süre gönderilir", async () => {
    const client = leasedCore({ ok: true, sahip: true, bitis: 1 });
    const deliver = vi.fn(async (item: ScheduleDelivery) => queued(item));
    await runOnePoll(client, deliver);

    expect(names(client)).toEqual([
      "zamanlama.sahiplik",
      "zamanlama.vadesi_gelenler",
      "zamanlama.teslim_bekleyenler",
      "zamanlama.teslim_onayla",
    ]);
    const [, veri] = client.request.mock.calls[0];
    expect(typeof veri.sahip).toBe("string");
    expect((veri.sahip as string).length).toBeGreaterThan(8);
    expect(veri.sure_s).toBe(75);
    expect(deliver).toHaveBeenCalledTimes(1);
  });

  it("kira isteği bilinmeyen (eski çekirdek) ise yoklama eskisi gibi sürer", async () => {
    const client = leasedCore({ ok: false, metin: "Bilinmeyen istek: zamanlama.sahiplik" });
    const deliver = vi.fn(async (item: ScheduleDelivery) => queued(item));
    await runOnePoll(client, deliver);

    expect(deliver).toHaveBeenCalledTimes(1);
  });

  it("sayfa kapanırken kira bırakılır", async () => {
    const client = leasedCore({ ok: true, sahip: true, bitis: 1 }, []);
    await runOnePoll(client, async (item) => queued(item));

    window.dispatchEvent(new Event("pagehide"));

    expect(names(client)).toContain("zamanlama.sahiplik_birak");
  });
});
