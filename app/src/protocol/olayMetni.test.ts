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

  it.each([
    ["completed", "görev tamamlandı"],
    ["partial", "görev kısmi kaldı"],
    ["failed", "görev başarısız"],
  ] as const)("%s tur sonucunu typed durumuyla taşır", (status, metin) => {
    expect(olayAdimi({ olay: "TurnOutcome", status })).toEqual({
      metin,
      sonuc: status,
    });
  });

  it("tanınmayan olay hiç gösterilmez", () => {
    expect(olayAdimi({ olay: "BilinmeyenSey" })).toBeNull();
  });

  it("workflow adımını sıra ve hedefle gösterir", () => {
    expect(olayAdimi({
      olay: "ExecutionStepStarted",
      index: 2,
      total_steps: 4,
      goal: "testleri çalıştır",
    })).toEqual({ metin: "adım 2/4 başladı", ayrinti: "testleri çalıştır" });
  });

  it("doğrulama kanıtını ham JSON yerine okunabilir metne çevirir", () => {
    expect(olayAdimi({
      olay: "ExecutionStepVerified",
      step_id: "verify",
      ok: true,
      evidence: ["pytest geçti", "ruff geçti"],
    })).toEqual({ metin: "verify doğrulandı", ayrinti: "pytest geçti · ruff geçti" });
  });

  it("hızlı turun yükseltilmesini gerekçesiyle gösterir", () => {
    // Yükseltme sessiz olmamalı: kullanıcı işin neden planlı yola geçtiğini görür.
    expect(olayAdimi({
      olay: "ExecutionPromoted",
      reasons: ["teşhis ve onarım gerektiren hata", "birden fazla araç ailesi"],
    })).toEqual({
      metin: "görev planlı yürütmeye yükseltildi",
      ayrinti: "teşhis ve onarım gerektiren hata · birden fazla araç ailesi",
    });
  });
});
