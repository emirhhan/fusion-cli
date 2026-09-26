import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Approval } from "./Approval";

const temel = {
  tur: "onay" as const,
  arac: "run_shell",
  baslik: "Bu komut çalıştırılsın mı?",
  hedef: "git push",
  argumanlar: ["command='git push'"],
  tehlike: null,
  secenekler: [
    { deger: "once", etiket: "Evet" },
    { deger: "session", etiket: "Evet, bu oturumda bunu tekrar sorma" },
    { deger: "deny", etiket: "Hayır, başka bir yol dene" },
  ],
};

afterEach(cleanup);

describe("Approval — izin kartı", () => {
  it("insan dilinde başlığı ve hedefi olduğu gibi gösterir; ham argüman ayrıntıda kalır", () => {
    render(<Approval soru={temel} onCevap={vi.fn()} />);
    expect(screen.getByRole("heading").textContent).toBe("Bu komut çalıştırılsın mı?");
    expect(screen.getByText("git push")).toBeTruthy();
    expect(screen.getByText("command='git push'").closest("details")).toBeTruthy();
  });

  it("çekirdeğin çıkardığı oturum seçeneğini yeniden eklemez ve tehlikeyi yazar", () => {
    const yikici = {
      ...temel,
      tehlike: "dosya siler",
      secenekler: temel.secenekler.filter((secenek) => secenek.deger !== "session"),
    };
    render(<Approval soru={yikici} onCevap={vi.fn()} />);
    expect(screen.queryByText("Evet, bu oturumda bunu tekrar sorma")).toBeNull();
    expect(screen.getByText(/dosya siler/)).toBeTruthy();
  });

  it("tıklama ve sayı tuşu seçimi `secim` olarak bildirir", () => {
    const onCevap = vi.fn();
    render(<Approval soru={temel} onCevap={onCevap} />);
    fireEvent.click(screen.getByRole("button", { name: /Hayır/ }));
    expect(onCevap).toHaveBeenLastCalledWith({ secim: "deny" });
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "2" });
    expect(onCevap).toHaveBeenLastCalledWith({ secim: "session" });
  });

  it("açılınca karta odaklanır, modal değildir ve Escape güvenli reddi seçer", () => {
    const onCevap = vi.fn();
    render(<Approval soru={temel} onCevap={onCevap} />);
    expect(document.activeElement).toBe(screen.getByRole("dialog"));
    expect(screen.getByRole("dialog").hasAttribute("aria-modal")).toBe(false);
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onCevap).toHaveBeenCalledWith({ secim: "deny" });
  });

  it("ilk olumlu seçeneği önerilen olarak işaretler", () => {
    render(<Approval soru={temel} onCevap={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Evet" }).getAttribute("data-recommended")).toBe("true");
  });

  it("düzenleme onayında ne değişeceğini diff olarak gösterir", () => {
    render(
      <Approval
        onCevap={() => undefined}
        soru={{
          tur: "onay",
          arac: "write_file",
          baslik: "Bu dosya yazılsın mı?",
          hedef: "stokapp/fiyat.py",
          diff: "--- a/stokapp/fiyat.py\n+++ b/stokapp/fiyat.py\n@@ -1 +1 @@\n-KDV = 0.18\n+KDV = 0.20\n",
          secenekler: [{ deger: "once", etiket: "Evet" }],
        }}
      />,
    );
    expect(screen.getByText("KDV = 0.20", { exact: false })).toBeTruthy();
  });
});

describe("Approval — soru kartı (ask_user)", () => {
  const soru = {
    tur: "soru" as const,
    soru: "Blog hangi teknolojiyle kurulsun?",
    secenekler: [
      { etiket: "Next.js", aciklama: "React tabanlı, SEO dostu" },
      { etiket: "Astro", aciklama: "İçerik odaklı, hızlı" },
    ],
    onerilen: "Next.js",
  };

  it("seçilen seçeneği `metin` olarak gönderir (eskiden cevap boş gidiyordu)", () => {
    const onCevap = vi.fn();
    render(<Approval soru={soru} onCevap={onCevap} />);
    expect(screen.getByText("Fusion soruyor")).toBeTruthy();
    expect(screen.getByText("Önerilen")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Astro/ }));
    expect(onCevap).toHaveBeenCalledWith({ metin: "Astro" });
  });

  it("Diğer ile serbest cevap yazılabilir", () => {
    const onCevap = vi.fn();
    render(<Approval soru={soru} onCevap={onCevap} />);
    fireEvent.click(screen.getByRole("button", { name: /Diğer/ }));
    const kutu = screen.getByLabelText("Cevabın");
    fireEvent.change(kutu, { target: { value: "SvelteKit" } });
    fireEvent.submit(kutu.closest("form")!);
    expect(onCevap).toHaveBeenCalledWith({ metin: "SvelteKit" });
  });

  it("seçeneksiz soruda doğrudan metin kutusu açılır; Escape soruyu boş cevapla atlar", () => {
    const onCevap = vi.fn();
    render(<Approval soru={{ tur: "soru", soru: "Proje adı ne olsun?" }} onCevap={onCevap} />);
    expect(document.activeElement).toBe(screen.getByLabelText("Cevabın"));
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onCevap).toHaveBeenCalledWith({ metin: "" });
  });
});
