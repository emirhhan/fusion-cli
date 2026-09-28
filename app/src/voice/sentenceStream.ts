/**
 * Model cevabını TTS için cümlelere böler.
 *
 * Amaç: `voice.speak`'in tüm cevabı TEK seferde sentezlemesi yerine (bkz.
 * `appserver/voice.py::speak`), ilk cümle hazır olur olmaz seslendirmeye
 * başlamak — kullanıcı cevabın TAMAMININ sentezlenmesini beklemez.
 *
 * Türkçe'ye özgü kısaltma tuzağı: "Dr. Ahmet geldi." cümle sonu noktalamasıyla
 * (. ! ? …) bölündüğünde "Dr." tek başına bir "cümle" sayılırsa TTS onu ayrı
 * bir tur olarak okur ve tuhaf bir duraklama yaratır. Çok kısa parçalar bu
 * yüzden bir önceki cümleyle birleştirilir.
 */

//: Bu uzunluktaki ya da daha kısa bir parça tek başına cümle sayılmaz, önceki
//: parçaya eklenir. 3, tipik kısaltmaları ("Dr.", "vb.", "Sn.") kapsar; daha
//: yüksek bir değer gerçek kısa cümleleri ("Tamam." "Evet.") de yutardı.
const MIN_STANDALONE_SENTENCE_CHARS = 3;

export function splitIntoSentences(text: string): string[] {
  const trimmed = text.trim();
  if (!trimmed) return [];
  // Cümle sonu noktalamasından (. ! ? …) sonra gelen boşluk ve ardından yeni
  // bir karakter geldiğinde böl. Noktalamadan SONRA metin bitiyorsa (son
  // cümle) bölme olmaz, tek parça olarak kalır.
  const pieces = trimmed.split(/(?<=[.!?…])\s+(?=\S)/);
  const sentences: string[] = [];
  for (const piece of pieces) {
    const value = piece.trim();
    if (!value) continue;
    // Kısa olan ÖNCEKİ parçadır (ör. "Dr."), yeni parça DEĞİL: bir kısaltma
    // kendi başına asla "cümle" sayılmaz, ne kadar uzun bir devamı olursa
    // olsun bir sonraki parçaya eklenir.
    const previous = sentences[sentences.length - 1];
    if (previous !== undefined && previous.length <= MIN_STANDALONE_SENTENCE_CHARS) {
      sentences[sentences.length - 1] = `${previous} ${value}`;
    } else {
      sentences.push(value);
    }
  }
  return sentences;
}
