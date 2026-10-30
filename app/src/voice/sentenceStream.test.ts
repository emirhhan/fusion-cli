import { describe, expect, it } from "vitest";
import { splitIntoSentences, splitIntoSpeechChunks } from "./sentenceStream";

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

it("kısa bir konuşma yanıtını tek ses parçasında tutar", () => {
 expect(splitIntoSpeechChunks("Merhaba. Nasıl yardımcı olayım?")).toEqual(["Merhaba. Nasıl yardımcı olayım?"]);
});

describe("splitIntoSentences — eski WebView uyumu (U2-24)", () => {
  it("geriye bakışlı düzenli ifade kullanmaz (WKWebView 16.4 öncesi modülü yükleyemez)", async () => {
    const source = (await import("./sentenceStream.ts?raw")).default as string;
    const code = source
      .split("\n").filter((line) => !/^\s*(\/\/|\*|\/\*)/.test(line)).join("\n");
    expect(code).not.toContain("(?<=");
    expect(code).not.toContain("(?<!");
  });

  it("noktalama sonrası çoklu boşluk ve satır sonunda aynı sonucu verir", () => {
    expect(splitIntoSentences("Birinci cümle.  İkinci cümle!\nÜçüncü cümle?")).toEqual([
      "Birinci cümle.", "İkinci cümle!", "Üçüncü cümle?",
    ]);
    expect(splitIntoSentences("Sürüm 3.5 hazır mı? Evet.")).toEqual(["Sürüm 3.5 hazır mı?", "Evet."]);
    expect(splitIntoSentences("Bitmeyen cümle devam ediyor")).toEqual(["Bitmeyen cümle devam ediyor"]);
  });
});
