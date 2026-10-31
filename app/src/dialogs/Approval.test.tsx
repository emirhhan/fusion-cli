import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Approval, KARAR_KORUMA_MS } from "./Approval";

/** Kart açıldıktan sonra kullanıcının bilinçli tuşuna izin veren koruma süresini geçirir. */
const korumaGec = () => vi.advanceTimersByTime(KARAR_KORUMA_MS + 1);

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

beforeEach(() => { vi.useFakeTimers({ toFake: ["Date"] }); });
afterEach(() => { cleanup(); vi.useRealTimers(); });

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
    const view = render(<Approval soru={temel} onCevap={onCevap} />);
    fireEvent.click(screen.getByRole("button", { name: /Hayır/ }));
    expect(onCevap).toHaveBeenLastCalledWith({ secim: "deny" });
    view.rerender(<Approval soru={{ ...temel }} onCevap={onCevap} />);
    korumaGec();
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

describe("Approval — karar notu ve izin kuralı (P-013, P-001)", () => {
  const notlu = { ...temel, not_alinir: true, kural: "Bash(git push *)" };

  it("Tab not kutusunu açar; dolu not kararla birlikte `not` alanında gider", () => {
    const onCevap = vi.fn();
    render(<Approval soru={notlu} onCevap={onCevap} />);
    expect(screen.getByText("Bash(git push *)")).toBeTruthy();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Tab" });
    const kutu = screen.getByLabelText("Karar notu");
    expect(document.activeElement).toBe(kutu);
    fireEvent.change(kutu, { target: { value: "  önce testleri yaz " } });
    fireEvent.click(screen.getByRole("button", { name: /Hayır/ }));
    expect(onCevap).toHaveBeenLastCalledWith({ secim: "deny", not: "önce testleri yaz" });
  });

  it("boş not alan eklemez; `not_alinir` yoksa not düğmesi yoktur", () => {
    const onCevap = vi.fn();
    const view = render(<Approval soru={notlu} onCevap={onCevap} />);
    fireEvent.click(screen.getByRole("button", { name: /Not ekle/ }));
    fireEvent.click(screen.getByRole("button", { name: "Evet" }));
    expect(onCevap).toHaveBeenLastCalledWith({ secim: "once" });
    view.rerender(<Approval soru={{ ...temel }} onCevap={onCevap} />);
    expect(screen.queryByRole("button", { name: /Not ekle/ })).toBeNull();
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

describe("Approval — yazarken beliren kart (WP16 madde 2)", () => {
  // Ölçüldü (29 Ekim): kart bağlanınca odağı kendine alır; kullanıcı composer'a
  // yazarken (ör. "12" ya da basılı tutulan tuş) sonraki rakam tuşu ilk seçeneği
  // (çoğu zaman "Evet") onay/geri alma olmadan seçiyordu.
  it("kart yeni açıldıysa rakam tuşu karar vermez; koruma süresinden sonra verir", () => {
    const onCevap = vi.fn();
    render(<Approval soru={temel} onCevap={onCevap} />);
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "1" });
    expect(onCevap).not.toHaveBeenCalled();
    korumaGec();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "1" });
    expect(onCevap).toHaveBeenCalledWith({ secim: "once" });
  });

  it("basılı tutulan tuş (repeat) koruma bitse bile karar vermez", () => {
    const onCevap = vi.fn();
    render(<Approval soru={temel} onCevap={onCevap} />);
    korumaGec();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "1", repeat: true });
    expect(onCevap).not.toHaveBeenCalled();
  });

  it("odaktaki karta Enter basmak tek başına karar vermez", () => {
    const onCevap = vi.fn();
    render(<Approval soru={temel} onCevap={onCevap} />);
    korumaGec();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Enter" });
    expect(onCevap).not.toHaveBeenCalled();
  });

  it("tehlikeli işlemde de aynı koruma geçerlidir ve Esc reddi seçmeye devam eder", () => {
    const onCevap = vi.fn();
    render(<Approval soru={{ ...temel, tehlike: "dosya siler" }} onCevap={onCevap} />);
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "1" });
    expect(onCevap).not.toHaveBeenCalled();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onCevap).toHaveBeenCalledWith({ secim: "deny" });
  });

  it("kendiliğinden açılan metin kutusunda koruma süresince Enter cevabı göndermez", () => {
    const onCevap = vi.fn();
    render(<Approval soru={{ tur: "soru", soru: "Proje adı ne olsun?" }} onCevap={onCevap} />);
    const kutu = screen.getByLabelText("Cevabın");
    fireEvent.change(kutu, { target: { value: "yazarken-kalan" } });
    const enter = fireEvent.keyDown(kutu, { key: "Enter" });
    expect(enter).toBe(false);
    korumaGec();
    expect(fireEvent.keyDown(kutu, { key: "Enter" })).toBe(true);
  });

  it("seçenek varken Esc, metin kutusundayken boş cevap göndermez; yalnız kutuyu kapatır", () => {
    const onCevap = vi.fn();
    const soru = { tur: "soru" as const, soru: "Hangisi?", secenekler: [{ etiket: "Astro" }] };
    render(<Approval soru={soru} onCevap={onCevap} />);
    fireEvent.click(screen.getByRole("button", { name: /Diğer/ }));
    fireEvent.keyDown(screen.getByLabelText("Cevabın"), { key: "Escape" });
    expect(onCevap).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Cevabın")).toBeNull();
  });

  // Ölçüldü (29 Ekim): `tur:"onay"` seçeneksiz gelirse kartta düğme yoktu, Esc de
  // bir şey yapmıyordu; tur yalnız Durdur ile kurtuluyordu.
  it("seçeneksiz gelen onay kartı yerleşik İzin ver / Reddet düğmeleri üretir", () => {
    const onCevap = vi.fn();
    render(<Approval soru={{ tur: "onay", arac: "run_shell", baslik: "Çalışsın mı?" }} onCevap={onCevap} />);
    expect(screen.getByRole("button", { name: /İzin ver/ })).toBeTruthy();
    fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
    expect(onCevap).toHaveBeenCalledWith({ secim: "deny" });
  });

  // Ölçüldü (30 Ekim): aynı etiketli iki seçenek React key uyarısı ve yanlış düğme durumu üretiyordu;
  // nesne argüman "[object Object]" yazıyordu (U4-15).
  it("aynı etiketli seçenekler ayrı düğme olur, nesne argüman JSON olarak gösterilir (U4-15)", () => {
    const hata = vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(<Approval soru={{
      tur: "soru", soru: "Hangisi?", secenekler: [{ etiket: "Evet" }, { etiket: "Evet" }],
      argumanlar: { ayar: { a: 1 } } as never,
    }} onCevap={vi.fn()} />);
    expect(screen.getAllByRole("button", { name: /Evet/ })).toHaveLength(2);
    expect(hata.mock.calls.flat().join(" ")).not.toContain("same key");
    hata.mockRestore();
    cleanup();
    render(<Approval soru={{ ...temel, argumanlar: { ayar: { a: 1 } } as never }} onCevap={vi.fn()} />);
    expect(screen.getByText('ayar={"a":1}')).toBeTruthy();
  });
});
