import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { ActivityLine } from "./ActivityLine";
import type { OlayAdimi } from "../protocol/olayMetni";

afterEach(cleanup);

const CALISAN_ADIM: OlayAdimi = { metin: "düşünüyor" };

describe("ActivityLine — süre sayacı", () => {
  /* Bkz. bug: kullanıcı başka bir sekmeye/sayfaya gidip dönünce (bileşen
     unmount/mount olunca) sayaç "25 sn" iken sıfıra dönüyordu. Sayaç artık
     `baslangicZamani` (oturumda saklanan sabit zaman) ile hesaplanıyor;
     yeniden bağlanma bu değeri değiştirmez, o yüzden sayaç KALDIĞI YERDEN
     devam etmeli. */
  test("bileşen yeniden bağlanınca (unmount/mount) sayaç sıfırlanmaz, aynı baslangicZamani'dan devam eder", () => {
    vi.useFakeTimers();
    try {
      const baslangicZamani = Date.now();
      const { unmount } = render(<ActivityLine adimlar={[CALISAN_ADIM]} baslangicZamani={baslangicZamani} />);

      act(() => { vi.advanceTimersByTime(25_000); });
      expect(screen.getByText("25 sn")).toBeTruthy();

      // Sekme değişimi: bileşen kaldırılır ve yeniden takılır.
      unmount();
      act(() => { vi.advanceTimersByTime(5_000); });
      render(<ActivityLine adimlar={[CALISAN_ADIM]} baslangicZamani={baslangicZamani} />);

      // Aynı başlangıçtan hesaplandığı için 0'a değil 30 sn'ye devam etmeli.
      expect(screen.getByText("30 sn")).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });

  test("baslangicZamani verilmezse (eski/eksik durum) sayaç basılmaz ama çalışıyor satırı görünür", () => {
    render(<ActivityLine adimlar={[CALISAN_ADIM]} />);
    expect(screen.getByText("düşünüyor")).toBeTruthy();
    expect(screen.queryByText(/sn$/)).toBeNull();
  });
});

describe("ActivityLine — kalıcı adım izi (Claude gibi)", () => {
  test("biten iş kaybolmaz, tıklanabilir özet bırakır; çalışırken biten adımlar görünür kalır", () => {
    const adimlar = [
      { metin: "a.py okunuyor", arac: "read_file", durum: "ok" },
      { metin: "'x' web'de aranıyor", arac: "web_search", basladi: true },
    ];
    const { container, rerender } = render(<ActivityLine adimlar={adimlar} baslangicZamani={Date.now()} />);
    expect(container.querySelector(".activity__trail")?.textContent).toContain("a.py okunuyor");
    expect(container.querySelector(".activity__pulse")?.textContent).toBe("'x' web'de aranıyor");

    rerender(<ActivityLine aktif={false} adimlar={[adimlar[0], { ...adimlar[1], basladi: false, durum: "ok" }]} />);
    const ozet = container.querySelector(".activity__summary summary");
    expect(ozet?.textContent).toBe("2 adım · 'x' web'de aranıyor");
  });

  test("ayrıntısı olan adım tek satırdır ve tıklanınca diff/komut/çıktı görünür", () => {
    const adimlar = [
      { metin: "src/app.py yazılıyor", arac: "write_file", durum: "ok", diff: "--- a\n+++ b\n+x = 1" },
      { metin: "pytest çalıştırılıyor", arac: "run_shell", durum: "ok", komut: "pytest -q", cikti: "3 passed" },
      { metin: "a.py okunuyor", arac: "read_file", durum: "ok" },
    ];
    const { container } = render(<ActivityLine aktif={false} adimlar={adimlar} />);
    const satirlar = container.querySelectorAll(".activity__trail > li");
    expect(satirlar).toHaveLength(3);
    const acilir = container.querySelectorAll(".activity__trail-item");
    expect(acilir).toHaveLength(2);
    expect(acilir[0].querySelector("summary")?.textContent).toContain("src/app.py yazılıyor");
    expect(acilir[0].querySelector('.diff-card__line[data-kind="add"]')?.textContent).toBe("+x = 1");
    expect(acilir[1].querySelector(".activity__trail-command")?.textContent).toBe("$ pytest -q");
    expect(acilir[1].querySelector(".activity__trail-output")?.textContent).toBe("3 passed");
    expect((acilir[0] as HTMLDetailsElement).open).toBe(false);
  });

  test("öğretmen ve hafıza adımları araç olmasa da izde kalır", () => {
    const adimlar = [
      { metin: "düşünüyor" },
      { metin: "öğretmene danışıldı: plan alındı", ayrinti: "3 adım", kalici: true },
      { metin: "hafızadan ilerleniyor", ayrinti: "3 adım · benzerlik 0.62", kalici: true },
    ];
    const { container } = render(<ActivityLine aktif={false} adimlar={adimlar} />);
    const ozet = container.querySelector(".activity__summary summary");
    expect(ozet?.textContent).toBe("2 adım · hafızadan ilerleniyor");
    expect(container.querySelector(".activity__trail")?.textContent).toContain("öğretmene danışıldı");
    expect(container.querySelector(".activity__trail")?.textContent).not.toContain("düşünüyor");
  });
});
