import { describe, expect, it } from "vitest";
import { olayAdimi } from "./olayMetni";

describe("olayAdimi", () => {
  it("öğretmen görev kararı ve planını kısa adım olarak gösterir", () => {
    expect(olayAdimi({ olay: "TeacherTaskClassified", size: "orta-buyuk", reasons: ["istenen etki: workspace_mutation"] })?.metin)
      .toBe("orta-büyük görev belirlendi");
    expect(olayAdimi({ olay: "TeacherPlanPrepared", steps: 2, structured: true })?.metin)
      .toBe("öğretmenden plan alındı");
  });
  it("hafızadan ilerlemeyi ve ders kaydını kısa adım olarak gösterir", () => {
    const hafiza = olayAdimi({ olay: "TeacherMemoryUsed", steps: 3, similarity: 0.625 });
    expect(hafiza?.metin).toBe("hafızadan ilerleniyor");
    expect(hafiza?.ayrinti).toBe("3 adım · benzerlik 0.63");
    expect(olayAdimi({ olay: "TeacherLessonRecorded", success: true, reused: false })?.metin)
      .toBe("öğretmen planı hafızaya yazıldı");
    const tutmadi = olayAdimi({ olay: "TeacherLessonRecorded", success: false, reused: true });
    expect(tutmadi?.metin).toBe("hafızadaki plan tutmadı");
    expect(tutmadi?.ayrinti).toContain("öğretmene yeniden sorulacak");
  });
  it("yapılamayan dış işi gerekçe ve alternatifiyle gösterir", () => {
    const adim = olayAdimi({
      olay: "TeacherLimitationFound",
      topic: "Story çıkartması",
      reason: "API desteklemiyor",
      alternative: "Telefona bildirim gönder",
    });
    expect(adim?.metin).toBe("Story çıkartması yapılamıyor");
    expect(adim?.ayrinti).toContain("Telefona bildirim gönder");
  });
  it("yedeğe geçişin sebebi insan doğrulamasıysa ayrıntıda saklanmaz", () => {
    const adim = olayAdimi({
      olay: "ModelFallbackActivated",
      requested_model: "chatgpt_web/main/auto",
      fallback_model: "nvidia_nim/x",
      reason: "web oturumu hatası: ChatGPT Web insan doğrulaması (captcha) istiyor.",
    });
    expect(adim?.ayrinti).toContain("insan doğrulaması");
    const siradan = olayAdimi({ olay: "ModelFallbackActivated", requested_model: "a", fallback_model: "b", reason: "429" });
    expect(siradan?.ayrinti).toBe("a → b");
  });

  it("model çağrısında rolü ve modeli ayrıntıya koyar", () => {
    const adim = olayAdimi({ olay: "ModelCallStarted", role: "agent", model: "openrouter/x" });
    expect(adim).toEqual({ metin: "düşünüyor", ayrinti: "agent · openrouter/x" });
  });

  it("arka plan çağrısı akışta hiç görünmez", () => {
    // Hakem ve sentez çağrıları kullanıcıya ilerleme satırı olarak gösterilmez.
    expect(olayAdimi({ olay: "ModelCallStarted", role: "hakem", model: "x", background: true }))
      .toBeNull();
  });

  /* Bkz. bug: model düşünürken/araç çalışırken sohbette hiçbir soluk durum
     yazısı yoktu. `ToolStarted` çekirdeğin ürettiği (TEK KAYNAK) `metin`
     alanını olduğu gibi basar — arayüz kendi çeviri tablosunu tutmaz. */
  it("araç başlarken çekirdeğin ürettiği insan cümlesini basar", () => {
    const adim = olayAdimi({
      olay: "ToolStarted",
      name: "read_file",
      args: { path: "src/app.py" },
      metin: "src/app.py okunuyor",
    });
    expect(adim).toEqual({ metin: "src/app.py okunuyor", kaynak: undefined, arac: "read_file", basladi: true });
  });

  it("çekirdek metin göndermezse (eski sürüm) ada dayalı bir yedek üretir", () => {
    const adim = olayAdimi({ olay: "ToolStarted", name: "read_file", args: {} });
    expect(adim?.metin).toBe("read_file çalıştırılıyor");
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

  it("başarılı araç çağrısını insan-okunur metinle anlatır", () => {
    // Ölçüldü: eşleşmeyen bitiş olayı ham "araç çalıştı: glob" satırı bırakıyordu.
    expect(olayAdimi({ olay: "ToolExecuted", name: "glob", outcome: "ok", args: { pattern: "**/*.ts" } })?.metin)
      .toBe("'**/*.ts' desenine uyan dosyalar bulunuyor");
    expect(olayAdimi({ olay: "ToolExecuted", name: "write_file", outcome: "ok", args: {} })?.metin)
      .toBe("dosya yazılıyor");
    expect(olayAdimi({ olay: "ToolExecuted", name: "bilinmeyen_arac", outcome: "ok", args: {} })?.metin)
      .toBe("bilinmeyen arac çalıştırılıyor");
  });

  it("uzun mutlak yolu satırda son iki parçaya kısaltır", () => {
    const adim = olayAdimi({
      olay: "ToolExecuted", name: "read_file", outcome: "ok",
      args: { path: "/Users/kullanici/Desktop/ornek-proje/lib/x.ts" },
    });
    expect(adim?.metin).toBe("lib/x.ts okunuyor");
    expect(adim?.ayrinti).toBe("lib/x.ts");
  });

  it.each([
    ["failed", "araç başarısız: write_file"],
    ["denied", "araç reddedildi: write_file"],
    ["blocked", "araç engellendi: write_file"],
  ] as const)("%s sonuçlu araç çağrısını çalıştı saymaz", (outcome, metin) => {
    // Kapsam dışı yazma çağrısı "araç çalıştı" görünüyor, dosya ise hiç yazılmıyordu.
    const adim = olayAdimi({ olay: "ToolExecuted", name: "write_file", outcome, args: {} });
    expect(adim?.metin).toBe(metin);
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

  it("plan tamamlandığında kanıtlanmayan davranışı ayrıntıya koyar", () => {
    expect(olayAdimi({
      olay: "ExecutionCompleted",
      total_steps: 3,
      warnings: ["davranış kanıtlanmadı: test yok"],
    })).toEqual({
      metin: "plan tamamlandı: 3 adım",
      ayrinti: "davranış kanıtlanmadı: test yok",
    });
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
