import { describe, expect, it } from "vitest";
import { isFullPage, SOHBET_KABUGU_SAYFALARI, type Page } from "./pageLayout";

describe("tam sayfa kuralı", () => {
  it("yalnız sohbet ve görsel oluşturma kenar çubuğuyla açılır", () => {
    expect(SOHBET_KABUGU_SAYFALARI).toEqual(["chat", "image-create"]);
    for (const page of SOHBET_KABUGU_SAYFALARI) expect(isFullPage(page, null), page).toBe(false);
  });

  it("sohbetle ilgisi olmayan her yönetim sayfası tam sayfadır", () => {
    const yonetim: Page[] = ["settings", "account", "help", "control", "skills", "connectors"];
    for (const page of yonetim) expect(isFullPage(page, null), page).toBe(true);
  });

  it("raydan açılan bölümler (Zamanlananlar, Kitaplık, Kits) sohbet sayfasında da tam sayfadır", () => {
    for (const section of ["scheduled", "library", "kits"] as const) expect(isFullPage("chat", section), section).toBe(true);
  });
});
