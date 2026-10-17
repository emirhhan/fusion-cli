import { describe, expect, it, vi } from "vitest";
import {
  VOICE_EVENT,
  VOICE_RUNTIME_STATE,
  createVoiceMessageDeduper,
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
    expect(emit).toHaveBeenCalledWith(
      VOICE_EVENT,
      expect.objectContaining({ metin: "gerçek", kaynak: "kullanici", id: expect.any(String) }),
    );
  });

  it("her söze tek seferlik kimlik verir; verilen kimliği korur", async () => {
    const emit = vi.fn();
    await emitVoiceMessage({ metin: "bir", kaynak: "kullanici" }, { emit });
    await emitVoiceMessage({ metin: "bir", kaynak: "kullanici" }, { emit });
    await emitVoiceMessage({ metin: "iki", kaynak: "kullanici", id: "sabit" }, { emit });
    const ids = emit.mock.calls.map(([, message]) => message.id);
    expect(ids[0]).not.toBe(ids[1]);
    expect(ids[2]).toBe("sabit");
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

describe("createVoiceMessageDeduper", () => {
  it("aynı kimliği ikinci kez geçirmez, kimliksizi her zaman geçirir", () => {
    const first = createVoiceMessageDeduper();
    expect(first("a")).toBe(true);
    expect(first("a")).toBe(false);
    expect(first("b")).toBe(true);
    expect(first(undefined)).toBe(true);
    expect(first(undefined)).toBe(true);
  });

  it("sınırı aşınca en eski kimliği unutur (bellek şişmez)", () => {
    const first = createVoiceMessageDeduper(2);
    first("a"); first("b"); first("c");
    expect(first("a")).toBe(true);
    expect(first("c")).toBe(false);
  });
});
