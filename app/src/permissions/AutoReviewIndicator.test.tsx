import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AutoReviewCard } from "../settings/sections/AutoReviewCard";
import { olayAdimi } from "../protocol/olayMetni";
import { AutoReviewIndicator } from "./AutoReviewIndicator";

afterEach(cleanup);

function client(durum: Record<string, unknown> = {}) {
  const listeners: ((veri: Record<string, unknown>) => void)[] = [];
  const state: Record<string, unknown> = {
    ok: true, mod: "auto", ayar: "ask_only", ayar_etiketi: "ask_only — sorulacakları sınıflandır",
    model: "hakem (sahte)", ardisik: 1, toplam: 2, esik_ardisik: 3, esik_toplam: 20,
    dustu: false, dusus_nedeni: "", model_erisilemiyor: false, son_kararlar: [], ...durum,
  };
  return {
    state,
    emit: (veri: Record<string, unknown>) => listeners.forEach((listener) => listener(veri)),
    onEvent: vi.fn((listener: (veri: Record<string, unknown>) => void) => {
      listeners.push(listener);
      return () => undefined;
    }),
    request: vi.fn(async (name: string, data: Record<string, unknown>) => {
      if (name === "oto.devam") Object.assign(state, { mod: "auto", dustu: false });
      if (name === "oto.ayar") state.ayar = data.deger;
      return { ...state };
    }),
  };
}

describe("AutoReviewIndicator (P-011)", () => {
  it("Otomatik kipte denetçi rozetini sayaçla gösterir, kapalıyken gizler", async () => {
    const api = client();
    const { rerender } = render(<AutoReviewIndicator approval="auto" client={api} />);
    const rozet = await screen.findByText("Denetçi");
    expect(rozet.getAttribute("aria-label")).toContain("engel 1/3 üst üste, 2/20 toplam");
    rerender(<AutoReviewIndicator approval="security" client={api} />);
    expect(screen.queryByText("Denetçi")).toBeNull();
  });

  it("kip düşünce olayla tazelenir ve Otomatik'e dön oto.devam çağırır", async () => {
    const api = client();
    const onResumed = vi.fn();
    render(<AutoReviewIndicator approval="security" client={api} onResumed={onResumed} />);
    await waitFor(() => expect(api.request).toHaveBeenCalledWith("oto.durum", {}));
    Object.assign(api.state, { mod: "security", dustu: true, dusus_nedeni: "denetçi üst üste 3 çağrıyı riskli buldu" });
    act(() => api.emit({ olay: "AutoModeFellBack", reason: "x", trips: 1 }));
    fireEvent.click(await screen.findByRole("button", { name: "Otomatik'e dön" }));
    await waitFor(() => expect(onResumed).toHaveBeenCalled());
    expect(api.request).toHaveBeenCalledWith("oto.devam", {});
  });

  it("düşüş uyarısı yalnız Manuel kipte görünür, Plan seçilince gizlenir", async () => {
    const api = client({ mod: "security", dustu: true, dusus_nedeni: "üst üste 3" });
    const { rerender } = render(<AutoReviewIndicator approval="security" client={api} />);
    expect(await screen.findByText("Otomatik → Manuel'e düştü")).toBeTruthy();
    rerender(<AutoReviewIndicator approval="plan" client={api} />);
    expect(screen.queryByText("Otomatik → Manuel'e düştü")).toBeNull();
    rerender(<AutoReviewIndicator approval="bypass" client={api} />);
    expect(screen.queryByRole("button", { name: "Otomatik'e dön" })).toBeNull();
  });

  it("ayar kartı seçimi oto.ayar ile yazar ve son kararları listeler", async () => {
    const api = client({
      son_kararlar: [{ arac: "run_shell", karar: "riskli", karar_etiketi: "riskli, soruluyor", kaynak: "model", ozet: "git push", gerekce: "istenmedi" }],
    });
    render(<AutoReviewCard client={api} />);
    fireEvent.click(await screen.findByRole("button", { name: /Kapalı/ }));
    await waitFor(() => expect(api.request).toHaveBeenCalledWith("oto.ayar", { deger: "off" }));
    expect(screen.getByRole("list", { name: "Son denetçi kararları" }).textContent).toContain("git push — istenmedi");
  });

  it("ayar kartı verinin gittiği modeli yazar, hata ve düşüş uyarısını gösterir", async () => {
    const api = client({ veri_notu: "Açıkken hakem (sahte) modeline son 3 mesajın gider", mod: "security", dustu: true, dusus_nedeni: "üst üste 3" });
    api.request.mockImplementation(async (name: string) => {
      if (name === "oto.ayar") return { ok: false, metin: "Kullanım: /auto-mode" };
      if (name === "oto.devam") Object.assign(api.state, { mod: "auto", dustu: false });
      return { ...api.state };
    });
    const onResumed = vi.fn();
    render(<AutoReviewCard client={api} onResumed={onResumed} />);
    expect(await screen.findByText(/hakem \(sahte\) modeline/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Tümünü denetle/ }));
    expect((await screen.findByText("Kullanım: /auto-mode")).getAttribute("role")).toBe("alert");
    fireEvent.click(screen.getByRole("button", { name: "Otomatik'e dön" }));
    await waitFor(() => expect(onResumed).toHaveBeenCalled());
  });

  it("denetçi olayları akışta kalıcı adım olur", () => {
    expect(olayAdimi({ olay: "AutoReviewDecided", verdict: "guvenli", source: "model", summary: "git push", reason: "istendi" }))
      .toMatchObject({ metin: "denetçi onayladı", kalici: true });
    expect(olayAdimi({ olay: "AutoModeFellBack", reason: "üst üste 3", trips: 1 })?.metin).toBe("Otomatik kip Manuel'e düştü");
  });
});
