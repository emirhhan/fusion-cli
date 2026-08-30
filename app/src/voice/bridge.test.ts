import { describe, expect, it, vi } from "vitest";
import { VOICE_EVENT, emitVoiceMessage, onVoiceMessage } from "./bridge";

describe("konuşma köprüsü", () => {
  it("konuşulanı ana pencereye taşır", async () => {
    const gorulen: unknown[] = [];
    const cikar = onVoiceMessage((yuk) => gorulen.push(yuk), {
      listen: async (_ad, isleyici) => {
        // Tauri dinleyicisinin yerine geçen sahte taşıma.
        (globalThis as { __tetikle?: unknown }).__tetikle = isleyici;
        return () => undefined;
      },
    });

    const tetikle = (globalThis as { __tetikle?: (e: { payload: unknown }) => void }).__tetikle!;
    tetikle({ payload: { metin: "merhaba", kaynak: "kullanici" } });

    expect(gorulen).toEqual([{ metin: "merhaba", kaynak: "kullanici" }]);
    (await cikar)();
  });

  it("boş metni hiç yollamaz", async () => {
    const emit = vi.fn();
    await emitVoiceMessage({ metin: "   ", kaynak: "kullanici" }, { emit });
    expect(emit).not.toHaveBeenCalled();

    await emitVoiceMessage({ metin: "gerçek", kaynak: "kullanici" }, { emit });
    expect(emit).toHaveBeenCalledWith(VOICE_EVENT, { metin: "gerçek", kaynak: "kullanici" });
  });
});
