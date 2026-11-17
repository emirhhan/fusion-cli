import { describe, expect, it, vi } from "vitest";
import { diktePasifMi, routeWakeSpeech, scheduleThinkingCues, speechFailureText } from "./wake";

it("bekleme seslerini istenen saniyelerde çalar ve yanıt başlayınca durur", () => {
  vi.useFakeTimers();
  try {
    const play = vi.fn();
    const cancel = scheduleThinkingCues(play);
    expect(play.mock.calls).toEqual([[undefined]]);
    vi.advanceTimersByTime(5_000);
    expect(play.mock.calls).toEqual([[undefined], [undefined]]);
    vi.advanceTimersByTime(10_000);
    expect(play).toHaveBeenLastCalledWith("Düşünüyorum.");
    vi.advanceTimersByTime(9_000);
    expect(play).toHaveBeenLastCalledWith("Hâlâ düşünüyorum.");
    vi.advanceTimersByTime(6_000);
    expect(play).toHaveBeenLastCalledWith("Bu soru biraz kafamı karıştırdı, düşünüyorum.");
    cancel();
    vi.advanceTimersByTime(60_000);
    expect(play).toHaveBeenCalledTimes(5);
  } finally {
    vi.useRealTimers();
  }
});
describe("uyandırma", () => {
  it("arka plan konuşmasını göndermez", () => expect(routeWakeSpeech("dosyayı sil", false)).toEqual({ awake: false, acknowledge: false, message: null }));
  it("Fusion tek başına yalnız uyandırır", () => expect(routeWakeSpeech("Fusion!", false)).toEqual({ awake: true, acknowledge: true, message: null }));
  it("tek cümledeki isteği ayırır", () => expect(routeWakeSpeech("Fusion, projeyi aç", false)).toEqual({ awake: true, acknowledge: true, message: "projeyi aç" }));
  it("başka sözcük içindeki Fusion uyandırmaz", () => expect(routeWakeSpeech("infusion hazır", false).acknowledge).toBe(false));
  it("tıklamadan sonra cümleyi kabul eder", () => expect(routeWakeSpeech("projeyi aç", true).message).toBe("projeyi aç"));
  it("kendi hm sesini görev saymaz", () => expect(routeWakeSpeech("Hm", true).message).toBeNull());
  it("Dikte hatasını mikrofon izniyle karıştırmaz", () => expect(speechFailureText("Siri and Dictation are disabled")).toContain("Klavye → Dikte"));
  // Ölçüldü (30 Ekim): arayüz yalnız sistemin İngilizce hata metnini ayrıştırıyordu; metin
  // değişirse Dikte uyarısı sessizce kaybolurdu. Swift yardımcısı artık `kod: dikte_kapali` yazar.
  it("yapısal kod metin değişse de Dikte kapalı sayılır", () => {
    expect(diktePasifMi({ kod: "dikte_kapali", metin: "başka bir metin" })).toBe(true);
    expect(speechFailureText("başka bir metin", "dikte_kapali")).toContain("Klavye → Dikte");
  });
  it("kodsuz eski yardımcının metni hâlâ tanınır", () => {
    expect(diktePasifMi({ metin: "Siri and Dictation are disabled" })).toBe(true);
    expect(diktePasifMi({ kod: "baska", metin: "aygıt bulunamadı" })).toBe(false);
  });
  it("bilinmeyen hatayı saklamaz", () => expect(speechFailureText("aygıt bulunamadı")).toBe("aygıt bulunamadı"));
});

it("Türkçe tanıyıcının Füzyon yazımını uyandırır", () => expect(routeWakeSpeech("Füzyon, projeyi aç", false)).toEqual({ awake: true, acknowledge: true, message: "projeyi aç" }));
