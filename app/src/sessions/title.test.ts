import { describe, expect, it } from "vitest";
import { DEFAULT_TITLE, titleFromTask } from "./title";

describe("titleFromTask", () => {
  it("ilk birkaç kelimeyi başlık yapar", () => {
    expect(titleFromTask("bana bir tarayıcı oyunu yaz lütfen")).toBe("bana bir tarayıcı oyunu");
  });

  it("kısa mesajı olduğu gibi bırakır", () => {
    expect(titleFromTask("merhaba")).toBe("merhaba");
  });

  it("kenar noktalamasını atar, cümle içindekini korur", () => {
    expect(titleFromTask("  «oyun», hemen! ")).toBe("oyun hemen");
    expect(titleFromTask("kullanıcı'nın isteği")).toBe("kullanıcı'nın isteği");
  });

  it("boş ve yalnız noktalama içeren girdide varsayılana düşer", () => {
    expect(titleFromTask("   ")).toBe(DEFAULT_TITLE);
    expect(titleFromTask("!!! ???")).toBe(DEFAULT_TITLE);
  });

  it("tek kelime tavanı aşsa bile başlık boş kalmaz", () => {
    const uzun = "a".repeat(80);
    expect(titleFromTask(uzun)).toHaveLength(48);
  });

  it("satır sonlarını tek boşluğa indirger", () => {
    expect(titleFromTask("ilk\n\nikinci  üçüncü")).toBe("ilk ikinci üçüncü");
  });
});
