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

## Fix Round 1

### Uygulama

- Global `restartAfterRecognitionEnd` boolean'ı kaldırıldı. Belirsiz onay finalinin yeniden başlatma niyeti artık `restartAfterRecognitionEndSession: number | null` ile yalnız kaynak session'a bağlı; sadece aynı session'ın `ended` olayı niyeti tüketebiliyor.
- Session bağlı restart niyeti fresh start, manual stop, TTS başlangıcı ve unmount sınırlarında açıkça temizleniyor. Eski session bitişi yeni session'ın bitiş davranışını değiştiremiyor.
- Recognition sahipliği sunum fazından ayrıldı. `VoiceWindow` gerçek start/stop/end yaşam döngüsünden `recognitionOwned` tutuyor ve `VoiceMode`'a zorunlu `listening` boolean'ı veriyor.
- `VoiceMode` dalga formu, `aria-label`, `aria-pressed` ve mikrofon eylemi görünümünü yalnız açık `listening` prop'undan alıyor. `interrupted` artık kendiliğinden listening sayılmıyor.
- Mevcut çoklu-session testi gerçek native yaşam döngüsünü yansıtacak şekilde her kabul edilen finalden sonra ilgili `recognitionEnded` olayını yayınlıyor.

### Test dosyaları

- `app/src/voice/VoiceWindow.test.tsx`
  - Eski belirsiz onay finali → manual stop/fresh start → eski session end → yeni session end regresyonu.
  - `interrupted` sırasında etkin recognition sahipliğinin “Dinlemeyi durdur” etiketi ve stop eylemiyle tutarlı olması.
- `app/src/voice/VoiceMode.test.tsx`
  - `state="interrupted"`, `listening={false}` birleşiminin “Konuşmaya başla”, `aria-pressed=false` ve doğru toggle callback'i üretmesi.

### RED

Komutlar:

```text
cd app && npm test -- VoiceWindow.test.tsx
cd app && npm test -- VoiceMode.test.tsx
```

Üretim değişikliğinden önceki tam sonuç özetleri:

```text
FAIL  src/voice/VoiceWindow.test.tsx > VoiceWindow — aynı sohbet ve mikrofon yaşam döngüsü > reddedilen final sırasında etkin recognition sahipliğini durdurma eylemiyle gösterir
AssertionError: expected "vi.fn()" to be called once, but got 2 times

FAIL  src/voice/VoiceWindow.test.tsx > VoiceWindow — sesli onay > eski belirsiz onayın yeniden başlatma niyetini yeni oturum sonuna taşımaz
TestingLibraryElementError: Unable to find an element with the text: yeni oturum kapandı.

Test Files  1 failed (1)
Tests       2 failed | 25 passed (27)
exit code 1
```

```text
FAIL  src/voice/VoiceMode.test.tsx > VoiceMode > interrupted sunumunda mikrofon eylemini açık recognition sahipliğinden alır
TestingLibraryElementError: Unable to find an accessible element with the role "button" and name "Konuşmaya başla"

Test Files  1 failed (1)
Tests       1 failed | 9 passed (10)
exit code 1
```

### GREEN ve build

Komut:

```text
cd app && npm test -- VoiceWindow.test.tsx VoiceMode.test.tsx voiceMachine.test.ts windowBridge.test.ts && npm run build
```

Tam sonuç özeti:

```text
Test Files  4 passed (4)
Tests       55 passed (55)

> app@0.1.0 build
> tsc && vite build

✓ 156 modules transformed.
✓ built in 967ms
exit code 0
```

### Öz-inceleme ve kaygılar

- Session eşitlik kontrolü kaldırılırsa yeni lifecycle regresyonu eski niyetin yeni session sonunu tükettiğini yakalar.
- `VoiceMode` tekrar fazdan ownership türetirse `interrupted + listening=false` birim testi yanlış label/ARIA değerini yakalar.
- `VoiceWindow` toggle kararı tekrar fazdan türetilirse interrupted entegrasyon testi ikinci start çağrısını yakalar.
- Start niyeti devam ederken düğme stop olarak kalır; permission reddi/start hatası, manual stop, expected/unexpected end, TTS ve cleanup ownership'i false yapar.
- Build başarılıdır; önceki `500 kB` üstü Vite chunk uyarısı değişmeden sürüyor ve bu fix round kapsamı dışındadır.
