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

---

## Fix round 1

### Bulgular ve düzeltmeler

1. **Tek 500 ms iptal bütçesi:** `terminate` ve `kill` artık aynı
   `time.monotonic()` deadline'ını paylaşır. İlk bekleme bütçeyi tüketirse
   kill sonrası ikinci bir 500 ms bloklama yapılmaz; çocuk daemon reaper ile
   güvenli biçimde toplanır. Sahiplik kaydı ve geçici dosya temizliği ACK'ten
   önce deterministik tamamlanır.
2. **Gerçek tek-oynatıcı garantisi:** TTS replacement, ayrı bir reentrant
   lifecycle kilidi altında `önce stop → sonra Popen → sonra register` sırasıyla
   serileştirilir. Ardışık ve eşzamanlı `speak()` çağrılarında canlı oynatıcı
   tepe sayısı 1'i aşmaz ve registry'de yalnız son tur kalır.
3. **İptal hatasında fail-closed recovery:** `ses.durdur` hatası runtime
   `error` olarak geldiğinde barge-in tamponları atılır, eski recognition
   oturumu geçersizleştirilip durdurulur ve görünür hata korunur. Kullanıcının
   “Konuşmaya başla” eylemi yeni oturum açar; eski tampon gönderilmez, taze söz
   normal güven kapısından kabul edilir.

### RED kanıtı

- `.venv/bin/pytest tests/test_voice.py -q`: **3 failure**
  - Tek deadline testi iki adet `0.5` bekleme gördü; toplam istenen bloklama
    `1.0 > 0.5` idi.
  - Ardışık replacement testinde ikinci `Popen`, ilk oynatıcı durmadan oluştu;
    `max_live == 2` idi.
  - Eşzamanlı `speak()` testinde iki spawn üst üste bindi;
    `max_live == 2` idi.
- `cd app && npm test -- VoiceWindow.test.tsx voiceTurn.test.ts`:
  **1 failure**
  - İptal hatasından sonra `stopRecognition` hiç çağrılmadı; barge-in pending
    sahipliği ve tamponları wedged kaldı.

### GREEN kanıtı

- `.venv/bin/pytest tests/test_voice.py tests/test_appserver_session.py -q`:
  **56 test PASS**
- `cd app && npm test -- VoiceWindow.test.tsx voiceTurn.test.ts`:
  **2 dosya, 33 test PASS**
- `cd app && npm test`: **65 dosya, 428 test PASS**
- `cd app && npm run build`: **PASS** (`tsc && vite build`)
- `.venv/bin/ruff check src/fusion_cli/appserver/voice.py \
  src/fusion_cli/appserver/session.py tests/test_voice.py \
  tests/test_appserver_session.py`: **PASS**
- `git diff --check`: **PASS**

### Fix round 1 self-review

- Protokol şekli değişmedi; mevcut `ses.durdur {tur_id}` ve `ses.bekle`
  dispatch testleri regresyon kümesinde geçti.
- OS sınırında yalnız `subprocess.Popen` sahteleştirildi; süreç sahipliği,
  replacement kilidi, deadline hesabı, registry ve cleanup gerçek kodla
  çalıştırıldı.
- Recognition kabul eşikleri değiştirilmedi. Hata yolu eski oturumu tamamen
  kapatır; yalnız kullanıcı eylemiyle açılan taze oturum tekrar kabul edebilir.
- Build yalnız daha önce mevcut olan Vite büyük chunk uyarısını verdi.

---

## Fix round 2

### Bulgular ve düzeltmeler

1. **Confirmed-exit sentinel:** 500 ms iptal deadline'ı sonunda kill edilmiş
   oynatıcının çıkışı doğrulanmamışsa süreç ve cleanup artık
   `_REAPING_SPEECH` sahipliğinde kalır. Yeni `speak()` lifecycle kilidi altında
   bu sentinel'i `Popen` öncesi kontrol eder ve
   `{ok: false, mesgul: true, metin: "…yeniden deneyin."}` sonucuyla hızlı
   döner. Reaper `wait()` ile çıkışı doğrulayıp cleanup'ı yaptıktan sonra
   sentinel'i bırakır; sonraki `speak()` ancak bundan sonra spawn edebilir.
2. **Windows kilitli geçici dosya:** Deadline içinde çıkış doğrulanmadığında
   geçici WAV hemen silinmez. Cleanup reaper sahipliğine taşınır ve confirmed
   reap sonrasında çalışır. `PermissionError`/`OSError` stop ACK'ini bozmaz;
   iptal sonucu her durumda başarıyla döner.
3. **500 ms bütçe korundu:** Terminate ve kill hâlâ tek monoton deadline'ın
   kalan bütçesini paylaşır. Sentinel beklemek API çağrısını bloklamaz; yeni
   konuşma hızlı ve eyleme dönük busy sonucu alır.

### RED kanıtı

- `.venv/bin/pytest tests/test_voice.py -q`: **2 failure**
  - Stubborn süreç daemon reaper'da beklerken ikinci `speak()` yanlışlıkla
    `ok:true` döndü ve ikinci `Popen` açtı; beklenen fail-fast busy sahipliği
    yoktu.
  - Windows-benzeri kilitli cleanup, `stop("turn-locked")` içinde doğrudan
    `PermissionError` yükseltti; iptal ACK'i kullanıcıya dönemedi.

İlk RED denemesinde test ekleme konumu eski eşzamanlı test gövdesini bölerek
ek bir `NameError` üretmişti. Bu ürün davranışı RED'i sayılmadı; test dosyası
önce eski yapısına getirildi ve yukarıdaki iki temiz davranışsal failure yeniden
üretildi.

### GREEN kanıtı

- `.venv/bin/pytest tests/test_voice.py tests/test_appserver_session.py -q`:
  **58 test PASS**
- `.venv/bin/pytest -q`: **2697 test, %100 PASS, exit code 0**
- `.venv/bin/ruff check src/fusion_cli/appserver/voice.py \
  src/fusion_cli/appserver/session.py tests/test_voice.py \
  tests/test_appserver_session.py`: **PASS**
- `git diff --check`: **PASS**

### Fix round 2 self-review

- Stubborn süreç testinde terminate ve kill sonrasında `poll()` çıkış
  bildirmedi; reaper serbest bırakılana kadar ikinci `Popen` sayısı 1'de ve
  canlı oynatıcı tepe sayısı 1'de kaldı. Confirmed reap sonrası konuşma başarıyla
  yeniden başladı.
- Locked cleanup testi, reap öncesi `unlink` çağrısında `PermissionError`
  üreten gerçek cleanup davranışını kullandı; stop ACK'i başarılı kaldı ve
  dosya temizliği reap sonrası tamamlandı.
- Protokol ve React arayüzü değişmedi. Fix round 1 cancellation-failure recovery
  testleri tam regresyon içinde geçti; React yeniden çalıştırılmadı.
- Süreç sahipliği, sentinel, deadline ve cleanup gerçek üretim koduyla test
  edildi; yalnız OS oynatıcı oluşturma sınırı `subprocess.Popen` sahteleştirildi.
