# Task 1 Raporu — Tanıma olay sözleşmesi ve ses etkinliği kapısı

## Uygulama

- macOS yardımcı çıktısı `TanimaOlayi` ile beş alanlı JSONL sözleşmesine taşındı: `tur`, `metin`, `guven`, `speech_ms`, `segment`.
- `guven` bulunmadığında alan atlanmıyor; açıkça `null` kodlanıyor. Yardımcı yeni bir session kimliği üretmiyor; Rust süreç düzeyi session sahipliği korunuyor.
- İlk 300 ms ortam kalibrasyonu, RMS tabanlı iki eşikli başlangıç/bitiş histerezisi, 80 ms başlangıç doğrulaması ve 350 ms bitiş doğrulaması eklendi.
- Tanıyıcıya yalnız VAD etkin olduktan sonraki mikrofon tamponları iletiliyor. 250 ms'den kısa konuşma aralıkları ve `0.2` altındaki final segment güveni `son` üretemiyor.
- Apple güven değeri `SFTranscriptionSegment.confidence` değerlerinin en yükseğinden türetiliyor. Düşük güvenli/boş final, `hata` ve ardından `ses-bitti` ile temiz biçimde tamamlanıyor; sözcüğe özel kara liste yok.
- Deterministik `FUSION_LISTEN_TEST_FIXTURE` yolu `silence`, `voiced` ve `low-confidence` sentetik RMS akışlarını gerçek VAD/olay kapısından geçiriyor.
- Windows yardımcı aynı beş alanı her olayda yayınlıyor. Mevcut tanıma davranışı korunurken platformun `Result.Confidence` değeri metin olaylarına ekleniyor; bulunmayan zaman/segment değerleri açık varsayılanlarla gönderiliyor.
- README olay tipleri, örnek JSONL, VAD süreleri ve session sahipliğiyle güncellendi.

## TDD ve RED/GREEN kanıtı

### RED 1 — sessizlik ve sesli olay sözleşmesi

Komut:

```text
.venv/bin/pytest tests/test_runtime_bundle.py -k 'listen_silence or listen_voiced' -q
```

Üretim değişikliğinden önce sonuç: `2 failed`. Her iki sentetik fixture çağrısı da desteklenmeyen bayrak nedeniyle gerçek mikrofon yoluna girip `returncode=-6` ile başarısız oldu. Bu, deterministik fixture/VAD sözleşmesinin bulunmadığını doğruladı.

### RED 2 — düşük güven kapısı

Komut:

```text
.venv/bin/pytest tests/test_runtime_bundle.py -k 'listen_low_confidence' -q
```

Sonuç: `1 failed`; çıktı yalnız `hazir` içerdiği için beklenen `ses-basladi` yoktu. Düşük güvenli sesli fixture davranışı henüz uygulanmamıştı.

### GREEN ve regresyon

Komutlar ve sonuçlar:

```text
.venv/bin/pytest tests/test_runtime_bundle.py -k 'listen_silence or listen_voiced or listen_low_confidence' -q
3 passed

.venv/bin/pytest tests/test_runtime_bundle.py -k 'macos_listen_sigterm' -q
1 passed

.venv/bin/pytest tests/test_runtime_bundle.py -q
20 passed

git diff --check
exit 0
```

Son tam doğrulama da `20 passed` ve exit code `0` verdi.

## Değişen dosyalar

- `desktop_build/listen/main.swift`
- `desktop_build/listen/windows/FusionListen.cs`
- `desktop_build/listen/README.md`
- `tests/test_runtime_bundle.py`
- `.superpowers/sdd/2026-08-31-chatgpt-benzeri-talk/task-1-report.md`

## Öz-inceleme

- Sessizlik fixture'ı `hazir` dışında metin olayı üretmiyor.
- Sesli fixture sırası `hazir → ses-basladi → kismi/son → ses-bitti`; tüm metin olaylarında sayısal güven, süre ve segment var.
- Final kapısı VAD kapandıktan sonra gelen Apple final callback'ini kabul edebilmek için doğrulanmış konuşma süresini koruyor; `ses-bitti` final metinden sonra yayınlanıyor.
- Düşük güvenli final süreçte asılı kalmıyor ve `son` üretmiyor.
- JSON optional alanının Swift `Codable` varsayılanıyla atlanmaması için `encodeNil` açıkça kullanıldı.
- Mevcut on-device zorunluluğu, signal cleanup ve kullanıcıya ait ilgisiz/untracked dosyalar korunuyor.

## Kaygılar

- RMS taban eşikleri (`0.012` başlangıç tabanı, `0.006` bitiş tabanı; gürültü katsayıları `3.0`/`1.8`) deterministik testlerde doğrulandı ancak farklı mikrofon ve oda koşullarında saha kalibrasyonu gerektirebilir.
- Bu makinede `dotnet`, `csc` veya `mcs` bulunmadığından Windows C# yardımcısı yerel olarak derlenemedi; Windows değişikliği mevcut build adapter sözleşmesi ve kaynak incelemesiyle doğrulandı.
