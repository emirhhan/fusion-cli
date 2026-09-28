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
