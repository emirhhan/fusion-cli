# Hedef istisnaları ve landmark: ilk bağımsız Python incelemesi

5 Kasım 2026, ürün sürümü `a19d61f3`. Sonuç: **ONAY BEKLİYOR**. Ana ajanın
yetkilendirdiği dar landmark düzeltmesi tamamlanmadan bu sürüm onaylanmadı.

## Bulgular

**ORTA — Görünmeyen öğedeki rol gerçek landmark sayılıyor.**
`_MainLandmarkParser.handle_starttag`, `script`, `style` veya `meta` üzerindeki
`role="main"` özniteliğini yeterli sayıyor. Böylece gerçekte ana içerik landmark'ı
olmayan belgede öneri kayboluyor. Bu üç örnek yeni rol dalının gerilemesidir; eski
yalnız-etiket kontrolü bunları landmark saymıyordu. Bulgu yalnız önerinin
doğruluğuyla ilgilidir; güvenlik veya engelleyici doğrulama atlaması değildir.

Aynı dar düzeltme kapsamına, `template` içindeki `<main>`, `hidden` ana öğe,
`hidden` atası olan rol ve `role="presentation"` ile örtülmüş yerel `<main>`
örnekleri de açıkça alındı. Bunlar önceki etiket deseninde de eksikti; yeni
gerileme olarak sunulmadı. Tam CSS/ARIA motoru talep edilmedi.

## Bağımsız kanıt

- İzole Chromium sayfalarında bütün ağ istekleri engellendi. Playwright rol
  sorguları gerçek `<main>` ve `div role="main"` için bir landmark, yorum/script
  metni, textarea/title metni, template, gizli ana öğe ve sunum rolü için sıfır
  landmark gösterdi. İlk dört sahte metin örneğinde mevcut öneri korunuyordu.
- Görev çalışma alanındaki
  `work/reliability-v2/a11y-python-review-v6/test_landmark_contract.py` dosyasında
  12 ek kontrol var: yedi yetkilendirilmiş landmark örneği kırmızı; gerçek
  landmark, uyarı/öneri ayrımı, ölçülemeyen durumun `UNVERIFIED` kanıtı ve bozuk
  geometri satırları için beş kontrol yeşil.
- Web/browser/hedef istisnaları/önem derecesi/d4 browser modüllerinde 132 test
  başarılı, 7,55 saniye.
- Temas formu ve tarayıcı istek koruması modüllerinde 58 test başarılı,
  68,09 saniye. Gerçek model/native çağrı yapılmadı.
- Dört değişen Python dosyasında Ruff, iki ürün dosyasında dar mypy temiz.

İncelenen kaynak SHA-256 değerleri:

- `browser_verify.py`: `c78d1770a4c2e16001d12b72dd6223fb80f9c33734907d8a6d5d0749abb1bd0d`
- `web_verify.py`: `16fdca0f6970a0ec2764da746b99e010fc1860b2756dbde322f339e0eed8f07f`

Gömülü JavaScript istisna ispatının bağımsız TypeScript incelemesi ayrı yürütülür.
Bu belge bir düzeltme sonrası onay veya tam WCAG uygunluk değerlendirmesi değildir.
