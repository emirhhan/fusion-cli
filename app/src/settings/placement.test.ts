import { beforeEach, describe, expect, test, vi } from "vitest";
import {
  getPlacement,
  PLACEMENT_KEY,
  readPlacement,
  resetPlacementCache,
  savePlacement,
  setPlacement,
  subscribePlacement,
} from "./placement";

beforeEach(() => {
  localStorage.clear();
  resetPlacementCache();
});

describe("çalışma paneli yerleşimi", () => {
  test("varsayılan sağdadır", () => {
    expect(readPlacement()).toBe("right");
  });

  test("yalnız 'bottom' değeri alt yerleşim sayılır", () => {
    localStorage.setItem(PLACEMENT_KEY, "bottom");
    expect(readPlacement()).toBe("bottom");

    localStorage.setItem(PLACEMENT_KEY, "alt");
    expect(readPlacement()).toBe("right");
  });

  test("kaydedilen değer geri okunur", () => {
    savePlacement("bottom");
    expect(readPlacement()).toBe("bottom");
  });

  /* Özel pencerede depo erişimi istisna fırlatabiliyor; bir tercih okunamadı
     diye uygulamanın açılmaması kabul edilemez. */
  test("depo okunamazsa varsayılana düşer, istisna sızdırmaz", () => {
    const bozuk = {
      getItem: vi.fn(() => {
        throw new Error("erişim yok");
      }),
    };
    expect(readPlacement(bozuk)).toBe("right");
  });

  test("depo yazılamazsa istisna sızdırmaz", () => {
    const bozuk = {
      setItem: vi.fn(() => {
        throw new Error("kota dolu");
      }),
    };
    expect(() => savePlacement("bottom", bozuk)).not.toThrow();
  });

  test("değişiklik abonelere duyurulur", () => {
    const dinleyici = vi.fn();
    const birak = subscribePlacement(dinleyici);

    setPlacement("bottom");

    expect(dinleyici).toHaveBeenCalledTimes(1);
    expect(getPlacement()).toBe("bottom");
    birak();
  });
});
