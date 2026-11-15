import { describe, expect, it } from "vitest";
import { dictationSendsOnFinal, isDictationCommand } from "./dictationCommand";

describe("isDictationCommand", () => {
  it("/voice ve /dikte mikrofonu açar; durum çekirdeğe gider", () => {
    expect(isDictationCommand("/voice")).toBe(true);
    expect(isDictationCommand(" /dikte gonder ")).toBe(true);
    expect(isDictationCommand("/voice durum")).toBe(false);
    expect(isDictationCommand("/voiceover")).toBe(false);
  });
});

describe("dictationSendsOnFinal", () => {
  it("yalnız /voice gonder dikte bitince gönderir", () => {
    expect(dictationSendsOnFinal("/voice gonder")).toBe(true);
    expect(dictationSendsOnFinal("/dikte Gönder")).toBe(true);
    expect(dictationSendsOnFinal("/voice")).toBe(false);
  });
});
