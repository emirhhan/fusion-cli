import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ScheduleScreen, draftPayload } from "./ScheduleScreen";
import { describeSchedule, type ScheduledTask } from "./types";
import { useScheduleRunner } from "./useScheduleRunner";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const gorev: ScheduledTask = {
  baslik: "Sabah raporu", etkin: true, gorev: "Stok raporunu çıkar", id: "a1", kok: "/proje",
  saat: "09:00", son_calisma: null, sonraki: 1_800_000_000, tur: "gunluk",
};

function fakeClient(list: ScheduledTask[] = [gorev]) {
  const request = vi.fn(async (name: string, _data: Record<string, unknown>) =>
    name === "zamanlama.liste" ? { ok: true, gorevler: list } : { ok: true, gorev });
  return { client: { request }, request };
}

describe("describeSchedule", () => {
  it("takvimi okunur Türkçe ile anlatır", () => {
    expect(describeSchedule({ tur: "gunluk", saat: "09:00" })).toBe("Her gün 09:00");
    expect(describeSchedule({ tur: "haftalik", saat: "18:30", gunler: [4, 0] })).toBe("Pzt, Cum 18:30");
    expect(describeSchedule({ tur: "aralik", dakika: 120 })).toBe("2 saatte bir");
    expect(describeSchedule({ tur: "aralik", dakika: 45 })).toBe("45 dakikada bir");
  });
});

describe("draftPayload", () => {
  const taslak = { baslik: "", dakika: "30", gorev: "iş", gunler: [1], kok: "/p", saat: "08:15", tarih: "", tur: "gunluk" as const };

  it("türe göre yalnız ilgili alanları gönderir", () => {
    expect(draftPayload(taslak)).toEqual({ baslik: "", gorev: "iş", kok: "/p", tur: "gunluk", saat: "08:15" });
    expect(draftPayload({ ...taslak, tur: "aralik" })).toMatchObject({ dakika: 30 });
    expect(draftPayload({ ...taslak, tur: "haftalik" })).toMatchObject({ gunler: [1], saat: "08:15" });
  });

  it("tek seferlikte tarih yoksa hata, varsa epoch saniye verir", () => {
    expect(draftPayload({ ...taslak, tur: "bir_kez" })).toBe("Tek seferlik görev için tarih ve saat seç.");
    const payload = draftPayload({ ...taslak, tur: "bir_kez", tarih: "2026-10-07" }) as Record<string, unknown>;
    expect(payload.zaman).toBe(Math.floor(new Date("2026-10-07T08:15").getTime() / 1000));
  });
});

describe("ScheduleScreen", () => {
  it("görevleri listeler; duraklatır, siler ve şimdi çalıştırır", async () => {
    const { client, request } = fakeClient();
    const onRunNow = vi.fn(async () => undefined);
    render(<ScheduleScreen client={client} defaultRoot="/proje" onRunNow={onRunNow} />);
    expect(await screen.findByText("Sabah raporu")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Duraklat" }));
    await waitFor(() => expect(request).toHaveBeenCalledWith("zamanlama.etkin", { id: "a1", etkin: false }));
    fireEvent.click(screen.getByRole("button", { name: "Şimdi çalıştır" }));
    await waitFor(() => expect(onRunNow).toHaveBeenCalledWith(gorev));
    fireEvent.click(screen.getByRole("button", { name: "Sabah raporu görevini sil" }));
    await waitFor(() => expect(request).toHaveBeenCalledWith("zamanlama.sil", { id: "a1" }));
  });

  it("yeni görevi açık projenin klasörüyle kaydeder", async () => {
    const { client, request } = fakeClient([]);
    render(<ScheduleScreen client={client} defaultRoot="/proje" onRunNow={vi.fn()} />);
    expect(await screen.findByText("Henüz zamanlanmış görev yok.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Yeni görev" }));
    fireEvent.change(screen.getByLabelText("Görev"), { target: { value: "Fiyatları güncelle" } });
    fireEvent.change(screen.getByLabelText("Saat"), { target: { value: "07:30" } });
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));
    await waitFor(() => expect(request).toHaveBeenCalledWith("zamanlama.kaydet", {
      baslik: "", gorev: "Fiyatları güncelle", kok: "/proje", tur: "gunluk", saat: "07:30",
    }));
    await waitFor(() => expect(screen.queryByRole("form")).toBeNull());
  });

  it("çekirdeğin ret mesajını gösterir ve formu açık bırakır", async () => {
    const request = vi.fn(async (name: string) =>
      name === "zamanlama.liste" ? { ok: true, gorevler: [] } : { ok: false, metin: "Aralık en az 15 dakika olmalı." });
    render(<ScheduleScreen client={{ request }} defaultRoot="/proje" onRunNow={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Yeni görev" }));
    fireEvent.change(screen.getByLabelText("Görev"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Aralık en az 15 dakika olmalı.");
    expect(screen.getByRole("form")).toBeTruthy();
  });
});

describe("useScheduleRunner", () => {
  const occurrence = { occurrence_id: "a".repeat(64), schedule_id: "a1", due_at: 123, title: "Sabah raporu", task: "Stok raporunu çıkar", root: "/proje", task_id: null };
  const receipt = { occurrenceId: occurrence.occurrence_id, taskId: `schedule-${occurrence.occurrence_id}`, status: "queued" as const };
  function requests(ack = true) {
    return vi.fn(async (name: string) => name === "zamanlama.teslim_bekleyenler" ? { ok: true, teslimler: [occurrence] } : name === "zamanlama.teslim_onayla" ? { ok: ack } : { ok: true, gorevler: [gorev] });
  }
  it("otomatik vade native sohbet açmaz; kalıcı makbuzdan sonra ack verir", async () => {
    const request = requests(); const create = vi.fn(async () => "s1"); const send = vi.fn(() => true); const deliver = vi.fn(async () => receipt);
    renderHook(() => useScheduleRunner({ client: { request }, create, send, sessions: {}, deliveryClient: { deliver } }));
    await waitFor(() => expect(request).toHaveBeenCalledWith("zamanlama.teslim_onayla", { occurrence_id: occurrence.occurrence_id, task_id: receipt.taskId }));
    expect(deliver).toHaveBeenCalledWith(occurrence); expect(create).not.toHaveBeenCalled(); expect(send).not.toHaveBeenCalled();
  });
  it("Kits veya geçerli makbuz yoksa pending korunur", async () => {
    const request = requests(); const create = vi.fn(async () => "s1");
    const { unmount } = renderHook(() => useScheduleRunner({ client: { request }, create, send: () => true, sessions: {} }));
    await waitFor(() => expect(request).toHaveBeenCalledWith("zamanlama.teslim_bekleyenler", {}));
    expect(create).not.toHaveBeenCalled(); expect(request.mock.calls.some(([name]) => name === "zamanlama.teslim_onayla")).toBe(false); unmount();
    renderHook(() => useScheduleRunner({ client: { request }, create, send: () => true, sessions: {}, deliveryClient: { deliver: async () => ({ ...receipt, occurrenceId: "b".repeat(64) }) } }));
    await new Promise((done) => setTimeout(done, 0)); expect(request.mock.calls.some(([name]) => name === "zamanlama.teslim_onayla")).toBe(false);
  });
  it("ack hatasından sonra aynı occurrence tekrar teslim edilir", async () => {
    vi.useFakeTimers(); const request = requests(false); const deliver = vi.fn(async () => receipt);
    const client = { request }; const deliveryClient = { deliver };
    renderHook(() => useScheduleRunner({ client, create: async () => "s1", send: () => true, sessions: {}, deliveryClient }));
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(deliver).toHaveBeenCalledTimes(2); expect(deliver.mock.calls.map(([value]) => value.occurrence_id)).toEqual([occurrence.occurrence_id, occurrence.occurrence_id]);
  });
  it("Şimdi çalıştır eski native sohbet yolunu korur", async () => {
    const create = vi.fn(async () => "s1"); const send = vi.fn(() => true); const started = vi.fn();
    const { result, rerender } = renderHook(({ sessions }) => useScheduleRunner({ client: null, create, send, sessions, onStarted: started }), { initialProps: { sessions: {} as Record<string, { status: string }> } });
    await act(async () => { await result.current.runNow(gorev); });
    expect(create).toHaveBeenCalledWith({ mode: "kod", root: "/proje", title: "Sabah raporu" }); expect(send).not.toHaveBeenCalled(); rerender({ sessions: { s1: { status: "ready" } } });
    expect(send).toHaveBeenCalledWith("s1", gorev.gorev); expect(started).toHaveBeenCalledWith(gorev);
  });
  it("bekleyen makbuz sırasında paralel poll ve aynı occurrence çoğalmaz", async () => {
    vi.useFakeTimers(); let resolve!: (value: typeof receipt | null) => void;
    const request = vi.fn(async (name: string) => name === "zamanlama.teslim_bekleyenler" ? { ok: true, teslimler: [occurrence, occurrence] } : { ok: true });
    const deliver = vi.fn(() => new Promise<typeof receipt | null>((done) => { resolve = done; }));
    const client = { request }; const deliveryClient = { deliver };
    renderHook(() => useScheduleRunner({ client, deliveryClient, create: async () => "s1", send: () => true, sessions: {} }));
    await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
    expect(deliver).toHaveBeenCalledOnce(); expect(request).toHaveBeenCalledTimes(2);
    await act(async () => { resolve(receipt); });
    expect(deliver).toHaveBeenCalledOnce(); expect(request).toHaveBeenCalledWith("zamanlama.teslim_onayla", { occurrence_id: occurrence.occurrence_id, task_id: receipt.taskId });
  });
  it("hook kapanınca geç kalan makbuz ack üretmez", async () => {
    let resolve!: (value: typeof receipt | null) => void;
    const request = requests(); const deliver = vi.fn(() => new Promise<typeof receipt | null>((done) => { resolve = done; })); const client = { request }; const deliveryClient = { deliver };
    const { unmount } = renderHook(() => useScheduleRunner({ client, deliveryClient, create: async () => "s1", send: () => true, sessions: {} }));
    await waitFor(() => expect(deliver).toHaveBeenCalledOnce()); unmount(); await act(async () => { resolve(receipt); });
    expect(request.mock.calls.some(([name]) => name === "zamanlama.teslim_onayla")).toBe(false);
  });
  it("makbuz timeout pending kaydı sonraki yoklamada yeniden dener", async () => {
    vi.useFakeTimers(); const request = requests(); const deliver = vi.fn(async () => null); const client = { request }; const deliveryClient = { deliver };
    renderHook(() => useScheduleRunner({ client, deliveryClient, create: async () => "s1", send: () => true, sessions: {} }));
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); }); expect(deliver).toHaveBeenCalledTimes(2); expect(request.mock.calls.some(([name]) => name === "zamanlama.teslim_onayla")).toBe(false);
  });

});
