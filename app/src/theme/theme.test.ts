import { afterEach, describe, expect, it } from "vitest";
import {
  applyTheme,
  readThemePreference,
  resolveTheme,
  THEME_STORAGE_KEY,
} from "./theme";

afterEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
  document.documentElement.style.colorScheme = "";
});

describe("tema sözleşmesi", () => {
  it("sistem tercihini işletim sistemi görünümüne çözer", () => {
    expect(resolveTheme("system", true)).toBe("dark");
    expect(resolveTheme("system", false)).toBe("light");
  });

  it("açık ve koyu tercihleri sistemden bağımsız korur", () => {
    expect(resolveTheme("light", true)).toBe("light");
    expect(resolveTheme("dark", false)).toBe("dark");
  });

  it("geçersiz saklı değeri sistem tercihi kabul eder", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "gecersiz");
    expect(readThemePreference()).toBe("system");
  });

  it("çözülen temayı belge köküne ve color-scheme alanına uygular", () => {
    expect(applyTheme("dark", document.documentElement, false)).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(document.documentElement.style.colorScheme).toBe("dark");
  });
});
