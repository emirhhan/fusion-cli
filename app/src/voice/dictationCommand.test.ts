import { describe, expect, it } from "vitest";
import { isDictationCommand } from "./dictationCommand";

describe("isDictationCommand", () => {
  it("/voice ve /dikte mikrofonu açar; durum çekirdeğe gider", () => {
    expect(isDictationCommand("/voice")).toBe(true);
    expect(isDictationCommand(" /dikte gonder ")).toBe(true);
    expect(isDictationCommand("/voice durum")).toBe(false);
    expect(isDictationCommand("/voiceover")).toBe(false);
  });
});
