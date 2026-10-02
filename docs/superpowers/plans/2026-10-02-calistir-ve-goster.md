# Çalıştır ve göster — "sneaksup" testinin dersleri

Kullanıcı Fusion'ın büyük bir işi nasıl yaptığını görmek için şunu istedi:
"sneaksup.com'a birebir benzeyen, her sayfası ve eklentisiyle gerçek çalışan
WordPress e-ticaret sitesi". Sonra "nasıl önizleyebilirim?" ve "ekstra bir şey
kurmadan önizlememi sağla" dedi.

## Ölçülen (2 Ekim 2026, sohbet `15606ae0`, Nemotron 3 Ultra / NIM)

| Ne oldu | Neden kötü |
|---|---|
| 10 dk'da 17 dosyalık tema iskeleti; WordPress çekirdeği yok, WooCommerce yok, ürün yok | "Gerçek çalışan site" istendi; hiçbir şey çalıştırılamazdı |
| Rapor: "✓ Doğrulandı: php -l 12 dosyada temiz" | Yalnız sözdizimi denetlenmişti; tema zorunlu `index.php` içermediği için WordPress'te etkinleşemiyordu |
| "Nasıl önizlerim?" → MySQL + WP-CLI + Docker rehberi, örnek parola | Makinede `php`, `wp`, `mysql`, `docker` zaten kuruluydu |
| "Kurmadan önizlet" → açılmayan bir `preview.html`, sonra bağlantı düzeltmeleri | Site hiç gösterilmedi; önizleme paneli vardı ama ajan ona adres veremiyordu |
| İşin büyüklüğü ve yapılmayanlar hiç söylenmedi | Kullanıcı "bitti" sandı |

Kabul koşusunda ek bulgu: değiştirme yetkisi olmayan modelde `ls -la`, `pwd`
bile "bu model dosya değiştiremez" diye engelleniyordu.

## Aşamalar

| # | Değişiklik | Dosya |
|---|---|---|
| 1 | **start_preview**: tür tespiti (WordPress/PHP/Node/statik), sunucuyu başlat, sayfayı ölç (HTTP, hata metni, boş sayfa, iç bağlantılar, konsol, ekran görüntüsü), `PreviewReady` olayı | `tools/preview_server.py`, `tools/preview_probe.py`, `engines/agent/preview_tools.py` |
| 2 | **WordPress'i kendisi kurar**: çekirdek (`--skip-content`), SQLite sürücüsü (MySQL'siz), kurulum (parola yalnız `.fusion/onizleme-giris.txt`, 0600), proje teması/eklentileri, tema kullanıyorsa WooCommerce; ikinci çağrıda yalnız eksik | `tools/wordpress_setup.py` |
| 3 | **Gerçek doğrulama**: sözdizimi kanıtı (`behavioral=False`) tek başına "Doğrulandı" saydırmaz; site kapısı PHP/WordPress'i çalıştırıp açar; zorunlu tema şablonu denetimi | `core/evidence.py`, `engines/agent/turn_report.py`, `engines/agent/site_verify.py`, `engines/agent/php_verify.py` |
| 4 | **Kendin yap**: ORTAM bloğu `wp`, `composer`, `mysql`, `docker`, `brew`'u da ölçer; sistem talimatı "makinedeki araçla yapılabilen kurulumu kendin yap; rehber yazma"; önizleme isteğine ve büyük kapsama özel tur notu | `engines/agent/project_instructions.py`, `prompts/system.md`, `engines/agent/turn_hints.py` |
| 5 | **Gösterme**: masaüstünde önizleme paneli `PreviewReady` ile kendiliğinden açılır; sohbette "Uygulamada aç / Tarayıcıda aç" kartı; terminalde adres satırı | `app/src/screens/PreviewCard.tsx`, `app/src/workspace/PreviewPanel.tsx`, `app/src/SessionApplication.tsx`, `ui/renderer.py` |
| 6 | Değiştirme yetkisi olmayan turda salt okuyan kabuk komutu engellenmez | `engines/agent/loop.py` |

## Ölçümler (elle, 2 Ekim)

- WordPress + SQLite kurulumu ~25 sn (çekirdek indirme 15 sn); WooCommerce kurulumu 5 sn;
  `php -S` ile ana sayfa 200, ürün oluşturma çalışıyor.
- Fusion'ın yazdığı sneaksup teması: `wp theme activate` → "Şablon eksik" (index.php yok).
  start_preview bu hatayı modele "SORUNLAR" altında verir.

## Kabul koşuları (aynı istek, boş klasör, `fusion agent --json`, Nemotron 3 Ultra / NIM)

Ölçüt kullanıcının beklentisidir: Fusion siteyi kendisi inceler; görselleri, yazıları,
yazı tiplerini ve bileşenleri ölçüp alır; ürün sayfaları ve sepetiyle çalışan siteyi
kurar ve gösterir.

| Koşu | Ne oldu | Kök neden | Düzeltme |
|---|---|---|---|
| 5 | 20 dk'da tek tema dosyası yok; `wp config create` + MySQL ile boğuştu | Boş klasörde `start_preview` "önce temayı yaz" deyip reddediyordu | `start_preview(kind="wordpress", plugins=[...])` boş klasörde kurar ve açar |
| 5 | `site_design` defterdeydi, hiç çağrılmadı; site 15 kez `browser_open` ile gezildi | Araç açıklaması tek başına yetmedi | Adres + benzerlik sözü taşıyan isteğe `DESIGN_NOTE` (`turn_hints.design_hint`) |
| 5-7 | Öğretmen plan veremedi | (a) Gemini "3.1 Pro" her soruya 85-340 sn sonra kalıp ret verdi ya da 180 sn sınırını aştı; (b) araçsız soruya da "araç çağır, todo_write ile plan yaz" çerçevesi ekleniyordu; (c) plan sorusu "kök neden / kod parçası" çerçevesiyle gidiyordu; (d) öğretmen çırağın araçlarını bilmiyordu ("Docker + MySQL kur" planladı); (e) ChatGPT oturumu captcha bekliyor | (a) kalıp ret ya da süre aşımında aynı hesapta KOMŞU modele geçilir ve süreç boyunca hatırlanır (`web_browser`), ret kalıbı ölçülen biçimlerle genişledi (`core/refusal.py`); (b) araçsız istek çerçevesiz gider; (c) `PLAN_FRAME`; (d) plan özetine araç listesi; reddeden öğretmene bir kez daha sorulur ve ret, öğretmeni tur boyunca kapatmaz; (e) kullanıcı işi: `fusion web-login chatgpt_web` |
| 5-6 | Süresi dolan turlar paylaşılan Chrome'da cevap üretmeye devam eden sahipsiz sekme bıraktı | Yeni sohbet sayfası havuza kaydedilmeden iptal ediliyordu | Sayfa hata/iptalde kapatılmak üzere sıraya alınır |
| 6 | `site_design`'dan sonra HER model çağrısı 500 verdi, devre açıldı | Araç sonucundaki ekran görüntüsü görsel okuyamayan modele gidiyordu ("multimodal processing is not enabled") | Görsel okuyamayan agent modeline araç görseli gönderilmez; yerine `view_image` notu. `start_preview` ekran görüntüsünü `.fusion/onizleme.jpg`'ye de yazar |

| 7 | Tema dosyası yazan çağrı 600 sn sınırını iki kez aştı; her seferinde baştan | NIM araç çağrısını parça parça akıtmıyor (ölçüldü: 250 satırlık dosya 181 sn tek sessizlik); aynı istek aynen yineleniyordu | Süre aşımından sonra modele "kısa adım at, dosyayı böl" notu; API istem katmanına "~150 satırı aşan içeriği böl" kuralı |
| 8 | Tema yazıldıktan sonra `start_preview` tekrar çağrısı `TOOL_CALL_DUPLICATE` ile engellendi; tema etkinleşmedi | Değiştirici aracın imzası çağa duyarsız | `Tool.reruns_on_change`: çalıştırıp ölçen araç değişiklikten sonra yeniden çağrılabilir |
| 8 | Kahraman alanı bomboş, menü madde imli, logo yazıyla çizilmiş; araç "hatasız açıldı" dedi | Görsel okuyamayan model ekran görüntüsünü göremez; 12 görsel 404 veriyordu | Önizleme yüklenemeyen kaynakları ADIYLA bildirir; kaynak site ölçülmüşse aynı ölçüm yerel sayfada yapılıp **KAYNAKLA FARKLAR** (görünmeyen yazı, logo, menü, yazı tipi, bölüm sırası/eksikleri, ürün sayısı, ürün sayfası düğmesi) yazıyla verilir (`tools/design_compare.py`); özet LOGO dosyasını söyler |
| 8 | Ürünler eklendiği halde /shop/ "coming soon" döndü | Yeni WooCommerce mağazası ziyaretçiye "Yakında" gösterir | Kurulumda `woocommerce_coming_soon=no` |
| 9 | Tema yazamadan düştü | NIM ~1 saat "Service temporarily overloaded" | Fusion dışı; aynı koşu NIM dönünce tekrarlandı |
| 10 | Hedef dizin olduğu için düşen `write_file`, dizin `rm -rf` ile kaldırıldıktan sonra da engellendi | Kabuk adımı düşen çağrıları serbest bırakmıyordu | Başarılı kabuk/çalıştırma adımı düşen çağrıları unutturur (çağ ilerlemez); dizine yazma denemesi "bu bir dizin" der |

`site_design` çıktısı (sneaksup.com, 5 sayfa, ~90 sn): 120 görsel, 16 yazı tipi dosyası,
2 kahraman videosu (6,5 + 15 MB), 48 ürünlük `urunler.json` (ad, fiyat, yerel görsel,
kategori; ayrıntı sayfasından galeri/seçenekler), ana sayfanın yukarıdan aşağı 14 bölümü
(tür, yükseklik, başlık yazı tipi, yerel medya) ve ürün sayfası düğme ölçüleri.

## Kapsam dışı / bilinen sınırlar

- WP-CLI yoksa kurulum yapılmaz, nasıl kurulacağı söylenir (`brew install wp-cli`).
- Önizleme sunucuları `fusion app` süreci yaşadıkça açıktır; uygulama kapanınca kapanır.
- "Birebir kopya" isteğinde kaynak sitenin logosu, görselleri ve metinleri YEREL çalışma
  için indirilir (kullanıcı böyle istedi); araç çıktısı ve tur notu, yayına almadan önce
  kendi içerikleriyle değiştirilmesi gerektiğini modele ve kullanıcıya söyler.
- Kalıp ret/süre aşımı sonrası geçilen komşu model süreç yaşadıkça kullanılır; seçili
  model düzelse de o süreçte geri dönülmez (yeni sohbet sekmesi/yeni koşu dener).
- Eklenti yolunda (`chrome` bağlıyken) sayfa kaydırılmaz ve çerez afişi gizlenmez:
  kullanıcının kendi Chrome'undaki sayfaya dokunulmaz; tembel yüklenen görseller eksik kalabilir.
