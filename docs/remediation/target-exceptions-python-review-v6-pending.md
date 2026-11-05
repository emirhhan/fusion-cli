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

## `54e1661f` üzerinde yeniden inceleme

Bu bölüm önceki yedi landmark bulgusunun son durumunu günceller: yedisi de
düzeltilmiştir. İlgisiz çalışma ağacı değişiklikleri incelenen sürüme karışmasın
diye `git archive 54e1661f` ile ayrı kaynak/test görüntüsü oluşturuldu.

- Önceki 12 bağımsız kontrol dahil ilgili beş modülde 161 test başarılı,
  8,03 saniye.
- Temas formu ve tarayıcı istek korumasında 58 test başarılı, 69,47 saniye.
- Dört dosyada Ruff ve biçim denetimi, iki kaynak dosyada dar mypy temiz.
- Kaynaklar: browser `2a095d6b39977e6e732aac42bdf82c95a8f705a8465b445e9a8e7a8c2c31e024`,
  web `8c3e014443aa8b1ee4697f3de32dce0cee71bafd2616c2fc24bcc7cb37b1d3d2`.

**Kalan bulgu — Yeni atalar yığını eşleşmeyen kapanış etiketlerinde karesel iş yapıyor.**
`handle_endtag`, açılmamış bir etiketi her gördüğünde tüm yığını geriye doğru
tarıyor. Ölçümde 100 açık `div` ve 100 eşleşmeyen kapanış 10.000 yığın okuması;
500 ve 500 ise 250.000 okuma üretti. Aynı kontrollü girdinin 9.026/36.026/108.026
karakterlik sürümleri 0,0068/0,0866/0,7279 saniye sürdü. Bu süreler tek makinedeki
gözlemdir; daha büyük dosya süresi ölçülmüş gibi sunulmaz.

Dokunulan HTML dosyaları boyut sınırı olmadan okunur ve statik inceleme event loop
üzerinde eşzamanlı yürür. Bu nedenle yalnız yeni yığın hesabının eşleşmeyen
etiketlerde doğrusal tutulması veya açık sınırlı bir geri dönüş kullanılması
önerildi. Bu, tam CSS/ARIA motoru istemi değildir. Dar düzeltme/karar beklenirken
son onay verilmedi; önceki landmark kusurları açıkmış gibi raporlanmadı.
