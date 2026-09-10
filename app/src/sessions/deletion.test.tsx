import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useSessions } from "./useSessions";
import { SESSION_VIEW_KEY } from "./persistence";
import type { SessionLineEvent, SessionTransport } from "./types";

afterEach(() => localStorage.clear());

function fakeTransport(fail = false) {
  let onLine: ((event: SessionLineEvent) => void) | null = null;
  const deleted: string[] = [];
  const transport: SessionTransport = {
    create: vi.fn(async (id, root) => ({
      oturum_id: id, kok: root ?? "/proje", pid: 42,
      durum: "calisiyor", kapanis_nedeni: null,
    })),
    send: vi.fn(async (id, line) => {
      const request = JSON.parse(line);
      if (request.ad === "sohbet.sil" && !fail) deleted.push(request.veri.sohbet_id);
      const veri = request.ad === "sohbet.listele"
        ? { ok: true, sohbetler: deleted.includes("eski") ? [] : [
          { sohbet_id: "eski", baslik: "Dünkü sohbet", kok: "/baska", guncelleme: 1, mesaj_sayisi: 2 },
        ] }
        : request.ad === "sohbet.sil" && fail
          ? { ok: false, metin: "Disk yazılamadı" }
          : { ok: true, mesajlar: [] };
      queueMicrotask(() => onLine?.({ oturum_id: id, satir: JSON.stringify({ tip: "sonuc", id: request.id, veri }) }));
    }),
    close: vi.fn(async () => undefined),
    list: vi.fn(async () => []),
    onLine: vi.fn(async (handler) => { onLine = handler; return vi.fn(); }),
    onClosed: vi.fn(async () => vi.fn()),
  };
  return { transport, deleted };
}

describe("kalıcı sohbet silme", () => {
  it("açılmamış sohbeti kendi proje kökünde siler ve yenilemede geri getirmez", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.storedConversations).toHaveLength(1));
    await act(async () => { await result.current.remove("eski"); });
    expect(fake.deleted).toEqual(["eski"]);
    expect(fake.transport.send).toHaveBeenCalledWith("varsayilan", expect.stringContaining('"kok":"/baska"'));
    await act(async () => { await result.current.refreshStored(); });
    expect(result.current.storedConversations).toHaveLength(0);
  });

  it("disk hatasında sohbeti tutar ve yeniden denemek için hata döndürür", async () => {
    const fake = fakeTransport(true);
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.sessions).toHaveLength(1));
    await act(async () => {
      await expect(result.current.remove("varsayilan")).rejects.toThrow("Disk yazılamadı");
    });
    expect(result.current.sessions).toHaveLength(1);
    expect(fake.transport.close).not.toHaveBeenCalled();
  });

  it("son sohbet silinince boş görünümü kaydeder ve yeniden açılışta yeni kimlik üretir", async () => {
    const fake = fakeTransport();
    const first = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(first.result.current.sessions).toHaveLength(1));
    await act(async () => { await first.result.current.remove("varsayilan"); });
    expect(JSON.parse(localStorage.getItem(SESSION_VIEW_KEY)!)).toMatchObject({
      activeId: null, sessions: [],
    });
    first.unmount();
    const second = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(second.result.current.sessions).toHaveLength(1));
    expect(second.result.current.sessions[0].id).not.toBe("varsayilan");
  });

  it("yükleme sırasında boş ilk görünüm kayıtlı sohbetlerin üzerine yazılmaz", async () => {
    const saved = JSON.stringify({ version: 1, activeId: "kayitli", sessions: [
      { id: "kayitli", title: "Kayıtlı", source: "fusion", root: "/proje", updatedAt: 1 },
    ] });
    localStorage.setItem(SESSION_VIEW_KEY, saved);
    const fake = fakeTransport();
    const originalCreate = fake.transport.create;
    let release!: () => void;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    fake.transport.create = vi.fn(async (id, root) => {
      await gate;
      return originalCreate(id, root);
    });
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(fake.transport.create).toHaveBeenCalled());
    expect(localStorage.getItem(SESSION_VIEW_KEY)).toBe(saved);
    await act(async () => { release(); });
    await waitFor(() => expect(result.current.sessions[0]?.id).toBe("kayitli"));
  });

  it("son kapalı sohbeti geçici çekirdek üzerinden silebilir", async () => {
    const fake = fakeTransport();
    const { result } = renderHook(() => useSessions(fake.transport));
    await waitFor(() => expect(result.current.sessions).toHaveLength(1));
    await act(async () => { await result.current.close("varsayilan"); });
    await act(async () => { await result.current.remove("varsayilan"); });
    expect(fake.deleted).toEqual(["varsayilan"]);
    expect(result.current.sessions).toHaveLength(0);
    expect(fake.transport.create).toHaveBeenCalledTimes(2);
    expect(fake.transport.close).toHaveBeenCalledTimes(3);
  });
});
