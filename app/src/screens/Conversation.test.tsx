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

  it("çalışma ve başarısızlık durumlarını ikonla ve metinle ayırt eder", () => {
    const { container } = render(
      <Conversation
        mesajlar={[
          { rol: "olay", metin: "dosya yazıyor", adimlar: [{ metin: "dosya yazıyor" }] },
          { rol: "olay", metin: "görev başarısız", adimlar: [{ metin: "görev başarısız", sonuc: true }] },
        ]}
      />,
    );
    expect(screen.getAllByText("Çalışma")).toHaveLength(2);
    expect(container.querySelector('[data-state="running"]')?.textContent).toContain("Çalışıyor");
    expect(container.querySelector('[data-state="failed"]')?.textContent).toContain("Başarısız");
    expect(screen.getByLabelText("Çalışıyor simgesi")).toBeTruthy();
    expect(screen.getByLabelText("Başarısız simgesi")).toBeTruthy();
  });

  it("ayrıntılı çalışma adımını açılabilir kutuda sunar", () => {
    render(
      <Conversation
        mesajlar={[{
          rol: "olay",
          metin: "araç çalıştı: write_file",
          adimlar: [{ metin: "araç çalıştı: write_file", ayrinti: "index.html" }],
        }]}
      />,
    );
    expect(screen.getByText("index.html").closest("details")).toBeTruthy();
  });

  it("tek ve ayrıntısız adımda açılır kutu açmaz; aynı cümleyi iki kez yazmaz", () => {
    render(<Conversation mesajlar={[{ rol: "olay", metin: "düşünüyor", adimlar: [{ metin: "düşünüyor" }] }]} />);
    expect(screen.getAllByText("düşünüyor")).toHaveLength(1);
    expect(screen.queryByRole("group")).toBeNull();
  });

  it("ardışık adımlar tek blokta ve sayısıyla görünür", () => {
    render(
      <Conversation
        mesajlar={[{
          rol: "olay",
          metin: "düşünüyor",
          adimlar: [
            { metin: "düşünüyor", ayrinti: "agent · openrouter/x" },
            { metin: "araç çalıştı: web_fetch", kaynak: "https://ornek.com" },
          ],
        }]}
      />,
    );
    expect(screen.getByText("2 adım")).toBeTruthy();
    expect(screen.getByRole("link", { name: "https://ornek.com" })).toBeTruthy();
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
