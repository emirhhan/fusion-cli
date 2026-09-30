# CI, arayüz eşliği ve öğretmen paketi — sonuç raporu (30 Eylül 2026)

Onaylanan faz sırası: A) CI → B) Claude gibi sohbet → C) ChatGPT görünümü →
D) Beceriler/Uygulamalar → E) Görsel stüdyosu → F) Meta + öğretmen → G) Ayarlar.
Çalışma bulut ortamında (Linux, root) yapıldı; paketli macOS uygulaması ve canlı
model turu bu ortamda denenemedi.

## A — CI yeniden yeşil

`main` üzerindeki CI en az son 5 koşuda kırmızıydı. Kalite kapısı `ruff format
--check` adımında 1 saniyede düşüyor, mypy ve testler CI'de hiç koşmuyordu.

- 77 dosya `ruff format` ile biçimlendirildi.
- mypy Linux ve Windows hedefinde platform dallarını erişilemez sayıyordu
  (Windows'ta 15 hata). Dallar mypy'ın anladığı `if/else sys.platform` biçimine
  getirildi. `mypy --platform linux|win32|darwin` üçü de temiz.
- Ortama bağlı testler: `OPENROUTER_API_KEY` bir testten sızıp `test_keys`'i
  yalnız tam koşuda düşürüyordu. `tests/conftest.py` her testten sonra süreç
  ortamını geri yüklüyor ve sağlayıcı anahtarlarını testlere sokmuyor.
- Root kullanıcıda kurulamayan "yazılamayan dosya" testleri `yazma_yasagi_kurulabilir`
  fikstürüyle atlanıyor; macOS'a özgü imzalama testi Linux'ta atlanıyor.
- Ürün hatası: anahtarlığı olmayan Linux'ta kimlik doğrulama istemeyen HTTP MCP
  bağlantısı bile `NoKeyringError` ile düşüyordu (`mcp_bridge/tokens.py`).
- `Makefile` `EXTRAS`'ı paketlemeyle aynı hale getirildi (`web` eksikti); CI'ye
  Chromium kurulum adımı eklendi. README'deki bulut komutları venv ile düzeltildi.

## B — Claude gibi sohbet

- Biten araç adımları tek satırda türlerine göre özetleniyor: "2 komut
  çalıştırıldı, dosyalar bulundu, Makefile okundu ›" (`protocol/adimOzeti.ts`).
- Canlı durum satırı: "✳ Pytest çalıştırılıyor… 9 dk 14 sn · 2,0 bin token".
  Token sayısı `ModelCallFinished.result.usage.completion_tokens`'tan gelir;
  kullanım bildirmeyen web oturumlarında sayı uydurulmaz.
- Ara anlatım metninin altındaki kopyala düğmesi kaldırıldı, hizalama düzeltildi.
- `system_api.md` konuşma biçimi örneklerle yeniden yazıldı; giriş istemi
  "Anladığım kadarıyla / Elbette" girişlerini yasaklıyor.
- İptal edilen tur artık geçmişte kalıyor: "devam et" denince model neyin
  yarıda kaldığını görüyor (`appserver/session.py`).

## C, D, E — Görünüm

- Palet ChatGPT değerlerine çekildi (koyu zemin `#212121`, kenar `#181818`).
  Koyu Ayarlar'daki kahverengi tonlar (`#382724` vb.) gerekçesiz bir sürüm
  commit'iyle gelmişti; nötr grilere döndü.
- Composer 28 px kapsül, siyah/beyaz ses düğmesi; uyarı metni composer'ın altına
  taşındı; okuma kolonu 768 px.
- Uygulamalar (eski "Bağlantılar") tablo yerine ChatGPT tarzı kart ızgarası.
- Beceriler: tür sekmeleri, "Etkin · N" bölümü, harf avatarları, sade ayrıntı paneli.
- Görsel oluştur: kare ızgara galeri, üzerine gelince eylem düğmeleri, tek görsel
  görüntüleyici (klavye ile gezinme, istemi yeniden kullan), yüzen istem çubuğu;
  iş akışı tuvalinde düğüm paleti tuvalin altında yüzen araç çubuğu.
- Önizleme düzeneğine (`app/e2e/preview.tsx`) `state=running` ve `state=image`
  eklendi.

## F — Meta ve öğretmen

- Meta Reklamları katalog girişi: client_id gerektirmeyen rehberli token yolu
  (sistem kullanıcısı token'ı → Bearer). Token şifreli depoda tutulur.
- Öğretmene giden pakete rol ve cevap biçimi çerçevesi ile düzenlenen/okunan
  dosyalardan kod kesitleri eklendi. Daha önce yalnız dosya yolları gidiyordu;
  web öğretmeni kodu görmeden cevap veriyordu. `.env*` hiç okunmaz.
- Maskeleme OpenRouter (`sk-or-v1-…`) ve NIM (`nvapi-…`) anahtarlarını
  tanımıyordu; eklendi.

## G — Ayarlar

Dokuz sekme 1280 ve 820 px'te tıklanarak denetlendi: konsol hatası ve yatay
taşma yok. Modeller sekmesindeki sıkışık anahtar/değer düzeni düzeltildi.

## Açık kalanlar

- Hiçbir değişiklik paketli macOS uygulamasında ve canlı modelle denenmedi.
- ChatGPT'nin kendisiyle yan yana piksel karşılaştırması yapılamadı (bu ortamda
  ChatGPT oturumu yok); değerler bilinen ChatGPT tasarım ölçülerine göre ayarlandı.
- Kontrol Paneli (sağlayıcılar) önizlemede veri olmadan boş; yeniden tasarlanmadı.
- Görsel oluşturmada en-boy oranı seçimi eklenmedi: NIM FLUX'un kabul ettiği
  boyutlar doğrulanmadan sabit yazılmadı.
- Meta rehberindeki adımlar Meta'nın güncel arayüzüyle canlı doğrulanmadı.
