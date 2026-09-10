import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useSessions } from "./useSessions";
import { SESSION_VIEW_KEY } from "./persistence";
import type { SessionClosedEvent, SessionLineEvent, SessionTransport } from "./types";

/**
 * Ölçüldü (kullanıcının makinesi, 7-8 Eylül): uygulama her açılışta TEK sekme
 * açıyordu ve o sekmenin kimliği sabitti. Dünkü konuşmalar diskte duruyordu ama
 * arayüzden onlara giden hiçbir yol yoktu — kullanıcı her seferinde sıfırdan
 * anlatmak zorunda kaldı.
 *
 * Kaydedilmiş sekme listesi zaten yazılıyordu; yalnız okunmuyordu.
 */

afterEach(() => localStorage.clear());

function fakeTransport() {
  let lineHandler: ((event: SessionLineEvent) => void) | null = null;
  const basladi: { oturum: string; sohbet: string }[] = [];
  const transport: SessionTransport = {
    create: vi.fn(async (id, root) => ({
      oturum_id: id,
      kok: root ?? "/aktif",
      pid: 42,
      durum: "calisiyor" as const,
      kapanis_nedeni: null,
    })),
    send: vi.fn(async (id, line) => {
      const request = JSON.parse(line) as { id: string; ad: string; veri?: Record<string, unknown> };
      if (request.ad === "oturum.baslat") {
        basladi.push({ oturum: id, sohbet: String(request.veri?.sohbet_id ?? "") });
      }
      const veri = request.ad === "oturum.gecmis"
        ? { ok: true, mesajlar: [{ rol: "kullanici", metin: `${id} geçmişi` }] }
        : request.ad === "sohbet.listele"
          ? { ok: true, sohbetler: [{ sohbet_id: "eski-c", baslik: "dünkü oyun", guncelleme: 1, mesaj_sayisi: 4 }] }
          : { ok: true };
      queueMicrotask(() => lineHandler?.({
        oturum_id: id,
        satir: JSON.stringify({ tip: "sonuc", id: request.id, veri }),
      }));
    }),
    close: vi.fn(async () => undefined),
    list: vi.fn(async () => []),
    onLine: vi.fn(async (handler) => { lineHandler = handler; return vi.fn(); }),
    onClosed: vi.fn(async (_handler: (event: SessionClosedEvent) => void) => vi.fn()),
  };
  return { transport, basladi };
}

function persist(sessions: { id: string; title: string; root: string }[], activeId: string) {
  localStorage.setItem(SESSION_VIEW_KEY, JSON.stringify({
    version: 1,
    activeId,
    sessions: sessions.map((session) => ({ ...session, source: "fusion", updatedAt: 10 })),
  }));
}

describe("oturum geri yükleme", () => {
  it("kaydedilmiş sekmeleri kendi kimlikleriyle geri açar", async () => {
    persist([
      { id: "sohbet-a", title: "Oyun", root: "/proje" },
      { id: "sohbet-b", title: "Fatura", root: "/proje" },
    ], "sohbet-b");
    const fake = fakeTransport();

    const { result } = renderHook(() => useSessions(fake.transport));

    await waitFor(() => expect(result.current.sessions.map((item) => item.id)).toEqual([
      "sohbet-a",
      "sohbet-b",
    ]));
    expect(fake.basladi.map((item) => item.sohbet).sort()).toEqual(["sohbet-a", "sohbet-b"]);
  });

  it("en son kullanılan sekmeyi seçili getirir", async () => {
    persist([
      { id: "sohbet-a", title: "Oyun", root: "/proje" },
      { id: "sohbet-b", title: "Fatura", root: "/proje" },
    ], "sohbet-b");
    const fake = fakeTransport();

    const { result } = renderHook(() => useSessions(fake.transport));

    await waitFor(() => expect(result.current.activeSession?.id).toBe("sohbet-b"));
  });

  it("kayıt yoksa eskisi gibi tek varsayılan sekme açar", async () => {
    const fake = fakeTransport();

    const { result } = renderHook(() => useSessions(fake.transport));

    await waitFor(() => expect(result.current.sessions.map((item) => item.id)).toEqual([
      "varsayilan",
    ]));
  });

  it("geri açılan sekme kendi geçmişini yükler", async () => {
    persist([{ id: "sohbet-a", title: "Oyun", root: "/proje" }], "sohbet-a");
    const fake = fakeTransport();

    const { result } = renderHook(() => useSessions(fake.transport));

    await waitFor(() => expect(result.current.activeSession?.messages).toEqual([
      { rol: "kullanici", metin: "sohbet-a geçmişi" },
    ]));
  });

  it("diskteki sohbetleri listeler ve tıklanınca o kimliğe bağlanır", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.activeSession).not.toBeNull());

    await waitFor(() => expect(result.current.storedConversations.map((item) => item.id)).toEqual([
      "eski-c",
    ]));
    await result.current.openStored("eski-c");

    await waitFor(() => expect(result.current.activeSession?.id).toBe("eski-c"));
    expect(fake.basladi.some((item) => item.sohbet === "eski-c")).toBe(true);
  });
});

it("yeniden bağlanma sohbetlerin gerçek etkinlik zamanını değiştirmez", async () => {
  localStorage.setItem(SESSION_VIEW_KEY, JSON.stringify({ version: 1, activeId: "yeni", sessions: [
    { id: "yeni", title: "Yeni", source: "fusion", root: "/proje", updatedAt: 200 },
    { id: "eski", title: "Eski", source: "fusion", root: "/proje", updatedAt: 100 },
  ] }));
  const fake = fakeTransport();
  const { result } = renderHook(() => useSessions(fake.transport));
  await waitFor(() => expect(result.current.sessions).toHaveLength(2));
  expect(result.current.state.sessions.yeni.updatedAt).toBe(200);
  expect(result.current.state.sessions.eski.updatedAt).toBe(100);
  expect(JSON.parse(localStorage.getItem(SESSION_VIEW_KEY)!).sessions.map((item: { updatedAt: number }) => item.updatedAt)).toEqual([100, 200]);
});

it("saklı sohbeti açmak etkinlik zamanını değiştirmez", async () => {
  const fake = fakeTransport();
  const { result } = renderHook(() => useSessions(fake.transport));
  await waitFor(() => expect(result.current.storedConversations).toHaveLength(1));
  await act(async () => { await result.current.openStored("eski-c"); });
  expect(result.current.state.sessions["eski-c"].updatedAt).toBe(1000);
  expect(JSON.parse(localStorage.getItem(SESSION_VIEW_KEY)!).sessions.find((item: { id: string }) => item.id === "eski-c").updatedAt).toBe(1000);
});
