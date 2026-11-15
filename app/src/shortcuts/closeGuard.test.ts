import { describe, expect, it } from "vitest";
import { CLOSE_CONFIRM_WINDOW_MS, closeDecision } from "./closeGuard";

describe("⌘W çalışan turu korur (#444)", () => {
  it("tur yoksa hemen kapatır", () => {
    expect(closeDecision(false, 1000, null)).toBe("close");
  });

  it("tur çalışıyorsa ilk basışta uyarır, süre içinde ikinci basışta kapatır", () => {
    expect(closeDecision(true, 1000, null)).toBe("arm");
    expect(closeDecision(true, 1000 + CLOSE_CONFIRM_WINDOW_MS - 1, 1000)).toBe("close");
    expect(closeDecision(true, 1000 + CLOSE_CONFIRM_WINDOW_MS + 1, 1000)).toBe("arm");
  });
});
