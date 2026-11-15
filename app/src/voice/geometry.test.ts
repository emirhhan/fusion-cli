import { describe, expect, it } from "vitest";
import { mergeVoiceSnapshot, readVoiceGeometry, saveVoiceGeometry, VOICE_GEOMETRY_KEY } from "./geometry";

describe("Talk pencere hafızası", () => {
  it("bozuk kayıtta profesyonel varsayılana döner", () => {
    localStorage.setItem(VOICE_GEOMETRY_KEY, "{");
    expect(readVoiceGeometry(localStorage)).toMatchObject({
      normalHeight: 460,
      normalWidth: 380,
      onTop: true,
      wide: false,
    });
  });

  it("normal boyut ve konumu korur; mini sabit boyutu normal hafızaya yazmaz", () => {
    const normal = mergeVoiceSnapshot({ ...readVoiceGeometry(localStorage), wide: true }, {
      height: 620,
      width: 470,
      x: 100,
      y: 80,
    });
    saveVoiceGeometry(localStorage, normal);
    const mini = mergeVoiceSnapshot({ ...readVoiceGeometry(localStorage), wide: false }, {
      height: 112,
      width: 360,
      x: 140,
      y: 90,
    });
    expect(mini).toMatchObject({ normalHeight: 620, normalWidth: 470, x: 140, y: 90 });
  });
});

describe("Talk pencere hafızası — dalga 4", () => {
  it("'Hep üstte kal' kapatılınca yeniden açıldığında da kapalı kalır (U2-21)", () => {
    saveVoiceGeometry(localStorage, { ...readVoiceGeometry(localStorage), onTop: false });
    expect(readVoiceGeometry(localStorage).onTop).toBe(false);
    // `wide` hâlâ sabit: eski sürümden kalan değer kullanıcıyı geniş yerleşime hapsetmez.
    localStorage.setItem(VOICE_GEOMETRY_KEY, JSON.stringify({ onTop: true, wide: true }));
    expect(readVoiceGeometry(localStorage)).toMatchObject({ onTop: true, wide: false });
  });

  it("kota dolu/özel pencere `setItem` fırlatsa da kayıt yakalanır (U2-22)", () => {
    const storage = { setItem: () => { throw new DOMException("dolu", "QuotaExceededError"); } } as unknown as Storage;
    expect(() => saveVoiceGeometry(storage, readVoiceGeometry(localStorage))).not.toThrow();
  });
});
