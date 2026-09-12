import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { Markdown } from "./Markdown";

afterEach(cleanup);

describe("Markdown", () => {
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
