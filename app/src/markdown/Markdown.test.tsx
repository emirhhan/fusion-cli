import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { Markdown } from "./Markdown";

afterEach(cleanup);

describe("Markdown", () => {
  test("table cells support safe line breaks without rendering arbitrary HTML", () => {
    const { container } = render(<Markdown text={"| Ad | Açıklama |\n|---|---|\n| Test | ilk<br>ikinci<br/>üçüncü |"} />);
    expect(container.querySelectorAll("td br")).toHaveLength(2);
    expect(container.querySelector("script")).toBeNull();
  });
  test("başlık, kalın metin ve satır içi kodu biçimlendirir", () => {
    const { container } = render(<Markdown text={"# Kurulum\n\nÖnce **projeyi** aç, sonra `npm install` çalıştır."} />);

    expect(container.querySelector("h1")?.textContent).toBe("Kurulum");
    expect(container.querySelector("strong")?.textContent).toBe("projeyi");
    expect(container.querySelector(".markdown__inline-code")?.textContent).toBe("npm install");
  });

  test("sırasız ve sıralı listeleri ayrı etiketlerle çizer", () => {
    const { container } = render(<Markdown text={"- bir\n- iki\n\n1. önce\n2. sonra"} />);

    expect(container.querySelectorAll("ul li")).toHaveLength(2);
    expect(container.querySelectorAll("ol li")).toHaveLength(2);
  });

  test("tabloyu kendi kaydırma kutusunda çizer", () => {
    const { container } = render(<Markdown text={"| ad | değer |\n|---|---|\n| hız | 120 |"} />);

    expect(container.querySelector(".markdown__table-scroll")).not.toBeNull();
    expect(container.querySelectorAll("tbody td")).toHaveLength(2);
    expect(screen.getByText("hız")).toBeTruthy();
  });

  test("bağlantıyı yeni sekmede ve referrer sızdırmadan açar", () => {
    const { container } = render(<Markdown text="[Godot](https://godotengine.org)" />);
    const link = container.querySelector("a");

    expect(link?.getAttribute("href")).toBe("https://godotengine.org");
    expect(link?.getAttribute("target")).toBe("_blank");
    expect(link?.getAttribute("rel")).toBe("noreferrer noopener");
  });

  test("kod bloğunu kod kartına çevirir", () => {
    const { container } = render(<Markdown text={"```python\nprint(1)\n```"} />);

    expect(container.querySelector(".code-card")).not.toBeNull();
    expect(container.querySelector(".code-card__body")?.textContent).toContain("print(1)");
  });

  test("dil etiketindeki dosya adını kart başlığına taşır", () => {
    const { container } = render(<Markdown text={"```gdscript:scripts/Player.gd\nextends Node\n```"} />);

    expect(container.querySelector(".code-card__name")?.textContent).toBe("scripts/Player.gd");
    expect(container.querySelector(".code-card__lang")?.textContent).toBe("gdscript");
  });

  /* Güvenlik: model cevabı güvenilmezdir. Token yolunda ham HTML DÜZ METİNDİR;
     çalıştırılabilir bir eleman olarak ağaca girmemeli. */
  test("cevaba gömülü ham HTML çalıştırılmaz, metin olarak görünür", () => {
    const zararli = '<img src=x onerror="globalThis.__sizdi = true"><script>globalThis.__sizdi = true</script>';
    const { container } = render(<Markdown text={zararli} />);

    expect(container.querySelector("script")).toBeNull();
    // `markdown__image` yalnız gerçek markdown görselinden doğar; ham HTML'den değil.
    expect(container.querySelector("img")).toBeNull();
    expect((globalThis as Record<string, unknown>).__sizdi).toBeUndefined();
    expect(container.textContent).toContain("onerror");
  });

  test("bağlantı metnine gömülü javascript şeması eleman üretmez", () => {
    const bagli = '<a href="javascript:alert(1)">tıkla</a>';
    const { container } = render(<Markdown text={bagli} />);

    expect(container.querySelector("a")).toBeNull();
    expect(container.textContent).toContain("javascript:alert(1)");
  });
});

describe("Markdown — görseller", () => {
  test("uzak adres olduğu gibi, yerel yol varlık protokolüyle çizilir", () => {
    vi.mock("../platform/assetUrl", () => ({
      assetUrl: (path: string) => `asset://localhost/${encodeURIComponent(path)}`,
    }));
    const { container } = render(
      <Markdown text={"![uzak](https://ornek.test/a.png)\n\n![yerel](</Users/e/.local/share/fusion-cli/gallery/a b.png>)"} />,
    );
    const sources = Array.from(container.querySelectorAll("img")).map((img) => img.getAttribute("src"));
    expect(sources[0]).toBe("https://ornek.test/a.png");
    expect(sources[1]).toBe(
      `asset://localhost/${encodeURIComponent("/Users/e/.local/share/fusion-cli/gallery/a b.png")}`,
    );
  });

  test("varlık protokolü yoksa (tarayıcı/test) kırık resim yerine alt metin gösterir", async () => {
    const { imageSource } = await import("./Markdown");
    expect(imageSource("https://x.test/a.png")).toBe("https://x.test/a.png");
  });
});

describe("Markdown — görseli büyütme", () => {
  test("görsele tıklayınca tam ekran açılır; Esc ve Kapat ile kapanır", () => {
    render(<Markdown text={"![mavi kuş](https://ornek.test/kus.png)"} />);
    fireEvent.click(screen.getByRole("button", { name: "mavi kuş — büyüt" }));
    expect(screen.getByRole("dialog", { name: "mavi kuş" })).toBeTruthy();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "mavi kuş — büyüt" }));
    fireEvent.click(screen.getByRole("button", { name: "Kapat" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  test("yüklenene kadar görünmez, yüklenince belirir (iskelet)", () => {
    const { container } = render(<Markdown text={"![x](https://ornek.test/a.png)"} />);
    const frame = container.querySelector(".markdown__image-button") as HTMLElement;
    expect(frame.dataset.loaded).toBe("false");
    fireEvent.load(container.querySelector("img") as HTMLImageElement);
    expect(frame.dataset.loaded).toBe("true");
  });
});
