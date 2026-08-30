# Konuşma tanıma yardımcısı

`main.swift`, macOS'un **cihaz üstü** konuşma tanıyıcısını (`SFSpeechRecognizer`)
kullanan küçük bir yardımcıdır. Uygulama bunu alt süreç olarak çalıştırır ve
satır başına bir JSON okur:

```
{"tur":"hazir","metin":"tr-TR"}
{"tur":"kismi","metin":"bu projede"}
{"tur":"son","metin":"bu projede neler var"}
```

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
