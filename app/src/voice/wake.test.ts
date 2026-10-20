import { describe, expect, it } from "vitest";
import { routeWakeSpeech, speechFailureText } from "./wake";
describe("uyandırma", () => {
  it("arka plan konuşmasını göndermez", () => expect(routeWakeSpeech("dosyayı sil", false)).toEqual({ awake: false, acknowledge: false, message: null }));
  it("Fusion tek başına yalnız uyandırır", () => expect(routeWakeSpeech("Fusion!", false)).toEqual({ awake: true, acknowledge: true, message: null }));
  it("tek cümledeki isteği ayırır", () => expect(routeWakeSpeech("Fusion, projeyi aç", false)).toEqual({ awake: true, acknowledge: true, message: "projeyi aç" }));
  it("başka sözcük içindeki Fusion uyandırmaz", () => expect(routeWakeSpeech("infusion hazır", false).acknowledge).toBe(false));
  it("tıklamadan sonra cümleyi kabul eder", () => expect(routeWakeSpeech("projeyi aç", true).message).toBe("projeyi aç"));
  it("kendi hm sesini görev saymaz", () => expect(routeWakeSpeech("Hm", true).message).toBeNull());
  it("Dikte hatasını mikrofon izniyle karıştırmaz", () => expect(speechFailureText("Siri and Dictation are disabled")).toContain("Klavye → Dikte"));
  it("bilinmeyen hatayı saklamaz", () => expect(speechFailureText("aygıt bulunamadı")).toBe("aygıt bulunamadı"));
});

it("Türkçe tanıyıcının Füzyon yazımını uyandırır", () => expect(routeWakeSpeech("Füzyon, projeyi aç", false)).toEqual({ awake: true, acknowledge: true, message: "projeyi aç" }));
