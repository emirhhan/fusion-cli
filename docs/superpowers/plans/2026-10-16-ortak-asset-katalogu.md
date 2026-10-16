# P12 — Ortak asset kataloğu

Mevcut `core/assets.py` doğrulama/lisans otoritesidir; `core/artifacts.py` büyük araç çıktısını saklar. İkisi galeri kimliği deposu değildir. Galeri yan dosyaları istem/sağlayıcı bilgisini, görsel iş makbuzu ise tamamlanma kanıtını tutar. Yeni katalog bu otoriteleri çoğaltmaz: yalnız dosya kimliği, izinli kök ve soy bağı kaydeder.

## Sözleşme

- SQLite katalog, kapsam/kök/göreli yol için tek kalıcı `asset_id` verir. Yeniden kayıt ve süreç açılışı aynı kimliği döndürür; dosya adı değişimi açık taşıma işlemi olmadan yeni kimliktir.
- `metadata_version: 1`, `kind`, `mime`, `relative_path`, `created_by_task_id`, `parent_asset_ids`; bilinmeyen model/seed/alpha/boyut null. İstek değeri gerçek ölçü diye kaydedilmez.
- Çözümleyici çağrıda verilen izinli köklere bağlıdır. Kimliği bilmek başka kökten dosya okuma yetkisi vermez. Kök dışına çıkan bağ, kayıp dosya veya başka kapsam kaydı reddedilir.
- Silinmiş ebeveyn soy bilgisini silmez; ebeveynin kullanılabilirliği ayrı sonuçtur.
- Eski galeri yolu ve yan dosyalar additive kayıt ile taşınır; eski istemci `yol` almaya devam eder. Yeni ortak alan aynı galeri/kitaplık/host yanıtında taşınır.
- Katalog listelemesi `(created_at, asset_id)` tam sıralı cursor kullanır; sayfa üst sınırı vardır. Görsel işinin başarı durumu katalog kaydından türetilmez.

## Sıra ve kabul

1. Saf kimlik/persistence/scope/missing/parent/cursor testleri kırmızı.
2. Küçük SQLite store ve mevcut path resolver adaptörü. Katalog şeması ileri sürümde fail-closed.
3. Galeri ve kitaplık aynı registration/resolve adaptörünü kullanır; eski path/sahipsiz metadata migration testi.
4. App/Kits ortak referans tipleri ve host bridge: eski host capability yoksa eski yol korunur, yeni kritik eylem ilan edilmez.
5. Gerçek roundtrip ve 10.000 kayıt ölçümü. UI karşılaştırma/yorum ayrı küçük görevdir; kullanıcının son talimatı doğrultusunda yeniden onay sorulmadan tarayıcıda doğrulanır.
6. Python/TS inceleme, ilgili testler ve paketlenmiş bridge smoke. Geçmeyen kabul açık kalır.

Durum: katalog, indeksli sayfalama, sınırlı önizleme, App/Kits belge roundtrip, galeri karşılaştırması ve cihazda yerel not uygulandı. Paketlenmiş çekirdek ile ayrı derlenmiş Kits üzerinde seçim–kaydetme–yeniden açma–kayıp dosya tarayıcı kontrolü geçti. Karşılaştırma/not arayüzünde 7 tarayıcı kontrolü geçti. Yerel not bulut yorumu değildir; native Tauri/hardware kabulünün yerine geçmez. Son toplu test sonuçları ilerleme kaydına eklenecek.
