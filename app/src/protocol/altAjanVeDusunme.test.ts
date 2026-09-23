/** Alt ajan adımları ve düşünme metni — masaüstü karşılıkları.
 *
 * CLI'de ikisi de vardı (`┌ alt-ajan` başlığı, `--show-thinking`); masaüstünde
 * olay akışında taşınıyor ama hiç okunmuyordu.
 */
import { describe, expect, it } from "vitest";

import { olayAdimi } from "./olayMetni";

describe("alt ajan adımları", () => {
  it("başlangıcı görevle birlikte işaretler", () => {
    const adim = olayAdimi({ olay: "SubAgentStarted", task: "testleri düzelt" });
    expect(adim).toEqual({
      metin: "alt ajan başladı",
      ayrinti: "testleri düzelt",
      altAjan: true,
    });
  });

  it("bitişi araç sayısıyla işaretler", () => {
    const adim = olayAdimi({ olay: "SubAgentFinished", tool_calls: 7 });
    expect(adim?.altAjan).toBe(true);
    expect(adim?.ayrinti).toBe("7 araç çağrısı");
  });

  it("araç sayısı yoksa ayrıntı uydurulmaz", () => {
    expect(olayAdimi({ olay: "SubAgentFinished" })?.ayrinti).toBeUndefined();
  });

  it("görev boşsa ayrıntı uydurulmaz", () => {
    expect(olayAdimi({ olay: "SubAgentStarted", task: "" })?.ayrinti).toBeUndefined();
  });
});

describe("düşünme metni", () => {
  it("reasoning varsa adım açar", () => {
    const adim = olayAdimi({
      olay: "ModelCallFinished",
      result: { reasoning: "önce dosyayı okumalıyım" },
    });
    expect(adim).toEqual({ metin: "düşündü", dusunme: "önce dosyayı okumalıyım" });
  });

  it("reasoning YOKSA adım açılmaz", () => {
    // Her model çağrısı için boş satır açmak akışı ikiye katlardı.
    expect(olayAdimi({ olay: "ModelCallFinished", result: {} })).toBeNull();
  });

  it("boşluktan ibaret reasoning adım açmaz", () => {
    expect(
      olayAdimi({ olay: "ModelCallFinished", result: { reasoning: "   \n " } }),
    ).toBeNull();
  });

  it("arka plan çağrısı akışa girmez", () => {
    // Hakem/sentez çağrıları muhasebe içindir, ekranı kalabalıklaştırır.
    expect(
      olayAdimi({
        olay: "ModelCallFinished",
        background: true,
        result: { reasoning: "hakem düşüncesi" },
      }),
    ).toBeNull();
  });

  it("result yoksa çökmez", () => {
    expect(olayAdimi({ olay: "ModelCallFinished" })).toBeNull();
  });
});
