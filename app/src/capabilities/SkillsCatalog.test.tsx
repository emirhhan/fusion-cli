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
        ajanlar: [{ ad: "reviewer", aciklama: "Kodu inceler", kaynak: "claude", tur: "ajan", etkin: false, izinler: ["dosya okuma", "komut çalıştırma"], ayarlar: { model: "openrouter/a/b", izin_kipi: "plan", en_fazla_tur: 5, yasak_araclar: ["Bash"] } }],
        talimatlar: [{ ad: "CLAUDE.md", kaynak: "proje", tur: "talimat", aciklama: "Proje talimatı", etkin: true, izinler: [] }],
        mcp: [{ ad: "github", aciklama: "GitHub araçları", kaynak: "fusion", tur: "mcp", etkin: true, izinler: ["dış araçlar"] }],
      };
      if (name === "yetenek.detay") return {
        ok: true, ...data, icerik: "Tam uzmanlık talimatı", kesildi: false,
        ...(data.ad === "reviewer" ? { bellek: { kapsam: "project", dizin: "/p/.fusion/ajan-bellek/reviewer", satir: 3, konular: ["testler"], metin: "# Fusion belleği\n- testler önce" } } : {}),
      };
      if (name === "yetenek.bellek_sil") return { ok: true, ad: data.ad, silindi: true };
      if (name === "yetenek.kullan") return { ok: true, ...data, sonraki_tur: true, fork: data.ad === "frontend-design" };
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

  it("ajan ayrıntısında tanımdaki ayarları Türkçe etiketle gösterir (P-034)", async () => {
    render(<SkillsCatalog client={client()} onClose={() => undefined} />);
    await screen.findByText("reviewer");
    fireEvent.click(screen.getByRole("button", { name: "reviewer ayrıntılarını aç" }));
    const ayarlar = screen.getByLabelText("Ajan ayarları");
    expect(ayarlar.textContent).toContain("Modelopenrouter/a/b");
    expect(ayarlar.textContent).toContain("İzin kipiplan");
    expect(ayarlar.textContent).toContain("En fazla tur5");
    expect(ayarlar.textContent).toContain("Yasak araçlarBash");
    // Ayarı olmayan beceride liste hiç çizilmez.
    fireEvent.click(screen.getByRole("button", { name: "frontend-design ayrıntılarını aç" }));
    expect(screen.queryByLabelText("Ajan ayarları")).toBeNull();
  });

  it("ajan belleğini gösterir ve silebilir (P-055)", async () => {
    const fake = client();
    render(<SkillsCatalog client={fake} onClose={() => undefined} />);
    await screen.findByText("reviewer");
    fireEvent.click(screen.getByRole("button", { name: "reviewer ayrıntılarını aç" }));
    const bellek = await screen.findByLabelText("Ajan belleği");
    expect(bellek.textContent).toContain("Kalıcı bellek · proje");
    expect(bellek.textContent).toContain("3 satır");
    expect(bellek.textContent).toContain("testler önce");
    // Ölçüldü (31 Ekim): tek tık onaysız rmtree çalıştırıyordu; silme iki adımlıdır ve
    // "Vazgeç" hiçbir istek göndermez.
    fireEvent.click(screen.getByRole("button", { name: "Belleği sil" }));
    fireEvent.click(screen.getByRole("button", { name: "Vazgeç" }));
    expect(fake.request).not.toHaveBeenCalledWith("yetenek.bellek_sil", expect.anything());
    fireEvent.click(screen.getByRole("button", { name: "Belleği sil" }));
    expect(bellek.textContent).toContain("geri alınamaz");
    fireEvent.click(screen.getByRole("button", { name: "Evet, sil" }));
    await waitFor(() => expect(fake.request).toHaveBeenCalledWith("yetenek.bellek_sil", { ad: "reviewer" }));
    await waitFor(() => expect(screen.getByLabelText("Ajan belleği").textContent).toContain("Henüz boş"));
    // Bellek alanı olmayan beceride bölüm yok.
    fireEvent.click(screen.getByRole("button", { name: "frontend-design ayrıntılarını aç" }));
    await screen.findByText("Tam uzmanlık talimatı");
    expect(screen.queryByLabelText("Ajan belleği")).toBeNull();
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
    // `context: fork` beceri: kullanıcı turun bağlamı devralan alt ajanda koşacağını görür (P-054).
    expect((await screen.findByText(/alt ajanda koşacak/)).textContent).toContain("frontend-design");
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
