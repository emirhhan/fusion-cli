import { beforeEach, describe, expect, test, vi } from "vitest";
import {
  getShowSteps,
  readShowSteps,
  resetShowStepsCache,
  saveShowSteps,
  setShowSteps,
  STEPS_STORAGE_KEY,
  subscribeShowSteps,
} from "./preferences";

beforeEach(() => {
  localStorage.clear();
  resetShowStepsCache();
});

describe("adım gösterme tercihi", () => {
  test("hiç kaydedilmemişse kapalıdır", () => {
    expect(readShowSteps()).toBe(false);
  });

  test("yalnız 'true' değeri açık sayılır", () => {
    localStorage.setItem(STEPS_STORAGE_KEY, "true");
    expect(readShowSteps()).toBe(true);

    localStorage.setItem(STEPS_STORAGE_KEY, "evet");
    expect(readShowSteps()).toBe(false);
  });

  test("kaydedilen değer geri okunur", () => {
    saveShowSteps(true);
    expect(readShowSteps()).toBe(true);
  });

  /* Özel pencerede `localStorage` erişimi istisna fırlatabiliyor. Bir tercih
     okunamadı diye sohbetin açılmaması kabul edilemez. */
  test("depo okunamazsa kapalıya düşer, istisna sızdırmaz", () => {
    const bozuk = {
      getItem: vi.fn(() => {
        throw new Error("erişim yok");
      }),
    };
    expect(readShowSteps(bozuk)).toBe(false);
  });

  test("depo yazılamazsa istisna sızdırmaz", () => {
    const bozuk = {
      setItem: vi.fn(() => {
        throw new Error("kota dolu");
      }),
    };
    expect(() => saveShowSteps(true, bozuk)).not.toThrow();
  });
});

describe("paylaşılan tercih deposu", () => {
  test("değişiklik abonelere duyurulur ve okunan değer güncellenir", () => {
    const dinleyici = vi.fn();
    const birak = subscribeShowSteps(dinleyici);

    setShowSteps(true);

    expect(dinleyici).toHaveBeenCalledTimes(1);
    expect(getShowSteps()).toBe(true);
    birak();
  });

  test("abonelik bırakıldıktan sonra duyuru gelmez", () => {
    const dinleyici = vi.fn();
    subscribeShowSteps(dinleyici)();

    setShowSteps(true);

    expect(dinleyici).not.toHaveBeenCalled();
  });
});
