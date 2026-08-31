# Task 2 Raporu — React Talk koordinatörü ve güvenilir tur sonlandırma

## Uygulama

- `RecognitionEvent` beş alanlı Task 1 sözleşmesiyle React reducer katmanına taşındı; `hazir`, `ses-basladi`, `kismi`, `son`, `ses-bitti` ve `hata` olayları ayrı işleniyor.
- Saf `evaluateRecognitionTurn` kapısı eklendi. Aktif session, aday revizyonu, en az `250 ms` konuşma, en az `0.2` güven ve metin kararlılığını birlikte denetliyor.
- Güvenilir native `son`, tek sözcükte de kabul ediliyor. `1_400 ms` kısmi zaman aşımı yalnız aynı session/revizyondaki, güvenilir ve en az iki sözcüklü kararlı adayı kabul ediyor; zamanlayıcı kapıyı atlayamıyor.
- Her yeni dinleme öncesinde önceki session pasifleştiriliyor, aday/transkript/zamanlayıcı temizleniyor ve varsa eski native süreç seri kuyrukta durdurulmadan yenisi başlatılmıyor.
- React görünür transkripti ve gönderimi yalnız aktif session olaylarından güncelliyor. Aynı session'ın ikinci finali ve eski session/timer olayları etkisiz.
- Sessizlik boş transkriptle `listening` durumunda kalıyor. Sesli fakat süre/güven kapısından geçmeyen final mesaj göndermeden `interrupted` durumunda “Anlayamadım, tekrar söyle” gösteriyor.
- `calibrating`, `hearing` ve `interrupted` aşamaları Talk görünümüne bağlandı.
- Native başlangıç köprüsü Rust'ın döndürdüğü gerçek session numarasını `Promise<number>` olarak koruyor.

## RED kanıtı

İlk reducer ve entegrasyon testlerinden sonra çalıştırılan komut:

```text
cd app && npm test -- voiceMachine.test.ts VoiceWindow.test.tsx
```

Sonuç: exit code `1`; `12 failed, 24 passed`. Saf kapı ve yeni reducer olayları bulunmadığı için 11 reducer testi başarısızdı. Entegrasyon regresyonu mevcut `1_400 ms` zaman aşımının `guven: 0.08`, `speech_ms: 0` olan “Evet” kısmisini gerçekten `emitMessage` ile gönderdiğini gösterdi.

Öz-incelemede eklenen sessiz tur sınır testi üretim düzeltmesinden önce ayrıca çalıştırıldı:

```text
cd app && npm test -- voiceMachine.test.ts
```

Sonuç: exit code `1`; `1 failed, 11 passed`. `ses-bitti` olayı beklenen `listening` yerine `calibrating` bırakıyordu.

Köprünün Rust session numarasını kaybetmemesi için sonuç sözleşmesi de eski `void` uygulamaya karşı doğrulandı:

```text
cd app && npm test -- windowBridge.test.ts
```

Sonuç: exit code `1`; `1 failed, 5 passed`. `tanima_baslat` sonucu `42` iken köprü `undefined` döndürüyordu.

## GREEN ve build kanıtı

Son taze doğrulama:

```text
cd app && npm test -- voiceMachine.test.ts VoiceWindow.test.tsx windowBridge.test.ts && npm run build
```

Sonuç: exit code `0`; `3 passed` test dosyası, `43 passed` test ve başarılı `tsc && vite build` (`156 modules transformed`).

## Değişen dosyalar

- `app/src/voice/voiceMachine.ts`
- `app/src/voice/voiceMachine.test.ts`
- `app/src/voice/VoiceWindow.tsx`
- `app/src/voice/VoiceWindow.test.tsx`
- `app/src/voice/windowBridge.ts`
- `app/src/voice/windowBridge.test.ts`
- `app/src/voice/VoiceMode.tsx` — yeni `VoicePhase` değerlerinin görünür durum ve avatar eşlemesi için zorunlu tüketici güncellemesi
- `.superpowers/sdd/2026-08-31-chatgpt-benzeri-talk/task-2-report.md`

## Öz-inceleme

- Güven veya süre karşılaştırmasını kaldırmak düşük güvenli “Evet” reducer ve entegrasyon regresyonlarını bozar.
- Session kontrolünü kaldırmak eski session testi; aday revizyonunu kaldırmak eski timer testi; finalize kilidini kaldırmak yinelenen final testi tarafından yakalanır.
- Kısmi zaman aşımının tek sözcük kararlılık koşulunu kaldırmak mevcut “Evet” semptomunu yeniden üretir; güvenilir tek sözcüklü gerçek final ayrı testle korunur.
- `startListening` eski session'ı olay kabulünden önce kapatıyor ve stop/start işlemlerini aynı promise kuyruğunda sıralıyor. Bekleyen permission/start niyetleri mevcut intent sayacıyla iptal ediliyor.
- Hızlı native çıktı, start tokenı gelmeden gelen olay kuyruğu, TTS sırasındaki gecikmiş stop ve sesli onay fail-closed regresyonları odak entegrasyon paketinde yeşil kaldı.
- Eski `PARTIAL`/`FINAL` reducer girişleri kaldırıldı; React içinden kabul kapısını atlayan ikinci bir sonlandırma yolu kalmadı.
- İlgisiz untracked dosyalar değiştirilmedi ve commit kapsamına alınmayacak.

## Kaygılar

- Vite build başarılı olmakla birlikte mevcut `500 kB` üstü chunk uyarısını vermeye devam ediyor; bu Task 2 davranışıyla ilgili değil.
- Zaman aşımındaki kısmi tek sözcükler bilinçli olarak bekletiliyor; yardımcı güvenilir `son` üretirse tek sözcük kabul ediliyor. Bu güvenlik/erken-sonlandırma dengesi saha konuşma örnekleriyle izlenmeli.
