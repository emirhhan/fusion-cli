import { afterEach, expect, it, vi } from "vitest";
import { readThemePreference, saveThemePreference } from "./theme";

afterEach(() => vi.restoreAllMocks());

it("localStorage erişimi SecurityError atsa da tema okuma/yazma çökmez (U6-10)", () => {
  const getter = vi.spyOn(window, "localStorage", "get").mockImplementation(() => { throw new DOMException("denied", "SecurityError"); });
  expect(readThemePreference()).toBe("dark");
  expect(() => saveThemePreference("light")).not.toThrow();
  expect(getter).toHaveBeenCalled();
});
