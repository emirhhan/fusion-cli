# Task 3 Raporu — Kesilebilir TTS ve gerçek barge-in

## Durum

Tamamlandı. TTS oynatımı artık tur kimliğiyle sahipleniliyor; `VoiceTurnHandle`
iptal ve bitiş yaşam döngüsünü taşıyor. Talk, Fusion konuşurken düşük gecikmeli
VAD oturumunu açık tutuyor. İlk `ses-basladi` ve devamındaki recognition
tamponları TTS iptal onayı gelene kadar korunuyor; onaydan sonra değişmeden
mevcut recognition güven kapısından geçiriliyor.

## RED kanıtı

Üretim değişikliklerinden önce odaklı testlerde şu davranışsal kırılmalar
gözlendi:

- `.venv/bin/pytest tests/test_voice.py tests/test_appserver_session.py -q`
  - 3 failure: `_register_speech_process` `turn_id` kabul etmiyordu;
    `ses.durdur` istenen tur kimliğini dispatch etmiyordu.
- `.venv/bin/pytest tests/test_appserver_session.py -q`
  - 1 failure: `ses.bekle {tur_id}` protokol kolu yoktu.
- `npm test -- voiceTurn.test.ts App.runtime.test.tsx`
  - 3 failure: TTS çağrısı handle döndürmüyor, `cancel()` yok ve başlangıç
    hatası çağırana taşınmıyordu.
- `npm test -- VoiceWindow.test.tsx`
  - 1 failure: konuşma sırasında recognition kapatıldığı için gerçek barge-in
    VAD sözleşmesi sağlanmıyordu.
- `.venv/bin/pytest tests/test_voice.py -q`
  - 1 failure: oynatıcı terminate sonrası 2 saniye bekliyor, 500 ms üst
    sınırını aşıyordu (`expected 0.5, got 2`).
- `npm test -- VoiceWindow.test.tsx`
  - 1 failure: barge-in finali TTS iptal ACK’inden önce kullanıcı mesajı
    olarak kabul ediliyordu.

İlk çıplak `pytest` çağrısı sistem Python’ında `fusion_cli` bulunamadığı için
collection error verdi; özellik RED’i sayılmadı. Kanıtlar repo `.venv` ortamında
yeniden üretildi.

## GREEN uygulaması

- Python TTS sahibi PID yerine UUID `tur_id` ile kayıt tutuyor ve aynı anda
  yalnız bir etkin oynatıcı bırakıyor.
- `ses.konus` tur kimliğini hemen döndürüyor; `ses.bekle {tur_id}` gerçek bitişi
  bekliyor; `ses.durdur {tur_id}` yalnız hedef turu idempotent kesiyor.
- Normal bitiş, hata, iptal ve oturum kapanışı süreç kaydı ile Piper geçici
  dosyasını temizliyor.
- Nazik sonlandırma 500 ms’de tamamlanmazsa oynatıcı zorla kapatılıyor.
- React `VoiceTurnHandle { id, cancel, finished }` üretiyor; iptal sırası
  `ses.durdur ACK → interrupted → listening`.
- Geliştirme build’inde `performance.now()` ile iptal ACK gecikmesi loglanıyor.
- Talk VAD’i TTS sırasında açık tutuyor, barge-in kanalını ana pencereye
  iletiyor ve ilk konuşma tamponlarını ACK gelene kadar saklıyor.
- Tekrarlı `cancel()` aynı promise’i döndürüyor ve ikinci player kill isteği
  üretmiyor.

## GREEN kanıtı

- `cd app && npm test`: **65 dosya, 427 test PASS**
- `.venv/bin/pytest tests/test_voice.py tests/test_appserver_session.py -q`:
  **53 test PASS**
- `cd app && npm run build`: **PASS** (`tsc && vite build`)
- `.venv/bin/ruff check ...`: **PASS**
- `git diff --check`: **PASS**

## Self-review / kaygılar

- Recognition güven eşikleri ve kabul kararı değiştirilmedi; ACK öncesi
  tamponlar aynı state machine’e sonradan yeniden oynatılıyor.
- Vite yalnız mevcut büyük chunk uyarısını veriyor; Task 3 kaynaklı build
  hatası yok.
- Hoparlör yankı benzerliği filtresi Task 1/platform VAD sorumluluğunda;
  bu görev yalnız gerçek `ses-basladi` olayından sonraki sahiplik ve sıralamayı
  uygular.
