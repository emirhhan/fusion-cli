import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, test, vi } from "vitest";
import { useAppTheme, type TemaIstemcisi } from "./SessionApplication";
import { THEME_STORAGE_KEY } from "./theme/theme";

afterEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

function sahteIstemci(tema: string): TemaIstemcisi {
  return { request: vi.fn(async () => ({ ok: true, tema })) };
}

describe("useAppTheme", () => {
  /* Bkz. bug: tema sohbet başına davranıyordu — beyaz temalı bir sohbete
     geçince genel tema beyaza, koyu temalı bir sohbete geçince koyuya
     dönüyordu. Kök neden: `ayar.tema` her AKTİF SEKME değişiminde (yeni
     `client` referansı) yeniden okunuyordu; her sekme kendi çekirdek
     sürecinin BELLEK İÇİ (bayat olabilen) tercihini döndürüyordu. Tema
     GLOBAL olmalı: yalnız uygulama başına BİR KEZ okunmalı. */
  test("ikinci bir istemciye (sekme değişimi) geçilince tema TEKRAR okunmaz", async () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    const koyuSekme = sahteIstemci("dark");
    const acikSekme = sahteIstemci("light");

    const { result, rerender } = renderHook(
      ({ client }: { client?: TemaIstemcisi }) => useAppTheme(client),
      { initialProps: { client: koyuSekme as TemaIstemcisi | undefined } },
    );

    await waitFor(() => expect(koyuSekme.request).toHaveBeenCalledWith("ayar.tema", {}));
    expect(result.current.themePreference).toBe("dark");

    // Kullanıcı açık temalı başka bir sohbete geçer.
    rerender({ client: acikSekme });

    // İkinci istemciden YENİDEN İSTEK ATILMAMALI — tema global kalır.
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(acikSekme.request).not.toHaveBeenCalled();
    expect(result.current.themePreference).toBe("dark");
  });

  test("hiç istemci yokken okumaya çalışmaz, önbellekteki tercihle başlar", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "light");
    const { result } = renderHook(() => useAppTheme(undefined));
    expect(result.current.themePreference).toBe("light");
  });
});
