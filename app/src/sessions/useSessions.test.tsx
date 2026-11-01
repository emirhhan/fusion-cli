import { saveSubmission } from "./submissionPersistence";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useSessions } from "./useSessions";
import { GOAL_WAITING_USER } from "../goal/goalResult";
import { initialSessionState, sessionReducer } from "./store";
import { DEFAULT_TITLE } from "./title";
import type { SessionClosedEvent, SessionLineEvent, SessionTransport } from "./types";

afterEach(() => localStorage.clear());

it("geri yüklenen ara anlatımın işaretini korur", async () => {
  const fake = fakeTransport([
    { rol: "kullanici", metin: "Projeyi yap" },
    { rol: "asistan", metin: "Dosyayı okuyorum", ara: true },
    { rol: "asistan", metin: "Bitti" },
  ]);
  const { result } = renderHook(() => useSessions(fake.transport));
  await waitFor(() => expect(result.current.activeSession?.messages).toHaveLength(3));
  expect(result.current.activeSession?.messages[1].ara).toBe(true);
  expect(result.current.activeSession?.messages[2].ara).toBeUndefined();
});

function fakeTransport(
  initialHistory: { rol: "kullanici" | "asistan"; metin: string; ara?: boolean }[] = [],
  resumedHistory = initialHistory,
  //: Sırayla dönecek `oturum.durum` ölçüleri; biterse boş ölçü döner.
  baglamlar: Record<string, number>[] = [],
  //: Sırayla dönecek maliyetler (USD); biterse `undefined` döner (eski
  //: çekirdek alanı hiç göndermeyebilir, `maliyetOku` bunu `null` okur).
  maliyetler: (number | undefined)[] = [],
) {
  const durumIstekleri: string[] = [];
  const baslikIstekleri: string[] = [];
  let lineHandler: ((event: SessionLineEvent) => void) | null = null;
  let closedHandler: ((event: SessionClosedEvent) => void) | null = null;
  const sent: { id: string; line: string }[] = [];
  const basladi: { oturum: string; sohbet: string }[] = [];
  const unlistenLine = vi.fn();
  const unlistenClosed = vi.fn();
  const transport: SessionTransport = {
    create: vi.fn(async (id, root) => ({
      oturum_id: id,
      kok: root ?? "/aktif",
      pid: id === "varsayilan" ? 41 : 42,
      durum: "calisiyor",
      kapanis_nedeni: null,
    })),
    send: vi.fn(async (id, line) => {
      const request = JSON.parse(line) as { id: string; ad: string; veri?: Record<string, unknown> };
      if (request.ad === "oturum.baslat") {
        basladi.push({ oturum: id, sohbet: String(request.veri?.sohbet_id ?? "") });
        queueMicrotask(() => lineHandler?.({
          oturum_id: id,
          satir: JSON.stringify({ tip: "sonuc", id: request.id, veri: { ok: true } }),
        }));
        return;
      }
      if (request.ad === "oturum.durum") {
        durumIstekleri.push(id);
        queueMicrotask(() => lineHandler?.({
          oturum_id: id,
          satir: JSON.stringify({
            tip: "sonuc",
            id: request.id,
            veri: {
              ok: true,
              baglam: baglamlar.shift() ?? { kullanilan: 0, sinir: 24000, yuzde: 0 },
              maliyet_usd: maliyetler.shift(),
            },
          }),
        }));
        return;
      }
      if (request.ad === "sohbet.baslik") {
        baslikIstekleri.push(String(request.veri?.metin ?? ""));
        queueMicrotask(() => lineHandler?.({
          oturum_id: id,
          satir: JSON.stringify({
            tip: "sonuc",
            id: request.id,
            veri: { ok: true, baslik: "Tarayıcı oyunu yaz" },
          }),
        }));
        return;
      }
      if (request.ad === "sohbet.listele") {
        queueMicrotask(() => lineHandler?.({
          oturum_id: id,
          satir: JSON.stringify({ tip: "sonuc", id: request.id, veri: { ok: true, sohbetler: [] } }),
        }));
        return;
      }
      if (request.ad === "sohbet.tasi") {
        sent.push({ id, line });
        queueMicrotask(() => lineHandler?.({
          oturum_id: id,
          satir: JSON.stringify({ tip: "sonuc", id: request.id, veri: { ok: true } }),
        }));
        return;
      }
      if (request.ad === "oturum.gecmis") {
        queueMicrotask(() => lineHandler?.({
          oturum_id: id,
          satir: JSON.stringify({
            tip: "sonuc",
            id: request.id,
            veri: { ok: true, mesajlar: id === "varsayilan" ? initialHistory : resumedHistory },
          }),
        }));
        return;
      }
      sent.push({ id, line });
    }),
    close: vi.fn(async () => undefined),
    list: vi.fn(async () => []),
    onLine: vi.fn(async (handler) => {
      lineHandler = handler;
      return unlistenLine;
    }),
    onClosed: vi.fn(async (handler) => {
      closedHandler = handler;
      return unlistenClosed;
    }),
  };
  return {
    transport,
    sent,
    basladi,
    durumIstekleri,
    baslikIstekleri,
    emitLine: (event: SessionLineEvent) => lineHandler?.(event),
    emitResult: (sessionId: string, requestId: string, veri: Record<string, unknown>) => lineHandler?.({
      oturum_id: sessionId,
      satir: JSON.stringify({ tip: "sonuc", id: requestId, veri }),
    }),
    emitClosed: (event: SessionClosedEvent) => closedHandler?.(event),
    unlistenLine,
    unlistenClosed,
  };
}

describe("useSessions", () => {
  it("yeni sohbeti de eski görevi de kod kipinde başlatır", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());
    let newId = "";
    await act(async () => { newId = await result.current.create({ root: "/Projects/example" }); });
    await act(async () => { await result.current.create({ id: "old-task", root: "/Projects/example" }); });
    const starts = vi.mocked(fake.transport.send).mock.calls.map(([, line]) => JSON.parse(line))
      .filter((request) => request.ad === "oturum.baslat");
    expect(starts.find((request) => request.veri.sohbet_id === newId)?.veri.kip).toBe("kod");
    expect(starts.find((request) => request.veri.sohbet_id === "old-task")?.veri.kip).toBe("kod");
    expect(localStorage.getItem(`fusion.session-mode.${newId}`)).toBe("kod");
  });

  it("açık sohbeti kapatıp hedef projede aynı kimlikle yeniden açar", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());
    await act(async () => { await result.current.create({ id: "chat-1", root: "/Projects/source" }); });
    await act(async () => { await result.current.move("chat-1", "/Projects/target"); });
    const moved = fake.sent.find(({ line }) => JSON.parse(line).ad === "sohbet.tasi");
    expect(JSON.parse(moved!.line).veri).toEqual({
      sohbet_id: "chat-1", kaynak_kok: "/Projects/source", hedef_kok: "/Projects/target",
    });
    expect(result.current.state.sessions["chat-1"].root).toBe("/Projects/target");
  });

  it("proje Fusion geçmişini varsayılan masaüstü konuşmasına yükler", async () => {
    const fake = fakeTransport([
      { rol: "kullanici", metin: "Eski oyun sorusu" },
      { rol: "asistan", metin: "Eski oyun yanıtı" },
    ]);
    const { result } = renderHook(() => useSessions(fake.transport));

    await waitFor(() => expect(result.current.activeSession?.messages).toEqual([
      { id: expect.any(String), rol: "kullanici", metin: "Eski oyun sorusu" },
      { id: expect.any(String), rol: "asistan", metin: "Eski oyun yanıtı" },
    ]));
  });

  it("sesli bağlamı ilk ve kuyruklu turda sözden ayrı tutar", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession?.status).toBe("ready"));
    act(() => {
      result.current.send("varsayilan", "Merhaba", [], true, {});
      result.current.send("varsayilan", "Diğerini anlat", [], true, { kesilen: "İlk seçenek" });
    });
    expect(result.current.state.sessions.varsayilan.messages.map((message) => message.metin))
      .toEqual(["Merhaba", "Diğerini anlat"]);
    await waitFor(() => expect(fake.sent).toHaveLength(1));
    expect(fake.baslikIstekleri).toEqual(["Merhaba"]);
    expect(JSON.parse(fake.sent[0].line).veri).toEqual({ gorev: "Merhaba", ekler: [], sesli: {}, gonderim_id: expect.any(String) });
    act(() => fake.emitResult("varsayilan", JSON.parse(fake.sent[0].line).id, { ok: true }));
    await waitFor(() => expect(fake.sent).toHaveLength(2));
    expect(JSON.parse(fake.sent[1].line).veri).toEqual({
      gorev: "Diğerini anlat", ekler: [], sesli: { kesilen: "İlk seçenek" }, gonderim_id: expect.any(String),
    });
  });

  it("çalışırken yazılan mesajı KUYRUĞA alır, tur bitince gönderir", async () => {
    // Claude'daki davranış: iş sürerken yazılan mesaj kaybolmaz, sıraya girer.
    // Ölçüldü (17 Eylül denetimi): ikinci mesaj "zaten çalışan bir tur var" ile
    // reddediliyor ve kullanıcının yazdığı kayboluyordu.
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());

    act(() => {
      result.current.send("varsayilan", "ilk görev");
      result.current.send("varsayilan", "ikinci görev");
    });

    // İkisi de kullanıcı mesajı olarak görünür; çekirdeğe sırayla gider.
    expect(result.current.state.sessions.varsayilan.messages.map((m) => m.metin)).toEqual([
      "ilk görev",
      "ikinci görev",
    ]);
    // İlk tur çekirdeğe gitti; ikincisi sırada bekliyor.
    await waitFor(() => expect(fake.sent).toHaveLength(1));
    expect(JSON.parse(fake.sent[0].line).veri.gorev).toBe("ilk görev");

    // İlk tur bitince kuyruktaki mesaj kendiliğinden gönderilir.
    const ilkIstek = JSON.parse(fake.sent[0].line) as { id: string };
    act(() => fake.emitResult("varsayilan", ilkIstek.id, { ok: true, metin: "ilk cevap" }));

    await waitFor(() => expect(fake.sent).toHaveLength(2));
    expect(JSON.parse(fake.sent[1].line).veri.gorev).toBe("ikinci görev");
    // Kuyruktaki mesaj ikinci kez kullanıcı mesajı olarak eklenmez.
    expect(
      result.current.state.sessions.varsayilan.messages.filter((m) => m.rol === "kullanici"),
    ).toHaveLength(2);
  });

  it("açılışta ve tur bitince kalan bağlamı yeniden okur", async () => {
    // Geçmiş tur SONUNDA büyür/özetlenir; ölçü yalnız açılışta okunsaydı
    // gösterge ilk değerde donar ve sıkıştırma yine sürpriz olurdu.
    const fake = fakeTransport([], [], [
      { kullanilan: 1200, sinir: 24000, yuzde: 5 },
      { kullanilan: 22000, sinir: 24000, yuzde: 92 },
    ]);
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() =>
      expect(result.current.activeSession?.baglam).toEqual({ kullanilan: 1200, sinir: 24000, yuzde: 5 }),
    );

    act(() => { result.current.send("varsayilan", "uzun bir iş"); });
    await waitFor(() => expect(fake.sent).toHaveLength(1));
    const tur = JSON.parse(fake.sent[0].line) as { id: string };
    // Tur sürerken ölçü değişmez; yeni okuma tur bitişini bekler.
    expect(fake.durumIstekleri).toHaveLength(1);
    act(() => fake.emitResult("varsayilan", tur.id, { ok: true, metin: "bitti" }));

    await waitFor(() => expect(result.current.activeSession?.baglam?.yuzde).toBe(92));
    expect(fake.durumIstekleri).toHaveLength(2);
  });

  it("açılışta ve tur bitince toplam maliyeti de yeniden okur", async () => {
    const fake = fakeTransport([], [], [], [0.01, 0.05]);
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession?.maliyetUsd).toBe(0.01));

    act(() => { result.current.send("varsayilan", "iş"); });
    await waitFor(() => expect(fake.sent).toHaveLength(1));
    const tur = JSON.parse(fake.sent[0].line) as { id: string };
    act(() => fake.emitResult("varsayilan", tur.id, { ok: true, metin: "bitti" }));

    await waitFor(() => expect(result.current.activeSession?.maliyetUsd).toBe(0.05));
  });

  it("çekirdek maliyet alanını hiç göndermezse null kalır, yanlış sıfır göstermez", async () => {
    const fake = fakeTransport([], [], [], [undefined]);
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(fake.durumIstekleri.length).toBeGreaterThan(0));

    expect(result.current.activeSession?.maliyetUsd).toBeNull();
  });

  it("ek yollarını yalnız çekirdek görev bağlamına ekler, kullanıcı mesajını temiz tutar", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());

    act(() => result.current.send("varsayilan", "Bu görseli incele", [
      { path: "/Users/test/Desktop/ornek.png", name: "ornek.png", kind: "image" },
    ]));
    await waitFor(() => expect(fake.sent).toHaveLength(1));
    const request = JSON.parse(fake.sent[0].line);
    expect(request.veri.gorev).toBe("Bu görseli incele");
    expect(request.veri.ekler).toEqual([
      { path: "/Users/test/Desktop/ornek.png", name: "ornek.png", kind: "image" },
    ]);
    expect(result.current.state.sessions.varsayilan.messages[0].metin).toBe("Bu görseli incele");
  });

  it("slash komutunu tur yerine komut.calistir ile yürütür", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());

    let command!: Promise<Record<string, unknown>>;
    act(() => { command = result.current.runCommand("varsayilan", "/mcp github"); });
    await waitFor(() => expect(fake.sent).toHaveLength(1));
    const request = JSON.parse(fake.sent[0].line);
    expect(request.ad).toBe("komut.calistir");
    expect(request.veri).toEqual({ ad: "mcp", arguman: "github" });
    act(() => fake.emitLine({
      oturum_id: "varsayilan",
      satir: JSON.stringify({ tip: "sonuc", id: request.id, veri: { ok: true, metin: "MCP hazır" } }),
    }));
    await act(async () => { await expect(command).resolves.toMatchObject({ ok: true }); });
    expect(result.current.state.sessions.varsayilan.messages.at(-1)?.metin).toBe("MCP hazır");
  });

  it("/worktree sonucu kök bildirirse sekmenin kökü güncellenir (P-037)", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());
    const eskiKok = result.current.state.sessions.varsayilan.root;

    let command!: Promise<Record<string, unknown>>;
    act(() => { command = result.current.runCommand("varsayilan", "/worktree ozellik"); });
    await waitFor(() => expect(fake.sent).toHaveLength(1));
    const request = JSON.parse(fake.sent[0].line);
    act(() => fake.emitLine({
      oturum_id: "varsayilan",
      satir: JSON.stringify({
        tip: "sonuc", id: request.id,
        veri: { ok: true, metin: "Çalışma ağacı hazır", kok: `${eskiKok}/.fusion/worktrees/ozellik` },
      }),
    }));
    await act(async () => { await expect(command).resolves.toMatchObject({ ok: true }); });
    expect(result.current.state.sessions.varsayilan.root).toBe(`${eskiKok}/.fusion/worktrees/ozellik`);
  });

  it("/rewind sonucu kalan geçmişi verirse sohbet panosu ona kesilir (P-004)", async () => {
    const fake = fakeTransport([
      { rol: "kullanici", metin: "bir" },
      { rol: "asistan", metin: "a-bir" },
      { rol: "kullanici", metin: "iki" },
      { rol: "asistan", metin: "a-iki" },
    ]);
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession?.messages).toHaveLength(4));

    let command!: Promise<Record<string, unknown>>;
    act(() => { command = result.current.runCommand("varsayilan", "/rewind 2 konusma"); });
    await waitFor(() => expect(fake.sent).toHaveLength(1));
    const request = JSON.parse(fake.sent[0].line);
    act(() => fake.emitResult("varsayilan", request.id, {
      ok: true,
      metin: "Konuşma 2. turun başına sarıldı (2 mesaj kaldı).",
      gecmis: [{ rol: "kullanici", metin: "bir" }, { rol: "asistan", metin: "a-bir" }],
    }));
    await act(async () => { await command; });

    expect(result.current.state.sessions.varsayilan.messages.map((message) => message.metin)).toEqual([
      "bir",
      "a-bir",
      "Konuşma 2. turun başına sarıldı (2 mesaj kaldı).",
    ]);
  });

  it("tur sonucu kök bildirirse (enter_worktree aracı) sekmenin kökü güncellenir (P-037)", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());
    const eskiKok = result.current.state.sessions.varsayilan.root;

    act(() => { result.current.send("varsayilan", "ayrı worktree'de dene"); });
    await waitFor(() => expect(fake.sent.map((item) => JSON.parse(item.line).ad)).toContain("tur.calistir"));
    const turn = fake.sent.map((item) => JSON.parse(item.line)).find((item) => item.ad === "tur.calistir");
    act(() => fake.emitResult("varsayilan", turn.id, {
      ok: true,
      metin: "tamam",
      kok: `${eskiKok}/.fusion/worktrees/ajan`,
    }));

    await waitFor(() => expect(result.current.state.sessions.varsayilan.root).toBe(`${eskiKok}/.fusion/worktrees/ajan`));
  });

  it("makro komutunun hazırladığı görevi hemen tur olarak başlatır", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());

    let command!: Promise<Record<string, unknown>>;
    act(() => { command = result.current.runCommand("varsayilan", "/goal oyunu bitir"); });
    await waitFor(() => expect(fake.sent).toHaveLength(1));
    const request = JSON.parse(fake.sent[0].line);
    act(() => fake.emitResult("varsayilan", request.id, {
      ok: true,
      metin: "goal çalıştırılıyor…",
      gorev: "oyunu bitir",
    }));
    await act(async () => { await command; });

    await waitFor(() => expect(fake.sent).toHaveLength(2));
    const turn = JSON.parse(fake.sent[1].line);
    expect(turn.ad).toBe("tur.calistir");
    expect(turn.veri.gorev).toBe("oyunu bitir");
    expect(result.current.state.sessions.varsayilan.running).toBe(true);
    const userMessages = result.current.state.sessions.varsayilan.messages
      .filter((message) => message.rol === "kullanici")
      .map((message) => message.metin);
    expect(userMessages).toEqual(["/goal oyunu bitir"]);
    expect(result.current.state.sessions.varsayilan.messages.some(
      (message) => message.rol === "asistan" && message.metin === "goal çalıştırılıyor…",
    )).toBe(false);
  });

  it("/goal henüz karşılanmadıysa devam turunu kullanıcı mesajı yazmadan sürer (P-058)", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());

    act(() => { result.current.send("varsayilan", "testleri düzelt"); });
    await waitFor(() => expect(fake.sent.map((item) => JSON.parse(item.line).ad)).toContain("tur.calistir"));
    const ilk = fake.sent.map((item) => JSON.parse(item.line)).find((item) => item.ad === "tur.calistir");
    act(() => fake.emitResult("varsayilan", ilk.id, {
      ok: true,
      metin: "bir test kaldı",
      hedef: { eylem: "devam", metin: "◎ Hedef henüz karşılanmadı — bir test kırık · sürdürülüyor (1/20)" },
      hedef_devam: "Hedef henüz karşılanmadı. Sürdür.",
    }));

    await waitFor(() => expect(
      fake.sent.map((item) => JSON.parse(item.line)).filter((item) => item.ad === "tur.calistir"),
    ).toHaveLength(2));
    const ikinci = fake.sent.map((item) => JSON.parse(item.line)).filter((item) => item.ad === "tur.calistir")[1];
    expect(ikinci.veri.gorev).toBe("Hedef henüz karşılanmadı. Sürdür.");
    const mesajlar = result.current.state.sessions.varsayilan.messages;
    expect(mesajlar.filter((message) => message.rol === "kullanici").map((message) => message.metin))
      .toEqual(["testleri düzelt"]);
    expect(mesajlar.some((message) => message.ara && message.metin.startsWith("◎ Hedef"))).toBe(true);
  });

  it("/goal devam zincirinde sohbet arada boşta görünmez (Zamanlananlar bitişi erken tetiklenmez)", async () => {
    const fake = fakeTransport();
    const gorulen: (boolean | undefined)[] = [];
    const { result } = renderHook(() => {
      const value = useSessions(fake.transport);
      gorulen.push(value.state.sessions.varsayilan?.running);
      return value;
    });
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());
    const turlar = () => fake.sent.map((item) => JSON.parse(item.line)).filter((item) => item.ad === "tur.calistir");

    act(() => { result.current.send("varsayilan", "testleri düzelt"); });
    await waitFor(() => expect(turlar()).toHaveLength(1));
    const basla = gorulen.lastIndexOf(true);
    act(() => fake.emitResult("varsayilan", turlar()[0].id, {
      ok: true, metin: "bir test kaldı", hedef: { eylem: "devam", metin: "◎" }, hedef_devam: "Sürdür.",
    }));
    await waitFor(() => expect(turlar()).toHaveLength(2));

    expect(gorulen.slice(basla)).not.toContain(false);
  });

  it("/goal devamı sırada kullanıcı mesajı varken gönderilmez, mesaj önce koşar (P-058)", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());
    const turlar = () => fake.sent.map((item) => JSON.parse(item.line)).filter((item) => item.ad === "tur.calistir");

    act(() => { result.current.send("varsayilan", "testleri düzelt"); });
    await waitFor(() => expect(turlar()).toHaveLength(1));
    act(() => { result.current.send("varsayilan", "README'ye de bak"); });
    act(() => fake.emitResult("varsayilan", turlar()[0].id, {
      ok: true,
      metin: "bir test kaldı",
      hedef: { eylem: "devam", metin: "◎ Hedef henüz karşılanmadı — bir test kırık · sürdürülüyor (1/20)" },
      hedef_devam: "Hedef henüz karşılanmadı. Sürdür.",
    }));

    await waitFor(() => expect(turlar()).toHaveLength(2));
    expect(turlar()[1].veri.gorev).toBe("README'ye de bak");
    act(() => fake.emitResult("varsayilan", turlar()[1].id, { ok: true, metin: "baktım" }));
    await waitFor(() => expect(result.current.state.sessions.varsayilan.running).toBe(false));
    expect(turlar()).toHaveLength(2);
    expect(result.current.state.sessions.varsayilan.messages.some(
      (message) => message.ara && message.metin === GOAL_WAITING_USER,
    )).toBe(true);
  });

  it("/btw yan sorusu için ara komut mesajı göstermez", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());

    let command!: Promise<Record<string, unknown>>;
    act(() => { command = result.current.runCommand("varsayilan", "/btw Bu dosya ne yapıyor?"); });
    await waitFor(() => expect(fake.sent).toHaveLength(1));
    const request = JSON.parse(fake.sent[0].line);
    act(() => fake.emitResult("varsayilan", request.id, {
      ok: true,
      metin: "btw çalıştırılıyor…",
      gorev: "Ana görevi değiştirmeden şu yan soruyu yanıtla: Bu dosya ne yapıyor?",
    }));
    await act(async () => { await command; });

    await waitFor(() => expect(fake.sent).toHaveLength(2));
    expect(JSON.parse(fake.sent[1].line).ad).toBe("tur.calistir");
    expect(result.current.state.sessions.varsayilan.messages.map((message) => message.metin))
      .toEqual(["/btw Bu dosya ne yapıyor?"]);
  });

  it("her protokol satırını yalnız ait olduğu oturuma yönlendirir", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession?.id).toBe("varsayilan"));
    await act(async () => {
      await result.current.create({ id: "ikinci", title: "İkinci", root: "/ikinci" });
    });

    act(() => {
      result.current.send("varsayilan", "birinci görev");
      result.current.send("ikinci", "ikinci görev");
    });
    await waitFor(() => expect(fake.sent).toHaveLength(2));
    for (const item of fake.sent) {
      const request = JSON.parse(item.line) as { id: string };
      act(() => {
        fake.emitLine({
          oturum_id: item.id,
          satir: JSON.stringify({
            tip: "sonuc",
            id: request.id,
            veri: { metin: `${item.id} yanıtı` },
          }),
        });
      });
    }

    await waitFor(() => {
      expect(result.current.state.sessions.varsayilan.messages.at(-1)?.metin).toBe(
        "varsayilan yanıtı",
      );
      expect(result.current.state.sessions.ikinci.messages.at(-1)?.metin).toBe("ikinci yanıtı");
    });
  });

  it("yalnız kapanan oturumu çökmüş işaretler ve dinleyicileri temizler", async () => {
    const fake = fakeTransport();
    const { result, unmount } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());
    await act(async () => {
      await result.current.create({ id: "ikinci", title: "İkinci" });
    });

    act(() => fake.emitClosed({ oturum_id: "ikinci", neden: "çöktü" }));
    expect(result.current.state.sessions.ikinci.status).toBe("crashed");
    expect(result.current.state.sessions.varsayilan.status).toBe("ready");

    unmount();
    await waitFor(() => {
      expect(fake.unlistenLine).toHaveBeenCalledOnce();
      expect(fake.unlistenClosed).toHaveBeenCalledOnce();
    });
  });

  it("kullanıcının kapattığı oturumu çöküş olarak göstermez", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());

    await act(async () => {
      await result.current.close("varsayilan");
    });
    act(() => fake.emitClosed({ oturum_id: "varsayilan", neden: "süreç kapandı" }));

    expect(result.current.state.sessions.varsayilan.status).toBe("closed");
    expect(result.current.state.sessions.varsayilan.error).toBeNull();
  });

  it("geçmiş künyesini yeni konuşmanın kendi çekirdeğinde hazırlar", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());

    let resumePromise!: Promise<{ id: string; secretCount: number }>;
    act(() => {
      resumePromise = result.current.resume({
        source: "claude",
        sessionId: "claude-1",
        title: "Oyun konuşması",
      });
    });
    await waitFor(() => expect(fake.sent).toHaveLength(1));
    const sent = fake.sent[0];
    const request = JSON.parse(sent.line) as { id: string; ad: string; veri: Record<string, string> };
    expect(sent.id).not.toBe("varsayilan");
    expect(request.ad).toBe("gecmis.surdur");
    expect(request.veri).toEqual({ kaynak: "claude", oturum_id: "claude-1" });

    act(() => {
      fake.emitLine({
        oturum_id: sent.id,
        satir: JSON.stringify({
          tip: "sonuc",
          id: request.id,
          veri: { ok: true, kaynak: "claude", baslik: "Oyun konuşması", sir_sayisi: 2 },
        }),
      });
    });
    await act(async () => {
      await expect(resumePromise).resolves.toEqual({ id: sent.id, secretCount: 2 });
    });
    expect(result.current.state.sessions[sent.id].source).toBe("claude");
    expect(result.current.state.sessions[sent.id].title).toBe("[claude] Oyun konuşması");
  });

  it("devralınan geçmişi aynı çekirdek kimliğinde tutar ve model değişiminden sonra korur", async () => {
    const fake = fakeTransport([], [
      { rol: "kullanici", metin: "Eski oyun sorusu" },
      { rol: "asistan", metin: "Eski oyun yanıtı" },
    ]);
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());

    let resumePromise!: Promise<{ id: string; secretCount: number }>;
    act(() => {
      resumePromise = result.current.resume({
        source: "claude",
        sessionId: "claude-game",
        title: "Oyun konuşması",
      });
    });
    await waitFor(() => expect(fake.sent).toHaveLength(1));
    const resumedId = fake.sent[0].id;
    const request = JSON.parse(fake.sent[0].line) as { id: string; ad: string };
    act(() => {
      fake.emitLine({
        oturum_id: resumedId,
        satir: JSON.stringify({
          tip: "sonuc",
          id: request.id,
          veri: { ok: true, kaynak: "claude", baslik: "Oyun konuşması", sir_sayisi: 0 },
        }),
      });
    });
    await act(async () => {
      await expect(resumePromise).resolves.toEqual({ id: resumedId, secretCount: 0 });
    });
    await waitFor(() => expect(result.current.state.sessions[resumedId].messages).toEqual([
      { id: expect.any(String), rol: "kullanici", metin: "Eski oyun sorusu" },
      { id: expect.any(String), rol: "asistan", metin: "Eski oyun yanıtı" },
    ]));

    const command = result.current.runCommand(resumedId, "/model agent ikinci-model");
    await waitFor(() => expect(fake.sent).toHaveLength(2));
    const commandRequest = JSON.parse(fake.sent[1].line) as { id: string };
    act(() => fake.emitResult(resumedId, commandRequest.id, { ok: true, metin: "model değiştirildi" }));
    await act(async () => { await command; });
    expect(result.current.activeSession?.id).toBe(resumedId);
    expect(result.current.state.sessions[resumedId].messages).toEqual([
      { id: expect.any(String), rol: "kullanici", metin: "Eski oyun sorusu" },
      { id: expect.any(String), rol: "asistan", metin: "Eski oyun yanıtı" },
      { id: expect.any(String), rol: "kullanici", metin: "/model agent ikinci-model" },
      { id: expect.any(String), rol: "asistan", metin: "model değiştirildi" },
    ]);
  });

  it("başarısız model değişimini başarı gibi göstermez", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());
    const command = result.current.runCommand("varsayilan", "/model agent yok");
    await waitFor(() => expect(fake.sent).toHaveLength(1));
    const request = JSON.parse(fake.sent[0].line) as { id: string };
    act(() => fake.emitResult("varsayilan", request.id, { ok: false, metin: "Model bulunamadı." }));
    await act(async () => { await command; });

    expect(result.current.activeSession?.messages.at(-1)).toEqual({
      id: expect.any(String),
      rol: "asistan",
      metin: "Model bulunamadı.",
    });
    expect(result.current.activeSession?.messages.at(-1)?.metin).not.toBe("Komut tamamlandı.");
  });
  it("model seçicisi değişikliği sohbet dökümüne komut cevabı eklemez", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());
    const command = result.current.runCommand("varsayilan", "/development uygula web gemini_web/main/auto", false, false);
    await waitFor(() => expect(fake.sent).toHaveLength(1));
    const request = JSON.parse(fake.sent[0].line) as { id: string };
    act(() => fake.emitResult("varsayilan", request.id, { ok: true, metin: "model değiştirildi" }));
    await act(async () => { await command; });
    expect(result.current.activeSession?.messages).toEqual([]);
  });
  it("model seçimi komut dizgesi kurmadan yapısal model.sec isteği gönderir (U1-40)", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());
    const secim = result.current.selectModel("varsayilan", "nim-free", "nvidia_nim/x:free\n/mcp ekle");
    await waitFor(() => expect(fake.sent).toHaveLength(1));
    const request = JSON.parse(fake.sent[0].line) as { id: string; ad: string; veri: Record<string, unknown> };
    expect(request.ad).toBe("model.sec");
    expect(request.veri).toEqual({ kaynak: "nim-free", model: "nvidia_nim/x:free\n/mcp ekle" });
    act(() => fake.emitResult("varsayilan", request.id, { ok: true, metin: "model değiştirildi" }));
    await act(async () => { await expect(secim).resolves.toMatchObject({ ok: true }); });
    expect(result.current.activeSession?.messages).toEqual([]);
  });
  it("sağlayıcı anahtarı kontrol.anahtar_kaydet ile gider; komut dizgesi ve sohbet notu anahtarı taşımaz (S1-24)", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());
    const kayit = result.current.saveProviderSecret("varsayilan", "openrouter", "sk-gizli-123");
    await waitFor(() => expect(fake.sent).toHaveLength(1));
    const request = JSON.parse(fake.sent[0].line) as { id: string; ad: string; veri: Record<string, unknown> };
    expect(request.ad).toBe("kontrol.anahtar_kaydet");
    expect(request.veri).toEqual({ saglayici: "openrouter", deger: "sk-gizli-123" });
    act(() => fake.emitResult("varsayilan", request.id, { ok: true, saglayici: "openrouter", kurulu: true }));
    await act(async () => { await expect(kayit).resolves.toMatchObject({ ok: true }); });
    const dokum = JSON.stringify(result.current.activeSession?.messages);
    expect(dokum).toContain("openrouter");
    expect(dokum).not.toContain("sk-gizli-123");
  });

  it("elle yazılan /providers add komutunun anahtarı sohbet dökümünde maskelenir ama çekirdeğe aynen gider (S1-24)", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());
    const command = result.current.runCommand("varsayilan", "/providers add openrouter sk-gizli-999");
    await waitFor(() => expect(fake.sent).toHaveLength(1));
    const request = JSON.parse(fake.sent[0].line) as { id: string; veri: Record<string, unknown> };
    expect(request.veri).toEqual({ ad: "providers", arguman: "add openrouter sk-gizli-999" });
    act(() => fake.emitResult("varsayilan", request.id, { ok: true, metin: "kaydedildi" }));
    await act(async () => { await command; });
    const dokum = JSON.stringify(result.current.activeSession?.messages);
    expect(dokum).not.toContain("sk-gizli-999");
    expect(dokum).toContain("/providers add openrouter ••••");
  });
  it("her sekmeyi kendi sohbet kimliğiyle çekirdeğe tanıtır", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());

    await act(async () => {
      await result.current.create({ id: "ikinci" });
    });

    await waitFor(() => expect(fake.basladi).toHaveLength(2));
    expect(fake.basladi.map((k) => k.sohbet)).toEqual(["varsayilan", "ikinci"]);
  });

  it("ilk mesajda başlığı çekirdekten ister ve yalnız bir kez uygular", async () => {
    // Başlık tek yerde (çekirdekte) üretilir; saklı sohbet listesiyle ayrışmaz.
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());

    act(() => { result.current.send("varsayilan", "merhaba, bana bir tarayıcı oyunu yaz lütfen"); });

    await waitFor(() => expect(result.current.state.sessions.varsayilan.title).toBe("Tarayıcı oyunu yaz"));
    expect(fake.baslikIstekleri).toEqual(["merhaba, bana bir tarayıcı oyunu yaz lütfen"]);
    // Başlık isteği turdan ÖNCE gider; tur çekirdeğe yine tek istek olarak ulaşır.
    expect(fake.sent.map((item) => JSON.parse(item.line).ad)).toEqual(["tur.calistir"]);
  });

  it("verilmiş başlığı ezmez", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());
    await act(async () => {
      await result.current.create({ id: "adli", title: "Kendi başlığım", root: "/aktif" });
    });

    act(() => { result.current.send("adli", "başka bir iş"); });

    await waitFor(() => expect(fake.sent).toHaveLength(1));
    expect(fake.baslikIstekleri).toEqual([]);
    expect(result.current.state.sessions.adli.title).toBe("Kendi başlığım");
  });

  /* Bkz. bug: "Durdur"a basılıp "Tur iptal edildi" göründükten sonra sohbete
     yeni mesaj gönderilemiyordu (Enter/gönder çalışmıyordu), uygulama
     yeniden başlatılınca düzeliyordu. Kök neden: `tur.calistir` isteğinin
     promise'i bazı iptallerde HİÇ çözülmüyor, bu yüzden `runningRequests`
     referansı sonsuza dek dolu kalıp yeni mesajı sonsuza dek kuyrukta
     bırakıyordu. `stop()` artık bir güvenli üst sınırda durumu ZORLA
     sıfırlar. */
  it("stop() temizlik doğrulanmadan kuyruktaki işi başlatmaz", async () => {
    vi.useFakeTimers();
    try {
      const fake = fakeTransport();
      const { result } = renderHook(() => useSessions(fake.transport));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(result.current.activeSession).not.toBeNull();

      const turlar = () => fake.sent
        .map(({ line }) => JSON.parse(line) as { ad: string; veri?: Record<string, unknown> })
        .filter((request) => request.ad === "tur.calistir");

      act(() => {
        result.current.send("varsayilan", "ilk görev");
      });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(turlar()).toHaveLength(1);

      // Kullanıcı Durdur'a basar; çekirdek `tur.calistir` cevabını HİÇ
      // göndermez (asılı kalan iptal senaryosu).
      act(() => {
        result.current.stop("varsayilan");
      });
      expect(result.current.state.sessions.varsayilan.running).toBe(true);
      expect(result.current.state.sessions.varsayilan.stopping).toBe(true);

      // İkinci mesaj: promise hâlâ asılı olduğu için normalde KUYRUĞA girerdi.
      act(() => {
        result.current.send("varsayilan", "ikinci görev");
      });
      expect(turlar()).toHaveLength(1);

      // Güvenli üst sınır dolar: durum zorla sıfırlanır ve kuyruktaki mesaj
      // gerçekten çekirdeğe gönderilir.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5_000);
      });

      expect(turlar()).toHaveLength(1);
      expect(result.current.state.sessions.varsayilan.stopError).toContain("doğrulanamadı");
      await act(async () => {
        fake.emitResult("varsayilan", String((turlar()[0] as { id?: string }).id), { ok: false, metin: "iptal edildi" });
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(turlar()).toHaveLength(2);
      expect(turlar()[1].veri?.gorev).toBe("ikinci görev");
      expect(result.current.state.sessions.varsayilan.running).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it("öneri gelene kadar sekme adlandırıldıysa öneriyi uygulamaz", () => {
    // Öneri eşzamansızdır; arada verilen ad kullanıcınındır.
    const client = {} as never;
    let state = sessionReducer(initialSessionState, {
      type: "created",
      session: { id: "a", title: DEFAULT_TITLE, source: "fusion", root: "/p", client },
    });
    state = sessionReducer(state, { type: "titleChanged", id: "a", title: "Elle verilen" });
    state = sessionReducer(state, { type: "titleSuggested", id: "a", title: "Önerilen" });
    expect(state.sessions.a.title).toBe("Elle verilen");
  });
});


it("kalıcı queued snapshot aynı requestId ile mevcut sürücüden restore edilir", async () => {
  saveSubmission({requestId: "kalici-kuyruk", sessionId: "varsayilan", root: "/aktif", task: "sıradaki", attachments: [], state: "queued"});
  const fake = fakeTransport();
  const {result} = renderHook(() => useSessions(fake.transport));
  await waitFor(() => expect(fake.sent).toHaveLength(1));
  const request = JSON.parse(fake.sent[0].line);
  expect(request.ad).toBe("tur.calistir");
  expect(request.veri.gonderim_id).toBe("kalici-kuyruk");
  expect(result.current.activeSession?.messages.filter((message) => message.rol === "kullanici").map((message) => message.metin)).toEqual(["sıradaki"]);
});

describe("Soru cevabı makbuzu", () => {
  it("makbuz gelmeden kartı kapatmaz ve eski makbuz yeni soruyu kapatmaz", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());
    const id = result.current.activeSession!.id;
    act(() => fake.emitLine({ oturum_id: id, satir: JSON.stringify({ tip: "soru", id: "q1", veri: { tur: "soru", soru: "Ad?" } }) }));
    let sending!: Promise<void>;
    act(() => { sending = result.current.answer(id, { metin: "örnek" }); });
    expect(result.current.activeSession?.question?.id).toBe("q1");
    const request = JSON.parse(fake.sent.at(-1)!.line);
    expect(request.ad).toBe("soru.cevapla");
    expect(request.veri.answer.decisionId).toEqual(expect.any(String));
    act(() => fake.emitLine({ oturum_id: id, satir: JSON.stringify({ tip: "soru", id: "q2", veri: { tur: "soru", soru: "Hedef?" } }) }));
    await act(async () => { fake.emitResult(id, request.id, { ok: true, questionId: "q1" }); await sending; });
    expect(result.current.activeSession?.question?.id).toBe("q2");
  });
});

it("RPC kanıtını tek correlated final mesajına bağlar", async () => {
  const fake = fakeTransport();
  const {result} = renderHook(() => useSessions(fake.transport));
  await waitFor(() => expect(result.current.activeSession?.status).toBe("ready"));
  act(() => result.current.send("varsayilan", "iş"));
  await waitFor(() => expect(fake.sent.length).toBeGreaterThan(0));
  const request = JSON.parse(fake.sent[0].line);
  const kanit = {schema_version: 1, dogrulandi: false, engelliyor: true,
    yanlis_iddia: false, degisen: ["a.py"], degisen_sayisi: 1, sorunlar: ["kontrol düştü"]};
  act(() => fake.emitResult("varsayilan", request.id, {ok: false, metin: "Kısmi", kanit}));
  await waitFor(() => expect(result.current.activeSession?.running).toBe(false));
  const final = result.current.activeSession!.messages.filter((message) => message.rol === "asistan");
  expect(final).toHaveLength(1);
  expect(final[0].delivery).toMatchObject({kind: "supported", blocking: true, verified: false});
  act(() => fake.emitResult("varsayilan", request.id, {ok: false, metin: "Kısmi", kanit}));
  expect(result.current.activeSession!.messages.filter((message) => message.rol === "asistan")).toHaveLength(1);
});

it("/code-review bulgularını kart olarak final mesajına bağlar (#214)", async () => {
  const fake = fakeTransport();
  const {result} = renderHook(() => useSessions(fake.transport));
  await waitFor(() => expect(result.current.activeSession?.status).toBe("ready"));
  act(() => result.current.send("varsayilan", "incele"));
  await waitFor(() => expect(fake.sent.length).toBeGreaterThan(0));
  const request = JSON.parse(fake.sent[0].line);
  const bulgular = [{file: "a.py", line: 3, summary: "sıfıra bölme", failure_scenario: "n=0", verdict: "PLAUSIBLE"}];
  act(() => fake.emitResult("varsayilan", request.id, {ok: true, metin: "Bir hata.", bulgular}));
  await waitFor(() => expect(result.current.activeSession?.running).toBe(false));
  const final = result.current.activeSession!.messages.filter((message) => message.rol === "asistan");
  expect(final[0].findings).toEqual([{file: "a.py", line: 3, summary: "sıfıra bölme", failureScenario: "n=0", verdict: "PLAUSIBLE"}]);
});

// U4-04 — Ölçüldü (29 Ekim): makbuz kabul edilmezse tur boyunca bütün olaylar sessizce düşüyor,
// kullanıcı turu donmuş sanıyordu.
describe("Makbuzsuz tur olayları", () => {
  async function turBaslat() {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession?.status).toBe("ready"));
    act(() => { result.current.send("varsayilan", "iş"); });
    await waitFor(() => expect(fake.sent.length).toBeGreaterThan(0));
    const gonderimId = String(JSON.parse(fake.sent[0].line).veri.gonderim_id);
    const olay = (veri: Record<string, unknown>) => act(() => fake.emitLine({
      oturum_id: "varsayilan", satir: JSON.stringify({tip: "olay", veri})}));
    return {fake, result, gonderimId, olay};
  }

  it("bilinmeyen durumlu makbuz uyarı üretir, sonraki tur olayları yine gösterilir", async () => {
    const {result, gonderimId, olay} = await turBaslat();
    olay({olay: "GonderimMakbuzu", gonderim_id: gonderimId, oturum_id: "varsayilan", tur_id: `${gonderimId}:1`, durum: "gelecek_durum"});
    expect(result.current.activeSession?.messages.some((m) => m.hata && m.metin.includes("makbuzu doğrulanamadı"))).toBe(true);
    olay({olay: "TokenReceived", text: "merhaba dünya", event_id: `${gonderimId}:1:1`, session_id: "varsayilan",
      turn_id: `${gonderimId}:1`, schema_version: 1});
    expect(result.current.activeSession?.messages.some((m) => m.metin.includes("merhaba dünya"))).toBe(true);
  });

  it("eski isteğin makbuzu uyarı üretmez", async () => {
    const {result, olay} = await turBaslat();
    olay({olay: "GonderimMakbuzu", gonderim_id: "eski-istek", oturum_id: "varsayilan", tur_id: "eski-istek:1", durum: "completed"});
    expect(result.current.activeSession?.messages.some((m) => m.metin?.includes("makbuzu doğrulanamadı"))).toBe(false);
  });
});

// U4-03 — Ölçüldü (29 Ekim): `oturum.baslat` başarısızsa hata yutuluyor, `oturum.gecmis` yine
// kimliksiz isteniyordu (yanlış sohbetin geçmişi) ve kip çekirdeğe bildirilmemiş kalıyordu.
describe("Başarısız oturum.baslat", () => {
  it.each(["ok-false", "reddedilen-istek"])("geçmiş istenmez, sekme hatayla işaretlenir (%s)", async (tur) => {
    const fake = fakeTransport([{rol: "kullanici", metin: "yanlış sohbetin mesajı"}]);
    const gecmisIstekleri: string[] = [];
    const asil = fake.transport.send;
    fake.transport.send = vi.fn(async (id: string, line: string) => {
      const istek = JSON.parse(line) as {id: string; ad: string};
      if (istek.ad === "oturum.gecmis") gecmisIstekleri.push(id);
      if (istek.ad === "oturum.baslat") {
        if (tur === "ok-false") queueMicrotask(() => fake.emitResult(id, istek.id, {ok: false, hata: "geçersiz kip"}));
        else throw new Error("yazma kırıldı");
        return;
      }
      return asil(id, line);
    });
    const {result} = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession?.status).toBe("crashed"));
    expect(result.current.activeSession?.error).toContain("oturum.baslat");
    expect(gecmisIstekleri).toEqual([]);
    expect(result.current.activeSession?.messages.some((m) => m.metin === "yanlış sohbetin mesajı")).toBe(false);
  });
});

// U4-08 (a) — Ölçüldü (29 Ekim): çekirdek "artık beklemiyor" (ok:false + questionId) dediğinde
// answer() fırlatıyor, kart kalıyor ve kullanıcı sonsuz yeniden deneme döngüsüne giriyordu.
describe("Artık beklemeyen soru", () => {
  async function soruyla() {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());
    const id = result.current.activeSession!.id;
    act(() => fake.emitLine({ oturum_id: id, satir: JSON.stringify({ tip: "soru", id: "q1", veri: { tur: "soru", soru: "Ad?" } }) }));
    return { fake, result, id };
  }
  it("ok:false + questionId kartı kapatır ve fırlatmaz", async () => {
    const { fake, result, id } = await soruyla();
    let sending!: Promise<void>;
    act(() => { sending = result.current.answer(id, { metin: "örnek" }); });
    const request = JSON.parse(fake.sent.at(-1)!.line);
    await act(async () => { fake.emitResult(id, request.id, { ok: false, questionId: "q1" }); await sending; });
    expect(result.current.activeSession?.question).toBeNull();
    expect(result.current.activeSession?.messages.some((m) => m.metin?.includes("artık cevap beklemiyordu"))).toBe(true);
  });
  it("geçersiz cevap hatasında (metin var) kart kalır ve hata fırlar", async () => {
    const { fake, result, id } = await soruyla();
    let sending!: Promise<void>;
    act(() => { sending = result.current.answer(id, { metin: "örnek" }); });
    const request = JSON.parse(fake.sent.at(-1)!.line);
    const sonuc = expect(sending).rejects.toThrow();
    await act(async () => { fake.emitResult(id, request.id, { ok: false, metin: "Soru kimliği veya cevap geçersiz." }); });
    await sonuc;
    expect(result.current.activeSession?.question?.id).toBe("q1");
  });
});

// Ölçüldü (30 Ekim): create beklenirken kapanan görünüm çekirdek oturumunu kapatmıyordu (U4-31);
// çökme sonrası kuyruktaki görev ölü istemciye gidiyordu (U4-32); sıradan başlayan görev kayıtta
// "queued" kalıp yeniden açılışta ikinci kez çalışıyordu (U4-34).
describe("useSessions oturum yaşam döngüsü (30 Ekim)", () => {
  it("create bitmeden görünüm kapanırsa çekirdek oturumu kapatılır (U4-31)", async () => {
    const fake = fakeTransport();
    let bitir: (() => void) | null = null;
    const gercek = fake.transport.create;
    fake.transport.create = vi.fn((id, root) => new Promise((cozumle) => {
      bitir = () => cozumle(gercek(id, root));
    }));
    const { unmount } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(fake.transport.create).toHaveBeenCalled());
    unmount();
    await act(async () => { bitir?.(); await Promise.resolve(); });
    await waitFor(() => expect(fake.transport.close).toHaveBeenCalledWith("varsayilan"));
  });

  it("sıradan başlayan görev kayıtta 'queued' kalmaz (U4-34)", async () => {
    const { loadSubmissions } = await import("./submissionPersistence");
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession?.status).toBe("ready"));
    act(() => {
      result.current.send("varsayilan", "birinci");
      result.current.send("varsayilan", "ikinci");
    });
    expect(loadSubmissions("varsayilan").find((e) => e.task === "ikinci")?.state).toBe("queued");
    await waitFor(() => expect(fake.sent).toHaveLength(1));
    act(() => fake.emitResult("varsayilan", JSON.parse(fake.sent[0].line).id, { ok: true }));
    await waitFor(() => expect(fake.sent).toHaveLength(2));
    expect(loadSubmissions("varsayilan").find((e) => e.task === "ikinci")?.state).toBe("pending");
  });

  it("çekirdek çökünce kuyruktaki görev ölü istemciye gönderilmez (U4-32)", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession?.status).toBe("ready"));
    act(() => {
      result.current.send("varsayilan", "birinci");
      result.current.send("varsayilan", "ikinci");
    });
    await waitFor(() => expect(fake.sent).toHaveLength(1));
    await act(async () => { fake.emitClosed({ oturum_id: "varsayilan", neden: "çöktü" }); });
    await waitFor(() => expect(result.current.state.sessions.varsayilan.status).toBe("crashed"));
    expect(fake.sent).toHaveLength(1);
    // Yalnız uçuştaki ilk istek hata alır; kuyruktaki ikinci görev ölü istemciye hiç denenmez.
    const hatalar = result.current.state.sessions.varsayilan.messages.filter((m) => m.hata && m.metin.startsWith("Hata:"));
    expect(hatalar).toHaveLength(1);
  });
});

it("saklı sohbetler her açık proje kökünden istenir (U4-39)", async () => {
  const fake = fakeTransport();
  const { result } = renderHook(() => useSessions(fake.transport));
  await waitFor(() => expect(result.current.activeSession?.status).toBe("ready"));
  await act(async () => { await result.current.create({ id: "a", root: "/Projects/a" }); });
  await act(async () => { await result.current.create({ id: "b", root: "/Projects/b" }); });
  vi.mocked(fake.transport.send).mockClear();
  await act(async () => { await result.current.refreshStored(); });
  const listeleme = vi.mocked(fake.transport.send).mock.calls
    .filter(([, line]) => JSON.parse(line).ad === "sohbet.listele").map(([id]) => id);
  expect(new Set(listeleme).size).toBe(3);
});

it("reddedilen komut isteği çağırana fırlamaz, hata mesajı gösterilir; argüman biçimi korunur (U4-40)", async () => {
  const fake = fakeTransport();
  const { result } = renderHook(() => useSessions(fake.transport));
  await waitFor(() => expect(result.current.activeSession?.status).toBe("ready"));
  let command!: Promise<Record<string, unknown>>;
  act(() => { command = result.current.runCommand("varsayilan", "/btw  satır bir\nsatır   iki"); });
  await waitFor(() => expect(fake.sent).toHaveLength(1));
  const request = JSON.parse(fake.sent[0].line);
  expect(request.veri).toEqual({ ad: "btw", arguman: "satır bir\nsatır   iki" });
  await act(async () => { await result.current.close("varsayilan"); });
  await act(async () => { await expect(command).resolves.toMatchObject({ ok: false }); });
  expect(result.current.state.sessions.varsayilan.messages.at(-1)).toMatchObject({ hata: true });
});
