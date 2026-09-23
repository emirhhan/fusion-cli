# Fusion ürün denetimi — 23 Eylül 2026

## Bu oturumda doğrulananlar

- Terminal panelinin yüksekliği sınırlandı. Kurulu uygulamada PTY açıldı, komut
  çalıştı ve önceki sürekli yeniden boyutlandırma döngüsü görülmedi.
- Konuşma yeni yanıtta alta kayıyor; kullanıcı geçmişi okurken zorla kaydırılmıyor.
- Ayarlar sekmeleri arasında başlık ve Kapat düğmesi sabit kaldı.
- İzin kartları doğrudan seçilebilir düğmelere dönüştü; her kart ilgili çalışma
  modu komutunu kullanıyor.
- Dar denetçide web önizleme araç çubuğu iki satıra yerleşti; adres alanı ve
  diğer kontroller panel dışına taşmadı.
- Doğrulama isteyen sağlayıcının devresi aynı oturumda yeniden denenmeden
  açık kalıyor. Devresi açık birincil model, katı zincirde yedeği kilitlemiyor.
- NIM Ultra profili kullanıcı uygulamasında seçildi; yeni bir görevde basit
  soruya doğru yanıt döndü. Yanıt süresi birkaç dakika olduğundan hız sorunu
  açık bulgudur.

## Kalite kanıtı

- `ruff check .` ve `mypy`: temiz.
- `python -m pytest -q`: başarılı.
- Frontend: 683 test başarılı; TypeScript ve Vite build başarılı.
- Rust: format, Clippy ve testler başarılı (74 test, 3 kasıtlı atlanan).
- macOS app/dmg paketi üretildi; imza ve paket içi çalışma testi doğrulandı.
- Kurulu uygulamada terminal, ayarlar, izinler ve web önizlemesi görsel olarak
  denetlendi.

## Açık ürün işleri

1. NIM Ultra ile basit görevin birkaç dakika sürmesinin nedenini model çağrısı,
   araç turu ve ilk çalışma alanı hazırlığı olarak ayrı ayrı ölçmek.
2. Görsel oluştur ve video oluştur gezintileri hâlen işlevsiz boş ekran açıyor.
3. Fusion motoru tek aday seçildiğinde çok modelli değerlendirme yapamıyor;
   arayüz bu durumu açıkça bildirmeli ve çok adaylı profile dönüş sağlamalı.
4. Profesyonel web sitesi üretimi, Fusion'ın kendi deposunda değişiklik yapması,
   GATE HOLDING benzeri tarayıcı işi, reklam kontrolü ve otomasyon için ayrı
   uçtan uca kabul koşuları henüz tamamlanmadı.

Bu bulgular tamamlanmadan ürünün Claude düzeyinde bütün işleri yaptığı sonucu
çıkarılamaz.
