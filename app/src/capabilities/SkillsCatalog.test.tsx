import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ProtocolClient } from "../protocol/client";
import { SkillsCatalog } from "./SkillsCatalog";

afterEach(cleanup);

function client() {
  return {
    request: vi.fn(async (name: string, data: Record<string, unknown>) => {
      if (name === "yetenek.katalog") return {
        ok: true,
        beceriler: [{ ad: "frontend-design", aciklama: "Profesyonel arayüz", kaynak: "claude+codex", tur: "beceri", etkin: true, izinler: ["dosya okuma"] }],
        ajanlar: [{ ad: "reviewer", aciklama: "Kodu inceler", kaynak: "claude", tur: "ajan", etkin: false, izinler: ["dosya okuma", "komut çalıştırma"] }],
        talimatlar: [{ ad: "CLAUDE.md", kaynak: "proje", tur: "talimat", aciklama: "Proje talimatı", etkin: true, izinler: [] }],
        mcp: [{ ad: "github", aciklama: "GitHub araçları", kaynak: "fusion", tur: "mcp", etkin: true, izinler: ["dış araçlar"] }],
      };
      if (name === "yetenek.detay") return { ok: true, ...data, icerik: "Tam uzmanlık talimatı", kesildi: false };
      return { ok: true, ...data };
    }),
  } as unknown as ProtocolClient;
}

describe("SkillsCatalog bozuk öğe", () => {
  // Ölçüldü (29 Ekim, U6-04): etkin alanı boolean olmayan TEK öğe bütün listeyi boşaltıyordu.
  it("bozuk öğeyi atlar, geçerli olanları gösterir ve atlananı bildirir", async () => {
    const bozuk = {
      request: vi.fn(async () => ({
        ok: true,
        beceriler: [
          { ad: "saglam", aciklama: "", kaynak: "claude", tur: "beceri", etkin: true, izinler: [] },
          { ad: "bozuk", aciklama: "", kaynak: "claude", tur: "beceri", etkin: "evet", izinler: [] },
          null,
        ],
      })),
    } as unknown as ProtocolClient;
    render(<SkillsCatalog client={bozuk} onClose={() => undefined} />);
    expect(await screen.findByText("saglam")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("status").textContent).toContain("2 katalog öğesi");
  });
});

describe("SkillsCatalog", () => {
  it("kaynakları, izinleri ve birleşik Claude/Codex etiketini gösterir", async () => {
    render(<SkillsCatalog client={client()} onClose={() => undefined} />);
    expect(await screen.findByText("frontend-design")).toBeTruthy();
    expect(screen.getByText("Beceri · Claude · Codex")).toBeTruthy();
    expect(screen.getByText("github")).toBeTruthy();
    // Etkin olanlar üstte kendi başlığı altında toplanır.
    expect(screen.getByText("Etkin · 2")).toBeTruthy();
    // İzinler ayrıntıda görünür.
    fireEvent.click(screen.getByRole("button", { name: "frontend-design ayrıntılarını aç" }));
    expect(screen.getByText(/dosya okuma/)).toBeTruthy();
  });

  it("arar, detay açar, oturumluk kapatır ve sonraki tur için seçer", async () => {
    const fake = client();
    render(<SkillsCatalog client={fake} onClose={() => undefined} />);
    await screen.findByText("frontend-design");
    fireEvent.change(screen.getByRole("searchbox", { name: "Beceri ve ajan ara" }), { target: { value: "frontend" } });
    expect(screen.queryByText("reviewer")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "frontend-design ayrıntılarını aç" }));
    expect(await screen.findByText("Tam uzmanlık talimatı")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Bu beceriyi sonraki turda kullan" }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("yetenek.kullan", { tur: "beceri", ad: "frontend-design" }));
    fireEvent.click(screen.getByRole("switch", { name: "frontend-design oturum etkinliği" }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("yetenek.etkinlik", { tur: "beceri", ad: "frontend-design", etkin: false }));
  });
});

describe("SkillsCatalog yarış", () => {
  // Ölçüldü (30 Ekim, U6-05): ilk isteğin içeriği ikinciden sonra gelirse ikinci seçilen öğenin
  // panelinde birincinin ayrıntısı görünüyordu.
  it("yavaş gelen eski ayrıntı, sonradan seçilen öğenin ayrıntısını ezmez", async () => {
    const bekleyen: Record<string, (deger: Record<string, unknown>) => void> = {};
    const base = client();
    const yarisli = {
      request: vi.fn((name: string, data: Record<string, unknown>) => {
        if (name === "yetenek.detay") return new Promise<Record<string, unknown>>((coz) => { bekleyen[String(data.ad)] = coz; });
        return (base as unknown as { request: (n: string, d: Record<string, unknown>) => Promise<Record<string, unknown>> }).request(name, data);
      }),
    } as unknown as ProtocolClient;
    render(<SkillsCatalog client={yarisli} onClose={() => undefined} />);
    fireEvent.click(await screen.findByRole("button", { name: "frontend-design ayrıntılarını aç" }));
    fireEvent.click(screen.getByRole("button", { name: "reviewer ayrıntılarını aç" }));
    await waitFor(() => expect(Object.keys(bekleyen).length).toBe(2));
    bekleyen.reviewer({ ok: true, icerik: "REVIEWER ayrıntısı" });
    await screen.findByText("REVIEWER ayrıntısı");
    bekleyen["frontend-design"]({ ok: true, icerik: "FRONTEND ayrıntısı" });
    await new Promise((coz) => setTimeout(coz, 20));
    expect(screen.queryByText("FRONTEND ayrıntısı")).toBeNull();
    expect(screen.getByText("REVIEWER ayrıntısı")).toBeTruthy();
  });
});

describe("SkillsCatalog yenile ve teşhis (P-051)", () => {
  it("Yenile kataloğu yeniden çeker, Teşhis metnini ayrıntı panelinde gösterir", async () => {
    let katalogSayisi = 0;
    const c = {
      request: vi.fn(async (name: string) => {
        if (name === "yetenek.katalog") {
          katalogSayisi += 1;
          return { ok: true, beceriler: katalogSayisi === 1
            ? [{ ad: "ilk", aciklama: "", kaynak: "claude", tur: "beceri", etkin: true, izinler: [] }]
            : [
              { ad: "ilk", aciklama: "", kaynak: "claude", tur: "beceri", etkin: true, izinler: [] },
              { ad: "ikinci", aciklama: "", kaynak: "proje", tur: "beceri", etkin: true, izinler: [] },
            ] };
        }
        if (name === "yetenek.yenile") return { ok: true, beceri: 2, ajan: 0 };
        if (name === "yetenek.teshis") return { ok: true, bulgular: [], metin: "Beceri teşhisi: 2 beceri, 0 ajan tarandı. Sorun bulunmadı." };
        return { ok: true };
      }),
    } as unknown as ProtocolClient;
    render(<SkillsCatalog client={c} onClose={() => undefined} />);
    await screen.findByText("ilk");
    fireEvent.click(screen.getByRole("button", { name: "Yenile" }));
    expect(await screen.findByText("ikinci")).toBeTruthy();
    expect(c.request).toHaveBeenCalledWith("yetenek.yenile", {});
    fireEvent.click(screen.getByRole("button", { name: "Teşhis" }));
    expect((await screen.findByLabelText("Beceri teşhisi")).textContent).toContain("Sorun bulunmadı");
  });
});
