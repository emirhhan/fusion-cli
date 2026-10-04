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
  it("vadesi gelen görev için sohbet açar ve oturum hazır olunca gönderir", async () => {
    const request = vi.fn(async () => ({ ok: true, gorevler: [gorev] }));
    const create = vi.fn(async () => "s1");
    const send = vi.fn(() => true);
    const started = vi.fn();
    const { rerender } = renderHook(
      ({ sessions }: { sessions: Record<string, { status: string }> }) =>
        useScheduleRunner({ client: { request }, create, send, sessions, onStarted: started }),
      { initialProps: { sessions: {} } },
    );
    await waitFor(() => expect(create).toHaveBeenCalledWith({ mode: "kod", root: "/proje", title: "Sabah raporu" }));
    expect(send).not.toHaveBeenCalled();
    rerender({ sessions: { s1: { status: "ready" } } });
    expect(send).toHaveBeenCalledWith("s1", "Stok raporunu çıkar");
    expect(started).toHaveBeenCalledWith(gorev);
    rerender({ sessions: { s1: { status: "ready" } } });
    expect(send).toHaveBeenCalledTimes(1);
  });

  it("çekirdek yokken yoklamaz, hata verirse çökmeden yeniden dener", async () => {
    vi.useFakeTimers();
    const request = vi.fn().mockRejectedValueOnce(new Error("kapalı")).mockResolvedValue({ ok: true, gorevler: [] });
    const create = vi.fn(async () => "s1");
    renderHook(() => useScheduleRunner({ client: null, create, send: () => true, sessions: {} }));
    renderHook(() => useScheduleRunner({ client: { request }, create, send: () => true, sessions: {} }));
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(request).toHaveBeenCalledTimes(2);
    expect(create).not.toHaveBeenCalled();
  });
});
