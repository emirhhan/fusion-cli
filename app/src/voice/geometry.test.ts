import { describe, expect, it } from "vitest";
import { mergeVoiceSnapshot, readVoiceGeometry, saveVoiceGeometry } from "./geometry";

describe("Talk pencere hafızası", () => {
  it("bozuk kayıtta profesyonel varsayılana döner", () => {
    localStorage.setItem("fusion.talk.window.v1", "{");
    expect(readVoiceGeometry(localStorage)).toMatchObject({
      normalHeight: 460,
      normalWidth: 380,
      onTop: true,
      wide: true,
    });
  });

  it("normal boyut ve konumu korur; mini sabit boyutu normal hafızaya yazmaz", () => {
    const normal = mergeVoiceSnapshot(readVoiceGeometry(localStorage), {
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
