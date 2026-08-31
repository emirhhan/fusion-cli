# Konuşma tanıma yardımcısı

`main.swift`, macOS'un **cihaz üstü** konuşma tanıyıcısını (`SFSpeechRecognizer`)
kullanan küçük bir yardımcıdır. `windows/FusionListen.cs` aynı sözleşmeyi
Windows Speech Recognition ile sağlar. Uygulama adaptörü alt süreç olarak
çalıştırır ve satır başına bir JSON okur:

```
{"tur":"hazir","metin":"tr-TR","guven":null,"speech_ms":0,"segment":0}
{"tur":"ses-basladi","metin":"","guven":null,"speech_ms":80,"segment":1}
{"tur":"kismi","metin":"bu projede","guven":0.74,"speech_ms":310,"segment":1}
{"tur":"son","metin":"bu projede neler var","guven":0.89,"speech_ms":920,"segment":1}
{"tur":"ses-bitti","metin":"","guven":null,"speech_ms":920,"segment":1}
```

Olay türleri `hazir`, `ses-basladi`, `kismi`, `son`, `ses-bitti` ve `hata`dır.
Her olay beş alanı da taşır; platformda bulunmayan güven değeri `null` yazılır.
Oturum kimliği yardımcı tarafından üretilmez, süreç düzeyindeki oturumun sahibi Rust'tır.
macOS yardımcısı ilk 300 ms'de ortam gürültüsünü ölçer, RMS tabanlı başlangıç/bitiş
histerezisi uygular ve 250 ms'den kısa ses aralıklarında final metin yayınlamaz.
Windows yardımcısı `SpeechDetected` ile aynı başlangıç/bitiş olaylarını bağlar; kısmi
ve final metinleri en az 250 ms konuşma ve `0.2` güven eşiğiyle sınırlar.

## Neden Swift, neden Rust değil

`objc2-speech` ile aynı işi Rust'tan yapmak mümkün ama `SFSpeechRecognizer` +
`AVAudioEngine` + delege geri çağrıları epey `unsafe` köprü kodu gerektiriyor ve
mikrofon yolu otomatik sınanamıyor. 62 KB'lık bu yardımcı aynı işi, okunabilir
ve tek dosyada yapıyor.

## Ölçülen kısıtlar

- **Türkçe cihaz üstü tanıma destekleniyor.** Ölçüm: 63 yerel ayar,
  `tr-TR` var, `supportsOnDeviceRecognition = true`. Ağ ve indirme gerekmez.
- **Siri sesleri/tanıyıcısı üçüncü taraf uygulamalara KAPALI.** Ölçüm:
  uygulamalara açılan 181 sesin sıfırı Siri.
- **`Info.plist` açıklamaları ZORUNLU.** Onlarsız izin penceresi hiç açılmıyor
  ve `authorizationStatus()` `notDetermined` olarak kalıyor — hata da vermiyor.
  Açıklamalar `app/src-tauri/Info.plist` içindedir.

## Derleme

```bash
swiftc -O -o fusion-listen desktop_build/listen/main.swift
```

CI'daki macOS koşucularında Swift zaten kuruludur.

Paket scripti platforma göre doğru resource adını zorunlu kılar:

```bash
python desktop_build/listen/build_adapter.py --platform macos \
  --output app/src-tauri/resources/fusion-listen
```

Windows karşılığı `fusion-listen.exe` üretir. Derleyici bulunamazsa, derleme
non-zero dönerse veya beklenen çıktı oluşmazsa paketleme sessizce devam etmez.

macOS helper `SIGTERM` ve `SIGINT` aldığında recognition task'i iptal eder,
audio request'i kapatır, çalışan motoru durdurur ve mikrofon tap'ini kaldırır.
