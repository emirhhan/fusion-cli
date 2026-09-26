# Claude düzeyi kapanış planı — 26 Eylül 2026

Hedef: Fusion'ın kullanıcının günlük işlerini (uzun kodlama, Motogate/WooCommerce,
Google Ads ve Meta yönetimi, tarayıcıda uzun akışlar, görsel üretimi, ses/hafıza/
projeler) mevcut ücretsiz sağlayıcılarla **ölçülerek** yapabilmesi. Model gücü
kapsam dışı; her fazda ölçülen kabul, kalite kapısı ve commit.

## Faz 1 — İzin ve soru deneyimi (Claude benzeri)

- **Kip anlamları** (tek yerde tanımlı politika tablosu, `engines/effects`):
  - *Otomatik*: okuma, çalışma alanı içindeki düzenleme, test/derleme ve güvenli
    kabuk komutları **sormadan** yürür. Yalnız geri dönüşü zor ya da dışa dönük
    işlemler sorar: çalışma alanı dışına yazma/silme, `git push`, yayımlama,
    canlı mağaza/reklam hesabında yazma, ödeme, gizli bilgi okuma.
  - *Yalnız plan*: yalnız okuma araçları; tur sonunda plan kartı ve
    "Onayla ve uygula / Düzenle / Vazgeç" seçimi. Onaylanınca aynı plan
    Otomatik kipte uygulanır.
  - *Güvenli*: her yazma ve komut sorar; "Bu oturumda bu tür işleme hep izin ver"
    seçeneği var.
- **`ask_user` aracı**: soru + 2-4 seçenek (+ açıklama, önerilen işareti) +
  "Diğer" serbest metin. Sistem talimatı: proje/özellik isteğinde gereksinim
  belirsizse ilk turda sor; kodla/varsayılanla çözülebilen şeyi sorma.
- **Arayüz**: ekranı kaplayan modal yerine composer üstünde, composer
  genişliğinde kompakt kart (Claude Code'daki gibi): tek satır başlık, insan dilinde
  özet (ham argüman yerine), gerekiyorsa diff, 1/2/3 kısayolları, Esc = reddet.
  Soru kartı aynı bileşenden.
- **Kabul**: her kip × 12 araç senaryosu için "sorar/sormaz" tablosu testle
  sabitlenir; canlı turda "bir blog uygulaması yap" isteğinde ajan önce seçenekli
  soru sorar; Otomatik kipte küçük bir düzeltme turunda sıfır izin sorusu.

## Faz 2 — Uzun, çok dosyalı kodlama güvenilirliği

- Kabul koşucusu (`evals/`): 3 gerçekçi görev, her biri **korunan** olumlu işlev
  testi + olumsuz güvenlik testi ile (ajan test dosyalarını değiştiremez):
  1. Yetkisi olan küçük bir Next.js projesinde yetkili CSV stok aktarımı
     (GATE'teki "auth yok" engeli yerine auth'u gerçek olan fikstür proje).
  2. Mevcut Python projesinde çok modüllü özellik + test onarımı.
  3. React arayüz özelliği + build.
- Ajan döngüsü iyileştirmeleri (ölçülen başarısızlıklara göre): başta plan →
  dosya dosya uygulama → her düzenlemeden sonra ilgili test → son düzenlemeden
  sonra tam test; olumlu işlev testi olmayan "reddet her şeyi" çözümleri
  başarısız sayılır; takılınca öğretmen devri.
- **Kabul**: her görev 2 kez koşulur; hedef en az 4/6 tam geçiş, sıfır sahte başarı.
  Tutmazsa sonuç ve kalan engel raporlanır.

## Faz 3 — Motogate / WooCommerce

- Novamira MCP bağlantısı Fusion'da (`mcp_servers`, token ortam değişkeninden;
  mevcut Novamira yenileme token'ı geçersiz → yeniden giriş gerekir).
- Canlı görevler: ürün arama, fiyat/stok okuma, son siparişleri özetleme,
  B2B fiyat kuralına göre öneri listesi; **yazma testi kullanıcının seçtiği
  kapsamda** (bkz. karar 2), her yazma izin kartıyla.

## Faz 4 — Tarayıcıda uzun akışlar, Google Ads ve Meta

- Chrome eklentisini Claude in Chrome düzeyine yaklaştır: `find` (erişilebilirlik
  ağacında metinle öğe bulma + ref), `read_page` ağacı, kaydırma, bekleme
  (öğe/metin görünene kadar), çoklu sekme, form doldurma, ekran görüntüsünü
  görsel modele gönderme.
- Canlı akışlar: Google Ads arayüzünde kampanya listesini okuma, bir kampanyanın
  metriklerini çıkarma ve öneri raporu (yazma yok); Instagram'da bir gönderinin
  yorumlarını okuma ve taslak yanıt yazma (gönderme izin kartıyla).
- Meta: Meta Ads MCP'ye bearer token ile bağlanma (`token_env`), hesap/kampanya
  içgörülerini okuma ve öneri; yazma yok.

## Faz 5 — Görsel oluşturma (basit ama çalışan)

- "Görsel oluştur" sayfası: istem kutusu, sağlayıcı seçimi (Gemini web / ChatGPT
  web), üretilen görsellerin ızgarası, indir/kaydet. Mevcut çerezli Playwright
  oturumu görseli üretir, dosyayı yerel klasöre indirir.
- **Kabul**: iki sağlayıcıdan en az birinde gerçek görsel dosyası iner ve sayfada
  görünür (CAPTCHA'ya takılan sağlayıcı raporlanır, zorlanmaz).

## Faz 6 — Uçtan uca kabul ve dağıtım

- Paketli uygulamada: ses (hoparlörden `say` ile mikrofona "merhaba" → hazır
  yanıt; normal soru → model yanıtı → seslendirme), hafıza ekle/sil ve yeni
  sohbette kullanımı, proje oluştur/taşı/sil, geçmişten sohbet açma, izin/soru
  kartları, görsel oluşturma. Her adım ekran görüntüsüyle.
- Kalite kapısı (Python, Ruff, mypy, React, Rust), paket, kurulum, rapor,
  onaylı push + release.
