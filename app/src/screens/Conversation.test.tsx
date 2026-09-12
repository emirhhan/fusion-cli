import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Conversation } from "./Conversation";

afterEach(cleanup);

describe("Conversation", () => {
  it("kullanıcıyı balonda, Fusion yanıtını balonsuz makalede gösterir", () => {
    const { container } = render(
      <Conversation
        mesajlar={[
          { rol: "kullanici", metin: "Bir oyun yap" },
          { rol: "asistan", metin: "Oyunu hazırladım." },
        ]}
      />,
    );
    expect(container.querySelector(".conversation__message--user")).toBeTruthy();
    expect(screen.getByRole("article", { name: "Fusion yanıtı" })).toBeTruthy();
    expect(container.querySelector(".conversation__message--assistant")?.className).not.toContain(
      "conversation__bubble",
    );
    expect(screen.getByText("Siz")).toBeTruthy();
    expect(screen.getByText("Fusion")).toBeTruthy();
  });

  it("Fusion yanıtını markdown olarak çizer; kodu kendi kartına alır", () => {
    const { container } = render(
      <Conversation
        mesajlar={[{ rol: "asistan", metin: "## Kurulum\n\n```python\nprint(1)\n```" }]}
      />,
    );
    expect(container.querySelector("h2")?.textContent).toBe("Kurulum");
    expect(container.querySelector(".code-card")).not.toBeNull();
  });

  it("mesaj geçmişini canlı bölge yapmaz; işlem durumunu ayrı canlı bölgede sunar", () => {
    const { container } = render(
      <Conversation
        mesajlar={[{
          rol: "olay",
          metin: "düşünüyor",
          adimlar: [{ metin: "düşünüyor", ayrinti: "agent · model" }],
        }]}
      />,
    );
    expect(container.querySelector(".conversation__stream")?.hasAttribute("aria-live")).toBe(false);
    expect(screen.getByRole("status").textContent).toBe("Çalışıyor");
  });

  it("çalışırken tek satır gösterir; kutu, ikon ve 'Çalışma' başlığı çizmez", () => {
    const { container } = render(
      <Conversation
        mesajlar={[{ rol: "olay", metin: "dosya yazıyor", adimlar: [{ metin: "dosya yazıyor" }] }]}
      />,
    );
    expect(screen.queryByText("Çalışma")).toBeNull();
    expect(container.querySelector(".activity__pulse")?.textContent).toBe("dosya yazıyor");
    expect(container.querySelector('[data-state="running"]')).not.toBeNull();
    expect(container.querySelector("details")).toBeNull();
  });

  /* Kullanıcının ölçülmüş şikayeti: basit bir soruda bile cevabın üstünde yeşil
     tikli bir "Tamamlandı" bloğu kalıyordu. Biten iş iz BIRAKMAMALI. */
  it("tamamlanan iş hiçbir iz bırakmaz", () => {
    const { container } = render(
      <Conversation
        mesajlar={[{
          rol: "olay",
          metin: "görev tamamlandı",
          adimlar: [{ metin: "görev tamamlandı", sonuc: "completed" }],
        }]}
      />,
    );
    expect(container.querySelector(".activity")).toBeNull();
    expect(container.textContent).not.toContain("Tamamlandı");
    expect(screen.getByRole("status").textContent).toBe("");
  });

  it("adım dökümü açıkken tamamlanan iş katlanmış özet bırakır", () => {
    render(
      <Conversation
        showSteps
        mesajlar={[{
          rol: "olay",
          metin: "görev tamamlandı",
          adimlar: [
            { metin: "düşünüyor", ayrinti: "agent · model" },
            { metin: "araç çalıştı: write_file", ayrinti: "index.html", sonuc: "completed" },
          ],
        }]}
      />,
    );
    const ozet = screen.getByText("2 adım · detaylar");
    expect(ozet.closest("details")?.hasAttribute("open")).toBe(false);
    expect(screen.getByText("index.html")).toBeTruthy();
  });

  it.each([
    ["failed", "Tamamlanamadı"],
    ["partial", "Kısmen tamamlandı"],
  ] as const)("%s sonucu kaybolmaz; sebebiyle görünür kalır", (sonuc, etiket) => {
    const { container } = render(
      <Conversation
        mesajlar={[{
          rol: "olay",
          metin: "adım düştü",
          adimlar: [{ metin: "adım düştü", ayrinti: "agent adım bütçesi doldu", sonuc }],
        }]}
      />,
    );
    const satir = container.querySelector(`[data-state="${sonuc}"]`);
    expect(satir?.textContent).toContain(etiket);
    expect(satir?.textContent).toContain("agent adım bütçesi doldu");
    expect(satir?.textContent).not.toContain("Tamamlandı");
  });

  it("başarısızlığı ekran okuyucuya duyurur, başarıyı duyurmaz", () => {
    const { rerender } = render(
      <Conversation
        mesajlar={[{ rol: "olay", metin: "düştü", adimlar: [{ metin: "düştü", sonuc: "failed" }] }]}
      />,
    );
    expect(screen.getByRole("status").textContent).toBe("Tamamlanamadı");

    rerender(
      <Conversation
        mesajlar={[{ rol: "olay", metin: "bitti", adimlar: [{ metin: "bitti", sonuc: "completed" }] }]}
      />,
    );
    expect(screen.getByRole("status").textContent).toBe("");
  });

  it("uzun ve satır sonlu metni güvenli metin akışında korur", () => {
    const { container } = render(
      <Conversation mesajlar={[{ rol: "asistan", metin: "ilk satır\nikinci satır" }]} />,
    );
    expect(container.querySelector(".conversation__text")?.textContent).toContain("ikinci satır");
  });
});

describe("Conversation — gönderilen ekler", () => {
  it("görsel eki küçük önizlemeyle gösterir", () => {
    render(
      <Conversation
        mesajlar={[{
          rol: "kullanici",
          metin: "şunu incele",
          ekler: [{ kind: "image", name: "ekran.png", path: "/tmp/ekran.png" }],
        }]}
      />,
    );
    // Kabuk yokken önizleme adresi üretilemez; ad yine görünür.
    expect(screen.getByText("ekran.png")).toBeTruthy();
  });

  it("eksiz mesajda ek bölümü hiç çizilmez", () => {
    render(<Conversation mesajlar={[{ rol: "kullanici", metin: "merhaba" }]} />);
    expect(screen.queryByLabelText("Gönderilen ekler")).toBeNull();
  });
});
