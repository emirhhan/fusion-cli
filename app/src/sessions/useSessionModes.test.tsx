import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { modlariOku, useSessionModes } from "./useSessionModes";

type Cevap = Record<string, unknown>;
function istemci(cevaplar: Record<string, Cevap | Error | (() => Promise<Cevap>)>) {
  return {
    request: vi.fn(async (ad: string) => {
      const cevap = cevaplar[ad];
      if (cevap instanceof Error) throw cevap;
      return typeof cevap === "function" ? cevap() : cevap ?? { ok: true };
    }),
  };
}

describe("modlariOku", () => {
  it("yalnız tanınan modları döndürür", () => {
    expect(modlariOku({ mod: "security", kip: "sohbet" })).toEqual({ approval: "security", workspace: "sohbet", persona: undefined });
    expect(modlariOku({ mod: "yok", kip: 3 })).toEqual({ approval: undefined, workspace: undefined, persona: undefined });
  });

  it("kişiliği nesne/null/yok olarak ayırır (P-053)", () => {
    expect(modlariOku({ kisilik: { ad: "explore", unvan: "Kâşif" } }).persona).toEqual({ ad: "explore", unvan: "Kâşif" });
    expect(modlariOku({ kisilik: null }).persona).toBeNull();
    expect(modlariOku({ kisilik: "bozuk" }).persona).toBeUndefined();
  });
});

describe("useSessionModes — oturum kişiliği (P-053)", () => {
  it("durumdan okur, değişikliği çekirdek onaylayınca gösterir", async () => {
    const c = istemci({
      "oturum.durum": { ok: true, mod: "auto", kip: "kod", kisilik: null },
      "oturum.baslat": { ok: true, mod: "auto", kip: "kod", kisilik: { ad: "plan", unvan: "Planlayıcı" } },
    });
    const { result } = renderHook(() => useSessionModes({ id: "a", client: c }, vi.fn()));
    await waitFor(() => expect(c.request).toHaveBeenCalledWith("oturum.durum", {}));
    expect(result.current.persona).toBeNull();
    await act(async () => { await result.current.changePersona("plan"); });
    expect(c.request).toHaveBeenCalledWith("oturum.baslat", { kisilik: "plan" });
    expect(result.current.persona).toEqual({ ad: "plan", unvan: "Planlayıcı" });
  });
});

describe("useSessionModes — sohbet başına mod", () => {
  it("sohbet değişince arayüz çekirdeğin O sohbetteki gerçek modunu gösterir", async () => {
    // Ölçüldü (29 Ekim): mod tek global useState("auto") idi; sohbet B "security" iken A'daki seçim görünürdü.
    const a = istemci({ "oturum.durum": { ok: true, mod: "plan", kip: "kod" } });
    const b = istemci({ "oturum.durum": { ok: true, mod: "security", kip: "sohbet" } });
    const { result, rerender } = renderHook(({ s }) => useSessionModes(s, vi.fn()), {
      initialProps: { s: { id: "a", client: a } },
    });
    await waitFor(() => expect(result.current.approval).toBe("plan"));
    rerender({ s: { id: "b", client: b } });
    await waitFor(() => expect(result.current.approval).toBe("security"));
    expect(result.current.workspaceMode).toBe("sohbet");
    rerender({ s: { id: "a", client: a } });
    await waitFor(() => expect(result.current.approval).toBe("plan"));
  });

  it("çekirdek ok:false derse eski görünüm korunur ve hata bildirilir", async () => {
    const hata = vi.fn();
    const c = istemci({
      "oturum.durum": { ok: true, mod: "auto", kip: "kod" },
      "oturum.baslat": { ok: false, metin: "bilinmeyen mod" },
    });
    const { result } = renderHook(() => useSessionModes({ id: "a", client: c }, hata));
    await waitFor(() => expect(c.request).toHaveBeenCalledWith("oturum.durum", {}));
    let basari = true;
    await act(async () => { basari = await result.current.changeApproval("bypass"); });
    expect(basari).toBe(false);
    expect(result.current.approval).toBe("auto");
    expect(hata).toHaveBeenLastCalledWith("İzin modu değiştirilemedi. bilinmeyen mod");
  });

  it("istek reddedilirse (bağlantı koptu) eski görünüm kalır; çalışma kipi için de aynı", async () => {
    const hata = vi.fn();
    const c = istemci({ "oturum.durum": { ok: true, mod: "edits", kip: "kod" }, "oturum.baslat": new Error("kapandı") });
    const { result } = renderHook(() => useSessionModes({ id: "a", client: c }, hata));
    await waitFor(() => expect(result.current.approval).toBe("edits"));
    await act(async () => { await result.current.changeApproval("plan"); });
    await act(async () => { await result.current.changeWorkspace("sohbet"); });
    expect(result.current.approval).toBe("edits");
    expect(result.current.workspaceMode).toBe("kod");
    expect(hata).toHaveBeenLastCalledWith("Sohbet kipi değiştirilemedi. Yeniden dene.");
  });

  it("çekirdek onaylayınca yeni mod görünür ve eski hata temizlenir", async () => {
    const hata = vi.fn();
    const c = istemci({ "oturum.durum": { ok: true, mod: "auto", kip: "kod" }, "oturum.baslat": { ok: true, mod: "security" } });
    const { result } = renderHook(() => useSessionModes({ id: "a", client: c }, hata));
    await waitFor(() => expect(c.request).toHaveBeenCalled());
    await act(async () => { await result.current.changeApproval("security"); });
    expect(result.current.approval).toBe("security");
    expect(hata).toHaveBeenLastCalledWith(null);
  });

  it("yanıt gelirken yapılan değişikliği bayat durum ezmez", async () => {
    let bitir: (cevap: Cevap) => void = () => undefined;
    const c = istemci({
      "oturum.durum": () => new Promise<Cevap>((cozumle) => { bitir = cozumle; }),
      "oturum.baslat": { ok: true, mod: "plan" },
    });
    const { result } = renderHook(() => useSessionModes({ id: "a", client: c }, vi.fn()));
    await act(async () => { await result.current.changeApproval("plan"); });
    await act(async () => { bitir({ ok: true, mod: "auto", kip: "kod" }); });
    expect(result.current.approval).toBe("plan");
  });
});

describe("useSessionModes — denetçi kip düşüşü (P-011)", () => {
  it("AutoModeFellBack olayıyla Manuel'e geçer, adoptApproval ile Otomatik'i benimser", async () => {
    let dinleyici: ((veri: Record<string, unknown>) => void) | null = null;
    const c = {
      ...istemci({ "oturum.durum": { ok: true, mod: "auto", kip: "kod" } }),
      onEvent: vi.fn((f: (veri: Record<string, unknown>) => void) => { dinleyici = f; return () => undefined; }),
    };
    const { result } = renderHook(() => useSessionModes({ id: "a", client: c }, vi.fn()));
    await waitFor(() => expect(dinleyici).not.toBeNull());
    act(() => dinleyici?.({ olay: "AutoModeFellBack", reason: "üst üste 3", trips: 1 }));
    expect(result.current.approval).toBe("security");
    act(() => result.current.adoptApproval("auto"));
    expect(result.current.approval).toBe("auto");
  });
});

describe("useSessionModes — karttan auto'ya geçiş (#82)", () => {
  it("IzinKipiDegisti olayıyla kip rozetini günceller, tanınmayan kipi yok sayar", async () => {
    let dinleyici: ((veri: Record<string, unknown>) => void) | null = null;
    const c = {
      ...istemci({ "oturum.durum": { ok: true, mod: "security", kip: "kod" } }),
      onEvent: vi.fn((f: (veri: Record<string, unknown>) => void) => { dinleyici = f; return () => undefined; }),
    };
    const { result } = renderHook(() => useSessionModes({ id: "a", client: c }, vi.fn()));
    await waitFor(() => expect(result.current.approval).toBe("security"));
    act(() => dinleyici?.({ olay: "IzinKipiDegisti", mod: "auto" }));
    expect(result.current.approval).toBe("auto");
    act(() => dinleyici?.({ olay: "IzinKipiDegisti", mod: "bilinmeyen" }));
    expect(result.current.approval).toBe("auto");
  });
});
