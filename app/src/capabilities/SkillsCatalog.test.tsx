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

describe("SkillsCatalog", () => {
  it("kaynakları, izinleri ve birleşik Claude/Codex etiketini gösterir", async () => {
    render(<SkillsCatalog client={client()} onClose={() => undefined} />);
    expect(await screen.findByText("frontend-design")).toBeTruthy();
    expect(screen.getByText("[claude] [codex]")).toBeTruthy();
    expect(screen.getAllByText("dosya okuma").length).toBeGreaterThan(0);
    expect(screen.getByText("github")).toBeTruthy();
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
