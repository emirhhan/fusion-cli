import type { Mesaj } from "../src/screens/Conversation";

/** Okuma ritmini, Türkçe karakterleri ve taşan içeriği birlikte gösterir. */
export const TYPOGRAPHY_TEXT = [
  "# Birlikte düşünmek",
  "",
  "İstanbul’un ışığı değişirken sakin bir okuma alanı kuruyoruz. İ ı Ğ ğ Ş ş Ç ç Ö ö Ü ü. **Açık bir düşünce**, *özenli bir vurgu* ve anlaşılır cümlelerle başlar.\nBu yumuşak satır sonu aynı paragrafın içinde akmaya devam eder.",
  "",
  "İkinci paragraf, ilk düşünceye nefes alacak kadar boşluk bırakır. Kullanıcının mesajı ve düğmeler kendi yazı karakterini korurken yanıt, uzun okumalar için ölçülü bir satır genişliği kullanır.",
  "",
  "## Ana fikir",
  "- Kısa ve açık bir başlangıç",
  "- İkinci düşünce\n  - İç içe bir ayrıntı\n  - Başka bir ayrıntı",
  "",
  "### Uygulama adımları",
  "1. İlk adımı dikkatle oku.",
  "",
  "   Açıklaması aynı liste maddesinin içinde kalır.",
  "",
  "2. İkinci adımı tamamla.",
  "",
  "#### Küçük ayrıntılar",
  "Bir satır içi örnek: `const şehir = 'İstanbul';`. Ardından gelen cümle normal anlatım rolünü sürdürür.",
  "",
  "##### Son kontrol",
  "Başlıklar küçülürken okuma sırası anlaşılır kalır.",
  "",
  "###### Kaynak notu",
  "> İyi bir açıklama, okuyucunun düşüncesini takip edebileceği kadar sakindir.",
  "",
  "| Şehir | Birinci gözlem | İkinci gözlem | Üçüncü gözlem | Dördüncü gözlem | Beşinci gözlem | Altıncı gözlem |",
  "| --- | --- | --- | --- | --- | --- | --- |",
  "| İstanbul | Sabah ışığı | Uzun ve ayrıntılı bir açıklama | Sakin sokaklar | Gölge ve renk | Akşamüstü | Tamamlandı |",
  "",
  "```typescript:ornek.ts",
  "const şehir = 'İstanbul';",
  "const uzunSatır = '" + "Türkçe karakterleri ve yatay kaydırmayı birlikte koruyoruz. ".repeat(8) + "';",
  ...Array.from({ length: 18 }, (_, index) => `console.log(şehir, ${index + 1});`),
  "```",
  "",
  "![Uzak görsel](https://example.com/tipografi.png)",
].join("\n");

export function typographyMessages(text = TYPOGRAPHY_TEXT, streaming = false): Mesaj[] {
  return [
    { rol: "kullanici", metin: "Yanıtı başlıklar, listeler ve örneklerle açıklar mısın?" },
    { rol: "asistan", metin: "Önce ana fikri okuyalım; sonra ayrıntılara birlikte bakalım.", ara: true },
    { rol: "asistan", metin: text, akan: streaming },
  ];
}
