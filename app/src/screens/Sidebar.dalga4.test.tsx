import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Sidebar, pinAnahtari, readProjectPreferences } from "./Sidebar";

const sohbet = (extra = {}) => ({
  session_id: "c1", source: "fusion" as const, title: "Birinci sohbet", updated_at: 5,
  project: "Mağaza", projectRoot: "/Users/t/magaza", ...extra,
});
const kur = (props = {}) => render(<Sidebar etkin={null} oturumlar={[sohbet()]} onSec={vi.fn()} onYeni={vi.fn()} {...props} />);

beforeEach(() => localStorage.clear());
afterEach(cleanup);

describe("Sidebar — dalga 4 P2/P3", () => {
  it("sabitleme anahtarı sohbet taşınınca değişmez (U1-50)", () => {
    expect(pinAnahtari("fusion", "c1")).toBe("fusion:c1");
    localStorage.setItem("fusion.sidebar.pinned-sessions.v1", JSON.stringify(["/Users/t/magaza:fusion:c1"]));
    const { rerender } = kur();
    expect(screen.getByRole("region", { name: "Sabitlenenler" }).textContent).toContain("Birinci sohbet");
    rerender(<Sidebar etkin={null} oturumlar={[sohbet({ projectRoot: "/Users/t/baska", project: "Başka" })]} onSec={vi.fn()} onYeni={vi.fn()} />);
    expect(screen.getByRole("region", { name: "Sabitlenenler" }).textContent).toContain("Birinci sohbet");
  });

  it("bozuk proje tercihi kenar çubuğunu çökertmez (U1-51)", () => {
    localStorage.setItem("fusion.sidebar.projects.v1", JSON.stringify({
      "/Users/t/magaza": { name: { bozuk: true }, hidden: "evet", pinned: 3 },
      "/x": "metin", "/y": null,
    }));
    expect(readProjectPreferences()).toEqual({ "/Users/t/magaza": {} });
    expect(() => kur()).not.toThrow();
  });

  it("arama kapatılınca süzgeç temizlenir ve Esc aramayı kapatır (U1-52)", () => {
    kur();
    const ac = screen.getByRole("button", { name: "Konuşma ve proje aramasını aç" });
    fireEvent.click(ac);
    fireEvent.change(screen.getByRole("searchbox", { name: "Konuşma ve proje ara" }), { target: { value: "yok böyle bir şey" } });
    expect(screen.queryByText("Birinci sohbet")).toBeNull();
    fireEvent.keyDown(screen.getByRole("searchbox", { name: "Konuşma ve proje ara" }), { key: "Escape" });
    expect(screen.queryByRole("searchbox")).toBeNull();
    expect(screen.getAllByText("Birinci sohbet").length).toBeGreaterThan(0);
  });

  it("proje diyaloğu Escape ile kapanır ve odağı geri verir (U1-54)", () => {
    kur({ onProjectCreate: vi.fn() });
    const yeni = screen.getByRole("button", { name: "Yeni proje" });
    yeni.focus();
    fireEvent.click(yeni);
    expect(screen.getByRole("dialog", { name: "Yeni proje" })).toBeTruthy();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(yeni);
  });

  it("sohbet menüsü Escape ile kapanınca odak ··· düğmesine döner (U1-55)", () => {
    kur();
    const dugme = screen.getByRole("button", { name: "Birinci sohbet sohbet seçenekleri" });
    fireEvent.click(dugme);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(document.activeElement).toBe(dugme);
  });

  it("silme/yeniden adlandırma geri çağırımı yoksa diyalog sessizce kapanmaz (U1-56)", async () => {
    const kayit = { id: "p1", name: "Mağaza", pinned: false, root: "", updated_at: 3 };
    kur({ projeler: [kayit], oturumlar: [] });
    fireEvent.click(screen.getByRole("button", { name: "Mağaza için proje seçeneklerini aç" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Projeyi sil" }));
    fireEvent.click(screen.getByRole("button", { name: "Projeyi sil" }));
    expect((await screen.findByRole("alert")).textContent).toContain("kullanılamıyor");
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("taşıma hatası 'Error:' öneki olmadan gösterilir (U1-60)", async () => {
    const hedef = { id: "p2", name: "Blog", pinned: false, root: "", updated_at: 4 };
    kur({ projeler: [hedef], onAssign: async () => { throw new Error("sunucu reddetti"); } });
    fireEvent.click(screen.getByRole("button", { name: "Birinci sohbet sohbet seçenekleri" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Blog" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("sunucu reddetti"));
  });
});
