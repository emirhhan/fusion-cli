import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Spotlight, isaretKutusu } from "./Spotlight";

afterEach(() => {
  cleanup();
  // Testlerin eklediği hedefler gövdede birikirse sonraki test yanlış öğeyi ölçer.
  document.querySelectorAll("[data-ders]").forEach((el) => el.remove());
});

function hedefKur(isaret: string, kutu: Partial<DOMRect> = {}) {
  const el = document.createElement("button");
  el.setAttribute("data-ders", isaret);
  el.getBoundingClientRect = () =>
    ({ top: 100, left: 50, width: 120, height: 32, ...kutu }) as DOMRect;
  document.body.append(el);
  return el;
}

describe("isaretKutusu", () => {
  it("işaretli öğeyi ölçer ve çevresine pay bırakır", () => {
    hedefKur("gorev-kutusu");
    expect(isaretKutusu("gorev-kutusu")).toEqual({ top: 92, left: 42, width: 136, height: 48 });
  });

  it("öğe yoksa ölçüm yapmaz", () => {
    expect(isaretKutusu("olmayan")).toBeNull();
  });

  it("görünmeyen öğeyi işaretlemez", () => {
    // Sıfır boyutlu öğe ekranda yoktur; üstüne ışık koymak boşluğu gösterirdi.
    hedefKur("kip", { width: 0, height: 0 });
    expect(isaretKutusu("kip")).toBeNull();
  });
});

describe("Spotlight", () => {
  it("öğe bulunamazsa hiçbir şey çizmez", () => {
    const { container } = render(
      <Spotlight isaret="olmayan" metin="şuraya bak" onClose={vi.fn()} />,
    );
    expect(container.querySelector(".spotlight")).toBeNull();
  });

  it("bulunan öğenin üstüne ışık ve açıklama koyar", () => {
    hedefKur("kip");
    render(<Spotlight isaret="kip" metin="Kipi buradan değiştirirsin." onClose={vi.fn()} />);
    expect(screen.getByText("Kipi buradan değiştirirsin.")).toBeTruthy();
  });

  it("kapatma düğmesi ışığı kaldırır", () => {
    hedefKur("kip");
    const onClose = vi.fn();
    render(<Spotlight isaret="kip" metin="x" onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: "Anladım" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("Escape ışığı kaldırır", () => {
    hedefKur("kip");
    const onClose = vi.fn();
    render(<Spotlight isaret="kip" metin="x" onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });
});

describe("Ders işaretleri arayüzde gerçekten var", () => {
  it("çekirdeğin bildiği her işaret bir arayüz öğesine karşılık gelir", async () => {
    // Bu test, çekirdekteki `KNOWN_MARKS` ile arayüzdeki `data-ders` arasındaki
    // bağı korur: biri değişip öteki unutulursa ders "olmayan bir düğmeyi"
    // gösterirdi.
    const { readFileSync } = await import("node:fs");
    const kaynaklar = [
      "src/screens/Composer.tsx",
      "src/screens/Sidebar.tsx",
    ].map((yol) => readFileSync(yol, "utf-8")).join("\n");

    const beklenen = [
      "gorev-kutusu",
      "kip",
      "ek",
      "izin",
      "mikrofon",
      "yeni-gorev",
      "arama",
      "gecmis",
      "kontrol-paneli",
      "dersler",
      "ayarlar",
    ];
    const eksik = beklenen.filter((isaret) => !kaynaklar.includes(`"${isaret}"`));
    expect(eksik).toEqual([]);
  });
});
