import { describe, expect, it } from "vitest";
import { decodeGoalResult } from "./goalResult";

describe("decodeGoalResult", () => {
  it("karar metnini ve devam görevini okur", () => {
    expect(decodeGoalResult({ hedef: { metin: "◎ Hedef henüz karşılanmadı", eylem: "devam" }, hedef_devam: "sürdür" }))
      .toEqual({ metin: "◎ Hedef henüz karşılanmadı", eylem: "devam", devam: "sürdür" });
  });

  it("devam yoksa ya da alan bozuksa güvenli döner", () => {
    expect(decodeGoalResult({ hedef: { metin: "✓ Hedef karşılandı", eylem: "tamam" } })?.devam).toBeNull();
    expect(decodeGoalResult({ hedef: "bozuk" })).toBeNull();
    expect(decodeGoalResult({ ok: true })).toBeNull();
  });
});
