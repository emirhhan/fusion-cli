import { describe, expect, it, vi } from "vitest";
import { isSpokenWorkRequest, localVoiceReply } from "./localVoice";
import { routeWakeSpeech } from "./wake";
describe("yerel ses niyeti", () => {
 it.each(["Merhaba Füzyon!", "Fusion merhaba", "Selam", "Nasılsın füzyon?", "Beni duyuyor musun?"])("hazır yanıt %s", text => expect(localVoiceReply(text)).toBeTruthy());
 it.each(["Merhaba füzyon projeyi aç", "teşekkürler ama devam et", "evet", "hayır", "merhaba dosyasını sil"])("görevi yutmaz %s", text => expect(localVoiceReply(text)).toBeNull());
 it("merhaba füzyon beklemeden uyanır ve mesaj kaybolmaz", () => expect(routeWakeSpeech("Merhaba Füzyon", false).message).toBe("Merhaba Füzyon"));
 it("hitaplı gerçek isteği model için korur", () => expect(routeWakeSpeech("Merhaba Füzyon projeyi aç", false).message).toBe("projeyi aç"));
 it("Merhaba Fizyo tanıma çıktısını doğrudan selamlar", () => {
   expect(localVoiceReply("Merhaba Fizyo")).toMatch(/^Merhaba/);
   expect(localVoiceReply("Merhaba Fizyo takvime bak")).toBeNull();
 });
});

it("tarih ve yıl sorularını cihazın güncel tarihine göre yanıtlar", () => {
  vi.useFakeTimers();
  try {
    vi.setSystemTime(new Date(2025, 11, 31, 23, 59));
    expect(localVoiceReply("Şu an hangi yıldayız?")).toBe("2025 yılındayız.");
    vi.setSystemTime(new Date(2026, 0, 1, 0, 1));
    expect(localVoiceReply("Fusion, şu an kaç yılındayız?")).toBe("2026 yılındayız.");
    expect(localVoiceReply("Bugün ayın kaçı?")).toBe("Bugün 1 Ocak 2026 Perşembe.");
  } finally {
    vi.useRealTimers();
  }
});

it.each([
  ["Peki bu nasıl oluyor?", false],
  ["Dosya ve klasör arasındaki fark ne?", false],
  ["Bu dosyayı nasıl silerim?", false],
  ["Dosyaları listele desem ne olur?", false],
  ["Sadece “projeyi sil” yaz.", false],
  ["Türkiye’de kaç tane bölge var?", false],
  ["Önceki söylediğin ne anlama geliyor?", false],
  ["Çalışma klasöründeki dosyaları listele", true],
  ["Dosyalarımı listeler misin lütfen?", true],
  ["Takvimime bak", true],
  ["Bu proje için bir tablo hazırla", true],
  ["Bu sunumu PDF olarak dışa aktar", true],
  ["Bu dosyanın kısa özetini çıkar", true],
  ["Bunu yap", true],
  ["Bir görsel üret", true],
  ["Webde 2026 değişikliklerini araştır", false],
  ["İnternette OpenAI’nin yeni raporunu bul", false],
  ["Rapora bir özet ekle", true],
  ["Dosyayı bana gösterir misiniz?", true],
  ["Projenin testlerini çalıştır", true],
] as const)("%s için araç kullanma kararı %s", (text, usesTools) => {
  expect(isSpokenWorkRequest(text)).toBe(usesTools);
});

it("öğretmen çalışırken kısa Türkçe sohbete cevap verir ve görevleri korur", () => {
  expect(localVoiceReply("İşler nasıl gidiyor?", true)).toContain("bekliyorum");
  expect(localVoiceReply("Bugün bayağı yoğunum", true)).toBeTruthy();
  expect(localVoiceReply("Bugün bayağı yoğunum, takvimime bak", true)).toBeNull();
});

it("çekirdeğin araç anlatımını okumadan cevabı seslendirir", async () => {
  const { spokenTeacherAnswer } = await import("./localVoice");
  expect(spokenTeacherAnswer("Bu bir araç gerektiren görev değil — basit bir sohbet sorusu. Elimdeki araçlar (Agent, DiscoverMcpTools, ListAgents) bunun için değil. Benim yaşım yok.")).toBe("Benim yaşım yok.");
  expect(spokenTeacherAnswer("**Sonuç**\nOtuz yedi çarpı yirmi beş 925 eder.")).toBe("Sonuç Otuz yedi çarpı yirmi beş 925 eder.");
  expect(spokenTeacherAnswer("Elimdeki araçlar: Agent, ListAgents ve TaskStop.")).toBe("Fusion’dan sesli aktarabileceğim bir cevap gelmedi.");
});

it.each(["Nasılsın?", "Fusion nasılsın bugün?", "Selam, nasılsın?", "Bu arada, ya sen nasılsın?", "Nasıl sın?", "Nasılsın filizcan", "Merhaba Fizyo nasılsın"])("%s kısa sohbete yönlenir", text => {
  expect(localVoiceReply(text)).toContain("İyiyim");
  expect(localVoiceReply(text + " Takvime bak")).toBeNull();
});

it("araç protokolünü, içindeki kodu ve biçim işaretlerini okumaz", async () => {
  const { spokenTeacherAnswer, voicePronunciation } = await import("./localVoice");
  expect(spokenTeacherAnswer('Önce bakayım. <fusiontoolcall>```json {"name":"web_search"}```</fusiontoolcall>')).toBe("Önce bakayım.");
  expect(spokenTeacherAnswer("fusiontoolcall gizli parametre fusiontoolcallend")).not.toMatch(/kod sohbette|gizli|fusiontoolcall/iu);
  expect(spokenTeacherAnswer("Bitti. FUSION_TOOL_CALL private command FUSION_TOOL_CALL_END")).toBe("Bitti.");
  expect(spokenTeacherAnswer("Bitti. FUSION_TOOL_CALL unfinished payload")).toBe("Bitti.");
  expect(voicePronunciation("• Python, MotoGate | 3,14.")).toBe("Paytın, Moto Geyt 3,14.");
});


it("markanın çekimli biçimlerini de Füzyon olarak seslendirir", async () => {
  const { voicePronunciation } = await import("./localVoice");
  expect(voicePronunciation("Fusion’a ve Fusion Kits’e sor.")).toBe("Füzyona ve Füzyon Kitse sor.");
});

it("konuşma motoruna kesme ve biçim işaretleri yerine doğal Türkçe gönderir", async () => {
  const { voicePronunciation } = await import("./localVoice");
  expect(voicePronunciation("API’yi **VS Code** ile çağır. “Türkiye’nin API’si” (örn. JSON)."))
    .toBe("Ey Pi Ayı Vi Es Kod ile çağır. Türkiyenin Ey Pi Ayı, örneğin Ceyson.");
  expect(voicePronunciation("• HTTP, GPU ve KVKK — sürüm 3.14. %25 + 5 ₺"))
    .toBe("Eyç Ti Ti Pi, Ci Pi Yu ve Ke Ve Ke Ke, sürüm 3,14. yüzde 25 artı 5 lira");
  expect(voicePronunciation("Saat 09:30’da. 2.000,50 ₺ ve 5–10 km. …"))
    .toBe("Saat 9 30 da. 2000,50 lira ve 5 ila 10 kilometre.");
});

it("çıkarma, eksi işaretleri, eşitsizlikler ve sürüm numaralarını korur", async () => {
  const { voicePronunciation } = await import("./localVoice");
  expect(voicePronunciation("8-3=5. 2 ≤ 3. 5 × −2. 1.2.3 sürümü."))
    .toBe("8 eksi 3 eşittir 5. 2 küçük veya eşittir 3. 5 çarpı eksi 2. 1, 2, 3 sürümü.");
  expect(voicePronunciation("(-5) ile (−2). 5 sn. sonra %25 veya 25%. APİ’yi kullan."))
    .toBe("eksi 5 ile, eksi 2. 5 saniye sonra yüzde 25 veya yüzde 25. Ey Pi Ayı kullan.");
});

it("teknik adların eklerini ve sıcaklık birimlerini kaybetmez", async () => {
  const { voicePronunciation } = await import("./localVoice");
  expect(voicePronunciation("OpenAI’ye 15°C ve 25°F örneğini sor. API'nin yanıtını oku."))
    .toBe("Opın Ey Aya 15 santigrat derece ve 25 Fahrenhayt derece örneğini sor. Ey Pi Ayın yanıtını oku.");
});

it("yeni İngilizce teknoloji terimlerini ve Türkçe eklerini ses metninde uyarlar", async () => {
  const { voicePronunciation } = await import("./localVoice");
  expect(voicePronunciation("Agentic workflow, streaming ve orchestrating."))
    .toBe("Acentik vörkflo, striming ve orkistreyting.");
  expect(voicePronunciation("Can test için acentik workflow’un sonucunu bekledi."))
    .toBe("Can test için acentik vörkflonun sonucunu bekledi.");
  expect(voicePronunciation("Bu bir Türkçe test. Can, markete git. Wagner ve Wang."))
    .toBe("Bu bir Türkçe test. Can, markete git. Wagner ve Wang.");
  expect(voicePronunciation("İngilizcede the ana artikeldir."))
    .toBe("İngilizcede dı ana artikeldir.");
  expect(voicePronunciation("C++ with the compiler")).toMatch(/^Si Plus Plus /u);
  expect(voicePronunciation("Wi-Fi with the router")).toMatch(/^Vay Fay /u);
});
