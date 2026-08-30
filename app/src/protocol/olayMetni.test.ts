import { describe, expect, it } from "vitest";
import { olayAdimi } from "./olayMetni";

describe("olayAdimi", () => {
  it("model çağrısında rolü ve modeli ayrıntıya koyar", () => {
    const adim = olayAdimi({ olay: "ModelCallStarted", role: "agent", model: "openrouter/x" });
    expect(adim).toEqual({ metin: "düşünüyor", ayrinti: "agent · openrouter/x" });
  });

  it("arka plan çağrısı akışta hiç görünmez", () => {
    // Hakem ve sentez çağrıları kullanıcıya ilerleme satırı olarak gösterilmez.
    expect(olayAdimi({ olay: "ModelCallStarted", role: "hakem", model: "x", background: true }))
      .toBeNull();
  });

  it("araç adresini kaynak olarak taşır", () => {
    const adim = olayAdimi({
      olay: "ToolExecuted",
      name: "web_fetch",
      args: { url: "https://ornek.com/a" },
    });
    expect(adim?.kaynak).toBe("https://ornek.com/a");
    expect(adim?.ayrinti).toBe("https://ornek.com/a");
  });

  it("dosya aracında yolu ayrıntı yapar, kaynak üretmez", () => {
    const adim = olayAdimi({ olay: "ToolExecuted", name: "write_file", args: { path: "a/b.py" } });
    expect(adim?.ayrinti).toBe("a/b.py");
    expect(adim?.kaynak).toBeUndefined();
  });

  it("tur sonucu kendi başına duran bir adımdır", () => {
    expect(olayAdimi({ olay: "TurnOutcome", status: "completed" })?.sonuc).toBe(true);
  });

  it("tanınmayan olay hiç gösterilmez", () => {
    expect(olayAdimi({ olay: "BilinmeyenSey" })).toBeNull();
  });
});
