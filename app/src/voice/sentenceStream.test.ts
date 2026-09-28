import { describe, expect, it } from "vitest";
import { splitIntoSentences } from "./sentenceStream";

describe("splitIntoSentences", () => {
  it("boş metni boş dizi olarak döner", () => {
    expect(splitIntoSentences("")).toEqual([]);
    expect(splitIntoSentences("   ")).toEqual([]);
  });

  it("tek cümleyi olduğu gibi döner", () => {
    expect(splitIntoSentences("Merhaba dünya.")).toEqual(["Merhaba dünya."]);
  });

  it("birden çok cümleyi noktalamadan böler", () => {
    expect(splitIntoSentences("Önce şunu yap. Sonra bunu dene! Tamam mı?")).toEqual([
      "Önce şunu yap.",
      "Sonra bunu dene!",
      "Tamam mı?",
    ]);
  });

  it("kısa kısaltmayı ayrı cümle saymaz, öncekine ekler", () => {
    expect(splitIntoSentences("Dr. Ahmet geldi. Nasılsın?")).toEqual([
      "Dr. Ahmet geldi.",
      "Nasılsın?",
    ]);
  });

  it("noktalamasız son parçayı da cümle sayar", () => {
    expect(splitIntoSentences("Birinci cümle. yarım kalan ikinci parça")).toEqual([
      "Birinci cümle.",
      "yarım kalan ikinci parça",
    ]);
  });

  it("üç nokta ile biten cümleyi doğru böler", () => {
    expect(splitIntoSentences("Düşünüyorum… Sanırım oldu.")).toEqual([
      "Düşünüyorum…",
      "Sanırım oldu.",
    ]);
  });

  it("fazla boşlukları ve satır sonlarını tolere eder", () => {
    expect(splitIntoSentences("Birinci.\n\nİkinci.   Üçüncü.")).toEqual([
      "Birinci.",
      "İkinci.",
      "Üçüncü.",
    ]);
  });
});
