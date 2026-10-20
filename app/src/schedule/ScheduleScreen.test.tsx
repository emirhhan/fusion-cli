import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
    expect(describeSchedule({ tur: "haftalik", saat: "09:00", gunler: [0, 1, 2, 3, 4] })).toBe("Hafta içi 09:00");
    expect(describeSchedule({ tur: "haftalik", saat: "16:00", gunler: [4] })).toBe("Her Cuma 16:00");
    expect(describeSchedule({ tur: "haftalik", saat: "08:00", gunler: [0, 1, 2, 3, 4, 5, 6] })).toBe("Her gün 08:00");
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
    expect(await screen.findByText("Sabah raporu", { selector: ".schedule__title" })).toBeTruthy();
    fireEvent.click(screen.getByRole("switch", { name: "Duraklat" }));
    await waitFor(() => expect(request).toHaveBeenCalledWith("zamanlama.etkin", { id: "a1", etkin: false }));
    fireEvent.click(screen.getByRole("button", { name: "Şimdi çalıştır" }));
    await waitFor(() => expect(onRunNow).toHaveBeenCalledWith(gorev));
    fireEvent.click(screen.getByRole("button", { name: "Sabah raporu görevini sil" }));
    await waitFor(() => expect(request).toHaveBeenCalledWith("zamanlama.sil", { id: "a1" }));
  });

  it("yeni görevi açık projenin klasörüyle kaydeder", async () => {
    const { client, request } = fakeClient([]);
    render(<ScheduleScreen client={client} defaultRoot="/proje" onRunNow={vi.fn()} />);
    expect(await screen.findByText("Henüz zamanlanmış görev yok.", { selector: ".schedule__empty-title" })).toBeTruthy();
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

describe("ScheduleScreen — Claude düzeni", () => {
  it("kartta istem özeti, sıklık, sıradaki zaman ve klasör görünür; anahtar açıktır", async () => {
    const { client } = fakeClient();
    render(<ScheduleScreen client={client} defaultRoot="/proje" onRunNow={vi.fn()} />);
    expect(await screen.findByText("Stok raporunu çıkar")).toBeTruthy();
    expect(screen.getByText("Her gün 09:00")).toBeTruthy();
    expect(screen.getByText(/^Sıradaki /)).toBeTruthy();
    expect(screen.getByText("proje")).toBeTruthy();
    expect(screen.getByRole("switch", { name: "Duraklat" }).getAttribute("aria-checked")).toBe("true");
  });

  it("duraklatılmış görev kapalı anahtar ve 'Duraklatıldı' ile görünür", async () => {
    const paused = { ...gorev, etkin: false };
    const { client } = fakeClient([paused, { ...gorev, id: "a2", baslik: "Haftalık özet" }]);
    render(<ScheduleScreen client={client} defaultRoot="/proje" onRunNow={vi.fn()} />);
    expect(await screen.findByText("Duraklatıldı")).toBeTruthy();
    expect(screen.getByRole("switch", { name: "Sürdür" }).getAttribute("aria-checked")).toBe("false");
  });

  it("boşken kronometre çizimi, çağrı düğmesi ve altında şablonlar görünür; şablon formu doldurur", async () => {
    const { client } = fakeClient([]);
    const { container } = render(<ScheduleScreen client={client} defaultRoot="/proje" onRunNow={vi.fn()} />);
    expect(await screen.findByText("Henüz zamanlanmış görev yok.", { selector: ".schedule__empty-title" })).toBeTruthy();
    expect(container.querySelector(".schedule__stopwatch")).not.toBeNull();
    const templates = within(screen.getByRole("list", { name: "Şablonlar" }));
    expect(templates.getAllByRole("button").length).toBeGreaterThanOrEqual(6);
    expect(templates.getByText("Hafta içi 09:00")).toBeTruthy();
    fireEvent.click(templates.getByRole("button", { name: /Sabah özeti/ }));
    expect(screen.getByRole("dialog", { name: "Yeni zamanlanmış görev" })).toBeTruthy();
    expect((screen.getByLabelText("Başlık") as HTMLInputElement).value).toBe("Sabah özeti");
    expect((screen.getByLabelText("Görev") as HTMLTextAreaElement).value).toContain("son değişiklikleri");
    expect((screen.getByLabelText("Saat") as HTMLInputElement).value).toBe("09:00");
    expect(screen.getByRole("button", { name: "Pzt", pressed: true })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Cmt", pressed: false })).toBeTruthy();
  });

  it("şablonla açılan formu kaydetmek çekirdeğe şablonun takvimini gönderir", async () => {
    const { client, request } = fakeClient([]);
    render(<ScheduleScreen client={client} defaultRoot="/proje" onRunNow={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: /Bağımlılık güncelleme kontrolü/ }));
    fireEvent.click(screen.getByRole("button", { name: "Kaydet" }));
    await waitFor(() => expect(request).toHaveBeenCalledWith("zamanlama.kaydet", expect.objectContaining({
      baslik: "Bağımlılık güncelleme kontrolü", kok: "/proje", tur: "haftalik", saat: "09:00", gunler: [0],
    })));
  });

  it("Şablonlar sekmesi görev varken de şablonları gösterir; Görevlerim'e dönülür", async () => {
    const { client } = fakeClient();
    render(<ScheduleScreen client={client} defaultRoot="/proje" onRunNow={vi.fn()} />);
    await screen.findByText("Sabah raporu", { selector: ".schedule__title" });
    fireEvent.click(screen.getByRole("tab", { name: "Şablonlar" }));
    expect(screen.getByRole("list", { name: "Şablonlar" })).toBeTruthy();
    expect(screen.queryByRole("list", { name: "Zamanlanmış görevler" })).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Görevlerim" }));
    expect(screen.getByRole("list", { name: "Zamanlanmış görevler" })).toBeTruthy();
  });

  it("arama, süzgeç ve sıralama görev listesini değiştirir", async () => {
    const tasks = [
      { ...gorev, id: "a", baslik: "Zebra", sonraki: 1_800_000_300 },
      { ...gorev, id: "b", baslik: "Armut", sonraki: 1_800_000_100 },
      { ...gorev, id: "c", baslik: "Kaplan", etkin: false },
    ];
    const { client } = fakeClient(tasks);
    render(<ScheduleScreen client={client} defaultRoot="/proje" onRunNow={vi.fn()} />);
    await screen.findByText("Zebra", { selector: ".schedule__title" });
    const titles = () => within(screen.getByRole("list", { name: "Zamanlanmış görevler" })).getAllByRole("listitem").map((item) => item.querySelector(".schedule__title")?.textContent);
    expect(titles()).toEqual(["Armut", "Zebra", "Kaplan"]); // sıradaki zamana göre, duraklatılan sonda
    fireEvent.click(screen.getByRole("button", { name: "Sırala" }));
    fireEvent.click(screen.getByRole("menuitemradio", { name: "Ada göre" }));
    expect(titles()).toEqual(["Armut", "Kaplan", "Zebra"]);
    fireEvent.click(screen.getByRole("button", { name: "Süz" }));
    fireEvent.click(screen.getByRole("menuitemradio", { name: "Duraklatılan" }));
    expect(titles()).toEqual(["Kaplan"]);
    fireEvent.click(screen.getByRole("button", { name: "Süz" }));
    fireEvent.click(screen.getByRole("menuitemradio", { name: "Tümü" }));
    fireEvent.click(screen.getByRole("button", { name: "Ara" }));
    fireEvent.change(screen.getByLabelText("Görevlerde ara"), { target: { value: "zeb" } });
    expect(titles()).toEqual(["Zebra"]);
    fireEvent.change(screen.getByLabelText("Görevlerde ara"), { target: { value: "yok böyle" } });
    expect(screen.getByText("Aramana ya da süzgecine uyan görev yok.")).toBeTruthy();
  });

  it("diyalog Esc ve Vazgeç ile kapanır", async () => {
    const { client } = fakeClient([]);
    render(<ScheduleScreen client={client} defaultRoot="/proje" onRunNow={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "İlk görevini oluştur" }));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Yeni görev" }));
    fireEvent.click(screen.getByRole("button", { name: "Vazgeç" }));
    expect(screen.queryByRole("dialog")).toBeNull();
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

it("zamanlananlar kendi menüsünde arama ve yeni görev sunar", async () => {
 const { client } = fakeClient();
 render(<ScheduleScreen client={client} defaultRoot="/proje" onRunNow={vi.fn()} />);
 const sidebar = screen.getByRole("complementary", { name: "Zamanlananlar menüsü" });
 expect(within(sidebar).getByRole("heading", { name: "Zamanlananlar" })).toBeTruthy();
 expect(within(sidebar).getByText("Yaklaşanlar")).toBeTruthy();
 await within(sidebar).findByRole("button", { name: /Sabah raporu/ });
 fireEvent.click(within(sidebar).getByRole("button", { name: "Ara" }));
 fireEvent.change(within(sidebar).getByLabelText("Görevlerde ara"), { target: { value: "eşleşmez" } });
 expect(within(sidebar).getByText("Görev bulunamadı.")).toBeTruthy();
 fireEvent.click(within(sidebar).getByRole("button", { name: "Yeni görev" }));
 expect(screen.getByRole("dialog")).toBeTruthy();
});

it("görev menüsündeki bağlantı gerçek görev kartına odaklanır", async () => {
 const { client } = fakeClient();
 render(<ScheduleScreen client={client} defaultRoot="/proje" onRunNow={vi.fn()} />);
 const sidebar = screen.getByRole("complementary", { name: "Zamanlananlar menüsü" });
 const link = await within(sidebar).findByRole("button", { name: "Sabah raporu" });
 const card = document.getElementById("scheduled-task-a1")!;
 const scroll = vi.fn();
 card.scrollIntoView = scroll;
 fireEvent.click(link);
 await waitFor(() => expect(document.activeElement).toBe(card));
 expect(scroll).toHaveBeenCalledWith({ block: "nearest" });
});
