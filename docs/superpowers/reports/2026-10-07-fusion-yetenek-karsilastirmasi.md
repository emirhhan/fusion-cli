# Fusion yetenek gelişimi — ölçüm sözleşmesi ve mevcut kanıt

Kullanıcının amacı Fusion’ın dört alanda tabana kıyasla %90 daha gelişmiş ve profesyonel üretim yapmasıdır. Eski çıktıyı elle onarmak, doğrulayıcı puanını yükseltmek veya tek bir başarılı örnek bu amacı karşılamaz. Yeni işler boş dizinden Fusion tarafından üretilmelidir; ürün kusurlarından çıkan düzeltmeler ortak motora, araca, beceriye veya kalite kapısına uygulanmalıdır.

## Kurtarılan taban

Kaynak: `fusion-kabul/taban/dalga*/rapor.json`. Geçersiz koşular kalite puanına katılmaz.

| Alan | Kullanılabilir taban | Eski denetim sonucu | Sınır |
| --- | --- | --- | --- |
| HTML oyun | dalga2 | 5/7; tuş tepkisi ve yeniden başlatma başarısız | Son görev varlıklar, boss ve uzun oyun içeriyor; ölçüt sayısı 10'a çıktı |
| Animasyon | dalga3 | 6/8; layout animasyonu ve easing çeşitliliği başarısız | Dalga2 sürücü çıktısız, geçersiz; profesyonellik doğrudan puanlanmadı |
| Remotion | dalga3 | 7/8 | Yeni görev ve ölçütler değişti; dalga27 11/11 olsa da insan gözleminde yerleşim kusurları vardı |
| Site kopyalama | dalga1 | Geçersiz, 0/0 | Denetçi URL hatası; karşılaştırılabilir geçerli taban yok |

Bu geçmişten dört alan için güvenilir %90 gelişim oranı hesaplanamaz. Eski ve yeni maddelerin sayısı farklıdır; site tabanı geçersizdir. En iyi koşuyu seçmek, başarısız/yarım üretimleri saklamak veya sağlayıcı kesintisini ürün kalitesiyle karıştırmak sonucu çarpıtır.

## Yüzde tanımı

Göreli iyileşme, aynı ölçekte `(sonra - taban) / taban * 100` olarak raporlanır. Mutlak %90 kalite ve kalan kusurların %90 azalması farklı ölçülerdir; kullanıcının istediği göreli gelişimin yerine konmaz. 7/8 gibi doygun eski kontrol oranının tavana ulaşması yalnız %14,3 göreli artıştır; bu oran profesyonellik gelişimini ölçmeye uygun değildir. %90 hedefinin kanıtlandığı iddiası şu an yapılmıyor.

## Eş koşullarda yeni kabul

Her alan için aynı brief, model/öğretmen yapılandırması, süre bütçesi, viewport ve denetim sürümü kaydedilir. Taban revizyonu ile güncel Fusion aynı boş başlangıç koşullarında değerlendirilir. Ardından farklı brief ile aktarım sınanır; eski çözüm dosyaları yeni koşuya verilmez. Ağır koşular sıralı yürür. Sağlayıcı/sürücü/denetçi hataları ayrı geçersiz ölçüm olarak gösterilir. Başarı oranları tüm geçerli denemeleri kapsar.

İşlev kapısı zorunludur: eksik dosya, gerçek tıklama ile başlayamama, konsol hatası, donma, bozuk rota, render taşması/çakışması/boş sahne varsa profesyonel teslim kabul edilmez. Kapıyı geçmek tek başına profesyonellik puanı değildir.

| Alan | İşlev kanıtı | Görsel ve profesyonellik kanıtı |
| --- | --- | --- |
| Oyun | Gerçek Başla tıklaması; yön/ateş/pause; oyun sonu ve yeniden başlatma; uzun oynama; file://; varlık yükleme | Menü, oynama ve bitiş görüntüleri; okunur HUD; tutarlı sprite; tepki, zorluk, efekt ve akıcılık |
| Remotion | Strict tsc; gerçek render; her sahne ve son saniyeler; yerleşim kapısı | Tipografi, kompozisyon, ritim, geçiş, görsel tutarlılık; boş son bölüm ve kesik metin olmaması |
| Site kopyalama | Ana/kategori/ürün/sepet/checkout; kontroller ve kırık kaynaklar; farklı viewport | Kaynak ile aynı viewport karelerinin karşılaştırılması; logo, tipografi, boşluk, görsel, renk, yerleşim; birebir benzerlik |
| Animasyon | Tüm kaynaklar; kaydırma/hover/etkileşim; konsol; reduced-motion ve donmama | Zamanlama, easing, hiyerarşi, akış, okunurluk ve hareketin amaca uygunluğu |

Görsel değerlendirme kaynak görüntü/kareleriyle birlikte gerekçeli ve aynı rubrikle yapılır. Bir sayı için ağırlıklar sonuç görülmeden sabitlenmelidir; eski raporlarda böyle bir profesyonellik rubriği bulunmadığından geçmişe yeni puan uydurulmaz.

## Bu turdaki genel gelişim

Remotion ortak kitinde normal akış, dış kart boyutu ve gerçek render yerleşim kapısı düzeltildi. Oyun ortak sondasında gerçek düğme tıklaması, durum geçişi ve sonda hatasının başarısızlık olarak dönmesi düzeltildi. Bu değişiklikler regresyonlarla doğrulandı; yeni üretimde aktarım ve dört alan karşılaştırması henüz tamamlanmadı.
