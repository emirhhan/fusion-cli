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

## Fix Round 1

### Kapatılan inceleme bulguları

1. macOS `kismi` olayları artık final ile aynı `0.2` güven eşiğini uygular. Düşük güvenli partial metin JSONL'ye çıkmaz.
2. macOS partial callback'i yalnız VAD hâlâ etkinken ve callback'in yakalanan segmenti güncel segmentle aynıyken kabul edilir. `endAudio()` sonrasındaki gecikmiş non-final callback düşürülür; doğrulanmış final kapanıştan sonra alınmaya devam eder.
3. Windows helper `SpeechDetected` ile `ses-basladi` üretir; metni en az 250 ms konuşma ve `0.2` güven ile sınırlar; başarılı, düşük güvenli, kısa veya reddedilmiş konuşmayı `ses-bitti` ile kapatır. Sessizlik metin üretmez.

Önceki “C# yerelde derlenemedi” kaygısı bu turda giderildi: CrossOver paketindeki gerçek Roslyn `csc.exe`, `System.Speech.dll` ve Wine runtime ile `FusionListen.cs` derlenip dört fixture için çalıştırıldı. Test helper'ı Windows CI'da yerel `csc` çalıştırmayı da destekler.

### Kapsayan test dosyaları

- `tests/test_runtime_bundle.py`
  - `test_macos_listen_low_confidence_never_emits_final_transcript`
  - `test_macos_listen_drops_partial_callback_after_speech_ends`
  - `test_windows_listen_enforces_shared_vad_and_confidence_contract` (`silence`, `voiced`, `low-confidence`, `too-short`)
  - mevcut `test_macos_listen_sigterm_runs_cleanup_and_exits_cleanly` regresyonu

### RED

Komut:

```text
.venv/bin/pytest tests/test_runtime_bundle.py -k 'low_confidence or drops_partial or windows_listen_enforces' -q
```

Tam terminal özeti:

```text
FFF
F
FF                                                                   [100%]
FAILED tests/test_runtime_bundle.py::test_macos_listen_low_confidence_never_emits_final_transcript
FAILED tests/test_runtime_bundle.py::test_macos_listen_drops_partial_callback_after_speech_ends
FAILED tests/test_runtime_bundle.py::test_windows_listen_enforces_shared_vad_and_confidence_contract[silence-expected_kinds0]
FAILED tests/test_runtime_bundle.py::test_windows_listen_enforces_shared_vad_and_confidence_contract[voiced-expected_kinds1]
FAILED tests/test_runtime_bundle.py::test_windows_listen_enforces_shared_vad_and_confidence_contract[low-confidence-expected_kinds2]
FAILED tests/test_runtime_bundle.py::test_windows_listen_enforces_shared_vad_and_confidence_contract[too-short-expected_kinds3]
```

macOS assertion çıktıları fixture'ların yalnız `['hazir']` ürettiğini gösterdi. Windows assertion çıktısı dört durumda da fixture işlenmeden recognizer oluşturulduğunu ve şu olayı/exit kodunu gösterdi:

```text
{"tur":"hata","metin":"Bu dil için Windows konuşma tanıyıcısı bulunamadı: tr-TR","guven":null,"speech_ms":0,"segment":0}
assert 2 == 0
```

### GREEN

Odak komutu:

```text
.venv/bin/pytest tests/test_runtime_bundle.py -k 'low_confidence or drops_partial or windows_listen_enforces' -q
```

Tam çıktı:

```text
......                                                                   [100%]
```

Son tam doğrulama komutu:

```text
.venv/bin/pytest tests/test_runtime_bundle.py -q && .venv/bin/pytest tests/test_runtime_bundle.py -k 'macos_listen_sigterm' -q && git diff --check
```

Tam çıktı ve exit code:

```text
.........................                                                [100%]
.                                                                        [100%]
exit code 0
```

### Değişen dosyalar

- `desktop_build/listen/main.swift`
- `desktop_build/listen/windows/FusionListen.cs`
- `desktop_build/listen/README.md`
- `tests/test_runtime_bundle.py`
- `.superpowers/sdd/2026-08-31-chatgpt-benzeri-talk/task-1-report.md`

### Öz-inceleme ve kaygılar

- Düşük güven eşiğini kaldırmak hem macOS low-confidence partial testini hem Windows low-confidence fixture'ını bozar.
- VAD etkinlik kontrolünü kaldırmak macOS delayed-partial testinde ikinci `kismi` olayı üretir.
- Windows süre kapısını kaldırmak `too-short`; güven kapısını kaldırmak `low-confidence`; konuşma olaylarını kaldırmak `voiced` fixture testini bozar.
- Windows gerçek mikrofon davranışı bu macOS ortamında ölçülemedi; ancak aynı üretim karar sınıfını kullanan derlenmiş C# fixture'ları ve gerçek `System.Speech` tip bağları çalıştırıldı.
