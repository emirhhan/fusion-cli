/** `@` ile dosya anma: imlecin önündeki anma parçasını bul.
 *
 * Anma yalnız KELİME BAŞINDAKİ `@` ile başlar: `bir@iki` bir e-posta ya da
 * tanıtıcı olabilir, dosya anması değil. Anma imlece kadar sürer ve içinde
 * boşluk BULUNMAZ — kullanıcı boşluk yazdığı anda anma kapanır.
 */
export interface DosyaAnmasi {
  /** `@` karakterinin metindeki konumu. */
  baslangic: number;
  /** `@` ile imleç arasındaki sorgu (boş olabilir). */
  sorgu: string;
}

export function anmayiBul(metin: string, imlec: number): DosyaAnmasi | null {
  const kesit = metin.slice(0, imlec);
  const yer = kesit.lastIndexOf("@");
  if (yer < 0) return null;
  const onceki = yer === 0 ? "" : kesit[yer - 1];
  // Kelime başı: metnin başı ya da boşluk. `(`/`[` gibi işaretler de kabul
  // edilir; kullanıcı parantez içinde dosya anabilir.
  if (onceki && !/[\s([{,;]/.test(onceki)) return null;
  const sorgu = kesit.slice(yer + 1);
  if (/\s/.test(sorgu)) return null;
  return { baslangic: yer, sorgu };
}

/** Anmayı seçilen yolla değiştir; imlecin yeni konumunu da döndür. */
export function anmayiDegistir(
  metin: string,
  anma: DosyaAnmasi,
  imlec: number,
  yol: string,
): { metin: string; imlec: number } {
  const once = metin.slice(0, anma.baslangic);
  const sonra = metin.slice(imlec);
  // Yolun ardına boşluk konur: kullanıcı yazmaya devam edince yeni bir anma
  // başlamasın ve iki yol birbirine yapışmasın.
  const parca = `@${yol} `;
  return { metin: `${once}${parca}${sonra}`, imlec: once.length + parca.length };
}
