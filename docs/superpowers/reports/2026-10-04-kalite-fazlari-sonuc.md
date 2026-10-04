# Kalite fazları — ölçülen sonuç (4 Ekim 2026)

Kaynak plan: [2026-10-04-nemotron-kalite-arastirmasi.md](2026-10-04-nemotron-kalite-arastirmasi.md).
Model: `nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b`, öğretmen Gemini web "3.6 Flash".
Ölçüm: `python -m evals.kabul` — her alanın bağımsız denetçisi, ajanın söylediğine değil
üretilen çıktıya bakar. Ham kayıtlar: `~/Desktop/01-Projeler/fusion-kabul/taban/` (önce) ve
`sonra/` (sonra).

## Önce → sonra

| Alan | Önce (baz) | Sonra | Not |
|---|---|---|---|
| Site kopyası (sneaksup → WP/Woo) | 6/14 (17. koşu, 90 dk sınırında) | **14/14**, 25,6 dk | Görsel benzerlik 0,89. Aynı kodla bir koşu 13/14 (benzerlik eşiği). |
| HTML oyun | 6/7 | 7/7, 7/7, 6/7 (üç tam koşu) | Üç koşudan biri "yeniden başlat" maddesinde kaldı; kararlı geçiyor denemez. İki koşu model cevap vermediği için uzadı. |
| Remotion | 8/8 (11,0 dk) | 8/8 (7,7 dk) | Puan aynı, süre kısaldı. İki denetçi hatası düzeltildi (kare farkı eşiği, alt klasördeki kaynak); eski koşular yeniden puanlandı. |
| Kendini geliştirme | 6/6 | 6/6 | Değişmedi. |
| Animasyon | 6/8 | 6/8 – 7/8 (üç koşu), kapanış kapısından sonra **8/8** (tek koşu, 27,5 dk) | Layout özelliği canlandırma kapısı eklendikten sonraki ilk tam koşu geçti; tek koşu istatistik değildir. |
| Tarayıcı (Fusion Browser) | 7/7 görünüyordu (curl ile) | 6/9 → 8/9 (gerçek Chrome, son koşu 5,5 dk) | Tarayıcıyla gezme ve form gönderme çalışıyor, tünel yok. Form alanları yanlış dolduruldu; alan geçmiş sayılmaz. |

Tek koşuluk sonuçlar istatistik değildir; her alan en az üç kez koşulmadan "geçti" denmez.

## Tarayıcı alanı: baz ölçüm yanıltıcıydı

- `chrome_navigate` ve `browser_open` yerel adresleri (127.0.0.1) 25 Eylül'den beri
  reddediyor (`tools/web.py: url_block_reason`). Kabul fikstürü yerel adreste çalışıyor.
- Ajan tarayıcı aracı reddedilince işi `curl` ile bitirdi. Baz ölçümdeki 7/7 de böyle geçti.
- Bir koşuda model kendi başına `ngrok` kurdu ve `cloudflared tunnel` ile yerel sunucuyu
  herkese açık adrese bağladı.

Yapılanlar:

- Denetçiye iki madde eklendi: `tarayiciyla_yapildi` (form ve tablo istekleri gerçek tarayıcı
  kimliğiyle gelmeli) ve `tunel_acilmadi`. Eski koşular yeni denetçiyle 4/9 ve 8/9.
- Tünel açan komutlar (`ngrok`, `cloudflared tunnel`, `lt --port`, `ssh -R`) tehlikeli komut
  listesine girdi; artık her kipte kullanıcıya sorulur.

Karar (kullanıcı onayıyla uygulandı): tarayıcı araçları, kullanıcının kendi mesajında açıkça
yazdığı yerel adrese (`localhost` / `127.0.0.1` / `[::1]` + port) gider
(`tools/web.py: browser_block_reason`, `ToolContext.local_origins`). Diğer özel ağ adresleri,
metadata ucu, mesajda geçmeyen yerel portlar ve `web_fetch` / indirme / tarama araçları eskisi
gibi kapalıdır. Bu değişiklikten sonra tarayıcı alanı henüz yeniden ölçülmedi.

İzin sonrası ilk ölçüm (dalga11): sayfalar gerçek Chrome'da gezildi, fiyat doğru bulundu, ama form
hiç gönderilmedi ve model "gönderildi" dedi. Kök neden eklentideydi: sayfada çalışan işlem hata
fırlatınca araç "başarılı: null" dönüyordu (seçim kutusuna yazma, eskimiş öğeye tıklama). Eklenti
İlk düzeltme (0.3.8) hatayı görünür yaptı ama sayfayı değiştiren başarılı tıklamaları da
"başarısız" saydı; ölçüm bunu yakaladı (dalga12: 8/9, form `python-requests` ile gönderildi,
denetçi `tarayiciyla_yapildi` maddesini düşürdü). 0.3.9 hatayı sayfadan veri olarak döndürüyor.
0.3.9 ölçümü (dalga16, Fusion uygulaması kapalıyken): **8/9, 5,5 dk**. Form ilk kez gerçek
tarayıcıyla gönderildi, hatalar araca ulaştı. Düşen madde `form_alanlari_dogru`: model "ad" alanına
"Destek" yazdı, konu seçim kutusunu "Satış"ta bıraktı ve yine de başarı bildirdi (sahte başarı 1).
Kalan sorun eklentide değil, modelin alan eşlemesinde ve seçim kutusu aracını kullanmamasında.
Not: Fusion uygulaması açıkken ölçüm eşleşmiyor (tek köprü dosyası); ölçümden önce kapatılmalı.

## Bu turda ayrıca düzeltilenler

- **Cevabın ezilmesi:** görev listesinde açık madde kalınca "bittiyse teyit et" notu altı kez
  gitti; modelin son kısa "tamamlandı" cevabı, fiyatı içeren asıl teslimin yerine geçti.
  Artık nottan önceki teslim korunur ve tur ilk teyitte biter (`loop.py`, `reflexion.keep_delivery`).
- **Oyun denetçisi:** `window.__GAME_STATE__` kancasını okur; yeniden başlatmayı oyun sonunda dener.
- **`play_probe`:** ajan oyunu başsız tarayıcıda oynatıp ölçer; `osascript` ile pencere
  sürmeye çalışması engellendi.

## Model çağrısı takılması (açık)

HTML oyun koşusu iki kez 10+ dakika "asılı" kaldı. Olay günlüğü satır satır yazılınca neden
görüldü: NIM modeli cevap vermiyor, tek çağrı ~10 dakika bekleniyor, ardından "deneme 1/10" ile
yeniden deneniyor. 600 sn sınırı bilerek seçilmiş (29 Eylül ölçümü: NIM büyük dosyayı araç
argümanı olarak yazarken akışta hiç parça göndermiyor; 120 sn sınırı her denemeyi kesiyordu).
Yani "takılan" çağrı ile "sessizce uzun yazan" çağrı bugün ayırt edilemiyor. Ayırt etmenin yolu
(ör. bağlantı açılış süresi) ölçülmeden değiştirilmedi; bu koşular geçersiz sayıldı.

## Ana menü, Kitaplık, Zamanlananlar, Kits

- En solda ana menü rayı: Home, Zamanlananlar, Kitaplık, Görsel ve video üretimi, Kits.
- Kitaplık: turda gerçekten değişen dosyalar, yüklenenler ve galeri görselleri.
- Zamanlananlar: tek seferlik, günlük, haftalık, aralıklı görevler; uygulama açıkken çalışır.
- Kits: ayrı depodaki modül (`fusion-kits`) tek dosyalı paket olarak uygulamaya gömülür; sohbetler
  dış servis olmadan yerel SQLite'ta tutulur. Gerçek modelle tur ve yeniden başlatma sonrası
  geçmiş doğrulandı. Paketli 0.7.0 içinde Kits ve Node çalışma zamanı var; imza doğrulandı.
- Doğrulanmayan: paketli uygulamada Kits bölümüne tıklayıp gömülü ekranı görmek (bu oturum
  uygulamaya tıklama gönderemiyor). Parçalar ayrı ayrı doğrulandı.

## Kalite kapısı

`ruff check` temiz, argümansız `mypy` temiz (464 dosya), `pytest` tam paket geçti (4 Ekim 20:02). Arayüz: 922+ test, derleme, `cargo clippy`, `cargo test` temiz. Kits: 223 test, lint, tip denetimi temiz.

## Açık kalanlar

1. Tarayıcı alanının yerel adres izninden sonra yeniden ölçülmesi (eklenti bağlıyken).
2. Animasyon alanı kapanış kapısıyla en az üç tam koşu.
3. Her alan için üçer koşu (istatistik); ikinci bir ücretsiz modelle genelleme koşusu.
4. MCP (Meta / Google Ads) tarafı bu ölçüm setinde yok.
5. Kabul koşuları terminal çekirdeğiyle yapıldı; masaüstü uygulaması + eklenti bağlıyken
   aynı set henüz koşulmadı.
6. Push yapılmadı. 0.7.0 yerelde paketlendi ve kuruldu (önceki sürüm yedekte).
7. Model çağrısında erken kesme (yukarıda).
8. CI paketlemesi Kits'siz kalır: Kits deposu ve Node ikilisi CI'da yok.
