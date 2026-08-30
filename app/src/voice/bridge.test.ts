import { describe, expect, it, vi } from "vitest";
import {
  VOICE_EVENT,
  VOICE_RUNTIME_STATE,
  emitVoiceMessage,
  onVoiceMessage,
  onVoiceRuntimeState,
  publishVoiceRuntimeState,
} from "./bridge";

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

describe("konuşma runtime durum köprüsü", () => {
  it("yalnız durum ve isteğe bağlı metin payload'ını taşır", async () => {
    const emit = vi.fn();
    await publishVoiceRuntimeState({ durum: "talking", metin: "Merhaba" }, { emit });
    expect(emit).toHaveBeenCalledWith(VOICE_RUNTIME_STATE, { durum: "talking", metin: "Merhaba" });

    const seen: unknown[] = [];
    let deliver: ((event: { payload: unknown }) => void) | null = null;
    const remove = await onVoiceRuntimeState((payload) => seen.push(payload), {
      listen: async (_event, handler) => {
        deliver = handler;
        return () => undefined;
      },
    });
    deliver?.({ payload: { durum: "listening" } });
    expect(seen).toEqual([{ durum: "listening" }]);
    remove();
  });
});
