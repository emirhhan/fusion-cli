import { describe, expect, it } from "vitest";
import { isVoiceWindow } from "./windowBridge";

describe("konuşma penceresi", () => {
  it("yalnız kendi arama parametresiyle tanınır", () => {
    expect(isVoiceWindow("?pencere=ses")).toBe(true);
    expect(isVoiceWindow("?pencere=ana")).toBe(false);
    expect(isVoiceWindow("")).toBe(false);
    // Benzer ama farklı değer ana pencereyi konuşma penceresi sanmamalı.
    expect(isVoiceWindow("?pencere=sesli")).toBe(false);
  });
});
