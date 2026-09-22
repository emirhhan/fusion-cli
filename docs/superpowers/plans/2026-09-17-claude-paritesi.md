# Claude Paritesi Planı (17 Eylül 2026)

Kaynak: 74 turluk kullanıcı denetimi (74 turun 37'si başarısız, 66 bulgu).
Hedef: ilk mesajdan son mesaja kadar Claude'a yakın davranış; ürün tamamen ücretsiz kalır.

Mimari yön: **Öğretmen–Çırak**. Çırak = ücretsiz API modelleri (araç çağrısı yerleşik,
262K–1M bağlam, ölçülen çağrı süresi 1,3 sn). Öğretmen = ChatGPT/Gemini web (plan,
takılmada danışma, son denetim; tur başına en fazla 4 çağrı). Uzun metin ve görseller
web sağlayıcıya DOSYA olarak yüklenir (ölçüldü: 74 bin karakter 8 sn, doğru cevap).

## Faz sırası

Her faz sonunda kalite kapısı çalışır (`ruff check` + `mypy` + `pytest`), sonra Türkçe
conventional commit atılır. Faz bitmeden sonrakine geçilmez.

### Faz 1 — Görünür hasarı durdur · TAMAM (21 Eyl 2026, bkz. reports/2026-09-21-claude-paritesi-faz1-faz2-sonuc.md) (bulgular D1, D2, A7, B1, C1, C2)

1. **Cevap biçimini koru (D1).** Web cevabı `innerText` yerine HTML'den Markdown'a
   çevrilerek okunur. Yeni saf modül + testleri.
2. **Sahte uyarıları kaldır (D2).** Adım kanıt kaydı düzelir; "doğrulama komutu yok"
   uyarısı yalnız gerçekten komut yoksa çıkar.
3. **Yanıt tamamlanma algısı (A7).** 192 saniyelik boş beklemeler biter.
4. **Sohbet kipinde iş akışı kapalı (B1).** Sohbet turu dosya yazmaz, plan motoruna girmez.
5. **Sağlayıcı sağlığı (C1, C2).** Varsayılan model ölçümü geçmiş olan olur; oturum
   hatasında yedeğe geçilir; web oturumu için gizli pencere kipi eklenir.

### Faz 2 — Tek ajan döngüsü · TAMAM (21 Eyl 2026, ayrıntılı plan: plans/2026-09-18-tek-ajan-dongusu.md) (A1, A2, A4, B2, B3, B4)

1. Plan adımları tek konuşma geçmişini paylaşır; geçmişsiz alt tur kaldırılır.
2. Düzenleme tam metin eşleşmesiyle yapılır, sonucunda diff modele döner.
3. Başarı beyanı yalnız projenin kendi test/build komutuna bağlanır.
4. Onay reddi turu durdurur; gözlem turunda yazma tümden kapalıdır.

### Faz 3 — Çırak katmanı · TAMAM (22 Eyl 2026, bkz. reports/2026-09-22-cirak-katmani-sonuc.md) (C5, C6, C9, C10)

1. Araç işleri ücretsiz API modeline taşınır (yerleşik araç çağrısı, akış).
2. Model zinciri ve hız sınırı yönetimi (429'da sıradaki modele geçiş).
3. Görsel okuma ücretsiz görsel modelleriyle açılır.

### Faz 4 — Öğretmen protokolü · TAMAM (22 Eyl 2026, ayrıntılı plan: plans/2026-09-22-ogretmen-protokolu.md, sonuç: reports/2026-09-22-ogretmen-protokolu-sonuc.md) (A3, A5, A6, A11, C7, C8)

1. Brief derleyici: durum + ilgili kod + denenenler + tek soru, en fazla 25 bin karakter.
2. Dosya yükleme (uzun metin, ekran görüntüsü) ve kırpma bildirimi.
3. Ders defteri `.fusion/ogretmen.md`, görev defteri, öğretmensiz kip.
4. Kademe doğrulama (Flash-Lite'a düşerse bildir), günlük çağrı bütçesi.

### Faz 5 — Arayüz paritesi · TAMAM (22 Eyl 2026, ayrıntılı plan: plans/2026-09-22-arayuz-paritesi.md, sonuç: reports/2026-09-22-arayuz-paritesi-sonuc.md — G6/G7 ve G3/G4'ün masaüstü tarafı BACKLOG'da) (H1–H13, D3, D4, D5)

Akış, düşünme bloğu, görev listesi, onayda diff önizlemesi, Esc ile kesme, `@` ile dosya
anma, bağlam/maliyet göstergesi, takip önerileri, başlık üretimi, tek kutu (kip ayrımının
kaldırılması), arka plan işleri, alt ajan kartları.

### Faz 6 — Bağlayıcılar · TAMAM (22 Eyl 2026, bkz. plans/2026-09-22-baglayicilar.md, reports/2026-09-22-baglayicilar-sonuc.md) (E1–E7)

Hata sınıflandırma, kaydetmeden doğrulama, kayıt defteri araması, gerektiğinde başlatma,
ChatGPT connector köprüsünün doğrulanması.

### Faz 7 — Ölçüm · TAMAM (22 Eyl 2026, bkz. plans/2026-09-22-kapanis-fazlari.md, reports/2026-09-22-kapanis-fazlari-sonuc.md)

Denetimdeki 74 tur `evals/` altına senaryo olarak girer. Kabul eşiği: doğru tur oranı
%70 üstü, yalan başarı 0, uzun oturumda 21/21 tamamlanma, ortalama tur 90 saniyenin altı.

**Yapıldı, bir sapmayla:** 74 turluk kaynak dosya (`fusion-denetim.html`) kayıp —
depoda, diskte ve git geçmişinde arandı, bulunamadı. Set bulgu kimliklerinden
yeniden kuruldu (`evals/suite/parite.yaml`, 14 gerileme senaryosu). Dört eşik
`evals/acceptance.py` ile makine-okunur oldu ve `--enforce` ile çıkış koduna
bağlandı. Yalan başarı bugüne kadar hiç ölçülmüyordu; ölçüm hattına eklendi.

## Açık kalan ölçümler

- ChatGPT üzerinden dosya yükleme ve connector köprüsü. **Kök neden bulundu**
  (22 Eyl): kullanıcının ChatGPT hesabı bir kerelik insan doğrulaması istiyor.
  Kod tarafı çalışıyor; tek adım `python -m fusion_cli.providers.web_login
  chatgpt_web main`. CAPTCHA otomatik aşılamaz.
- Uzun oturumun son 5 turu.
- `parite.yaml`'ın canlı koşusu: birincil web oturumu doğrulanana kadar her tur
  yedeğe düşüyor ve ortalama tur süresi 90 sn eşiğinin üstünde kalıyor
  (ölçüldü: önemsiz bir okuma turu 2 dk 54 sn).
