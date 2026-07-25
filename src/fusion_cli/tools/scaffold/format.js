/* Biçimlendirme yardımcıları — HAZIR VE DOĞRU. Kendin yazma, bunları kullan.
 *
 * Ölçülen gerçek hata: model fiyatı yüze BÖLEREK biçimlendirdi ve 14.999 TL'lik
 * ürün sayfada ₺149,99 göründü. Fiyat ANA BİRİMDE (TL) saklanır, bölünmez.
 *
 * KLASİK BETİKTİR (modül dışa aktarımı YOK): ES modülleri file:// protokolünde CORS ile engellenir
 * ve sayfa çift tıklanarak açıldığında JavaScript hiç çalışmaz.
 */

/** 14999 -> "₺14.999"  (fiyat ANA BİRİMDE, kuruş değil) */
function formatPrice(tutar) {
  return new Intl.NumberFormat('tr-TR', {
    style: 'currency', currency: 'TRY', minimumFractionDigits: 0, maximumFractionDigits: 0,
  }).format(tutar);
}

/** 1234.5 -> "1.234,5" */
function formatNumber(sayi) {
  return new Intl.NumberFormat('tr-TR').format(sayi);
}

/** Date | ISO metin -> "15 Mayıs 2024"  (İngilizce ay adı sızdırmaz) */
function formatDate(tarih) {
  const d = tarih instanceof Date ? tarih : new Date(tarih);
  return new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long', year: 'numeric' }).format(d);
}

/** 0.25 -> "%25" */
function formatPercent(oran) {
  return new Intl.NumberFormat('tr-TR', { style: 'percent', maximumFractionDigits: 0 }).format(oran);
}

/** Basit e-posta doğrulaması (form geri bildirimi için yeterli). */
function isValidEmail(deger) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(String(deger).trim());
}
