# Task 3 Raporu — Composer, ekler ve eğik çizgi önerileri

## Durum

Tamamlandı. Var olan `App → Composer → useSessions → core` akışı korundu; paralel attachment store veya komut motoru eklenmedi. Composer bağımsız slash düğmesi çizmez, `/` girdisine göre öneri üretir, öneri tıklaması yalnız input'u doldurur ve tam komutta Enter mevcut `runCommand` yolunu çalıştırır.

## Dosyalar

- `app/src/screens/Composer.tsx`
- `app/src/screens/Composer.test.tsx`
- `app/src/App.tsx`
- `app/src/App.test.tsx`
- `.superpowers/sdd/2026-08-30-karakter-sohbet-composer/task-3-report.md`

`Composer.css` mevcut davranış için yeterliydi ve gereksiz görsel değişiklik yapılmadı. Snapshot'lar, `:memory:.ses`, kök `index.html` ve eski pixel varlıkları değiştirilmedi.

## Denetim sonucu

- Önceden çalışan mimari korundu: slash önerileri controlled draft üzerinden, ekler oturum kimliğiyle App state'inde, gönderim `controller.send` üzerinden ilerliyor.
- `history.sources` kaynaklı resume türetimi ve ham resume komut filtresi App testinde gözlemleniyor; olmayan kaynak önerilmiyor.
- MCP satırları artık yalnız katalog kaydı açıkça `etkin: true` ise türetiliyor.
- OS seçici ve Tauri native drop gerçek path'leri aynı ek listesine ekliyor; browser `File` drop ikincil yol olarak mevcut `path/webkitRelativePath/name` sırasını koruyor.
- Bilinmeyen uzantılı proje dosyaları kabul ediliyor. React tarafında Python'ın existence veya 5 MiB inline-image politikası kopyalanmadı.
- Selector reddi, native drop listener kurulumu ve tamamen boş path listesi mevcut `attachmentError` alanında işlem-özel hata gösteriyor.
- IME composition sırasında Enter, Shift+Tab ve diğer textarea shortcut dalları çalışmıyor ve browser varsayılanı engellenmiyor.

## TDD — RED

IME RED komutu:

```text
cd app && npm test -- src/screens/Composer.test.tsx
```

Çıktı (exit 1):

```text
Test Files  1 failed (1)
Tests       2 failed | 15 passed (17)
IME Enter: onSend received "/mcp github"
IME Shift+Tab: onApprovalChange received "plan"
Duration    932ms
```

App boundary RED komutu:

```text
cd app && npm test -- src/App.test.tsx
```

Çıktı (exit 1):

```text
Test Files  1 failed (1)
Tests       3 failed | 19 passed (22)
FAIL: etkinliği eksik "mcp belirsiz" önerisi görünüyordu
FAIL: native drop listener kurulum hatası görünmüyordu
FAIL: boş selector path sonucu görünür hata üretmiyordu
Duration    4.09s
```

Bu App RED'inde selector success/failure, bilinmeyen uzantı, image/file chip, native/browser başarılı drop ve session path iletimi testleri geçti; üç hata yalnız yeni eksik dallardaydı.

## GREEN ve doğrulama

Focused Composer/App GREEN:

```text
cd app && npm test -- src/screens/Composer.test.tsx src/App.test.tsx
Test Files  2 passed (2)
Tests       39 passed (39)
Duration    2.03s
```

Focused session ve build:

```text
cd app && npm test -- src/sessions/useSessions.test.tsx && npm run build
Test Files  1 passed (1)
Tests       6 passed (6)
✓ 140 modules transformed.
✓ built in 602ms
exit 0
```

Core attachment policy odaklı kontrolü:

```text
.venv/bin/python -m pytest -q tests/test_attachment_images.py tests/test_appserver_session.py -k 'attachment or ekleri'
.........                                                                [100%]
exit 0
```

Rust kaynağı değiştirilmedi; bu nedenle genuinely modified Rust focused test yoktu.

İstenen tek full npm çalıştırması:

```text
cd app && npm test
Test Files  53 passed (53)
Tests       288 passed (288)
Duration    9.47s
exit 0
```

Ek kalite kontrolleri:

```text
git diff --check
exit 0
```

## Self-review

- Mutation kontrolü: IME guard kaldırılırsa iki Composer testi; `etkin !== true` gevşetilirse MCP App testi; path filtresi veya listener catch kaldırılırsa ilgili App hata testi kırılır.
- Testler mock varlığını değil gerçek Composer/App çıktısını, draft değerini, görünür chip/error alanını ve transport'a giden gerçek protokol payload'unu gözlüyor.
- Ek path'leri mesaj metnine gömen veya ikinci state deposu oluşturan kod yok.
- Dosya uzantısı allowlist'i yok; `model.weights-custom` testte chip'e ve core payload'una ulaşıyor.
- Diff yalnız Task 3 kaynak/test/rapor dosyalarında; yasaklı untracked dosyalar stage edilmedi.

## Endişeler

Açık engel yok. Browser `File` nesnesi gerçek path sağlamazsa mevcut ikincil `name` fallback'i korunur; core existence doğrulaması bu yolu reddedebilir. Masaüstündeki birincil ve güvenilir akış Tauri native drop gerçek path'idir.

## Fix round 1/5 — Exact komut önceliği

### Important finding ve çözüm

Gerçek registry sırası `/models`, `/model`, `/mode` olduğunda filtre ilk olarak `/models` satırını etkin bırakıyordu. Kullanıcı exact `/model` veya `/mode` yazıp Enter'a bastığında Composer typed komutu çalıştırmadan önce aktif öneriyi `/models` ile değiştiriyordu.

Enter dalı artık autocomplete seçimine bakmadan önce tüm `commands` içinde locale-normalized exact komut adını arar. En az bir exact kayıt destekleniyorsa var olan `send()` yolunu çalıştırır. Exact kayıt yalnız desteklenmeyen satırlardan oluşuyorsa input'u koruyup hiçbir şey çalıştırmaz. Exact eşleşme yoksa önceki Arrow seçimi ve prefix autocomplete akışı aynen devam eder; click-to-fill değiştirilmedi. Bu karşılaştırma `/mcp github` gibi çok sözcüklü adları ve `/resumeclaude` gibi türetilmiş resume adlarını da aynı command-name sözleşmesiyle kapsar.

### RED

Komut:

```text
cd app && npm test -- src/screens/Composer.test.tsx
```

Çıktı (exit 1):

```text
Test Files  1 failed (1)
Tests       3 failed | 17 passed (20)
FAIL: exact /model için onSend çağrısı 0; beklenen ["/model"]
FAIL: exact /mode için onSend çağrısı 0; beklenen ["/mode"]
FAIL: desteklenmeyen /legacy onSend ile 1 kez çalıştırıldı
Duration    987ms
```

Bu RED, hem ilk filtre sonucunun exact komutu ele geçirmesini hem de unsupported exact komutun yanlışlıkla gönderilmesini gerçek `Composer` davranışında yakaladı.

### GREEN

İlk focused GREEN:

```text
cd app && npm test -- src/screens/Composer.test.tsx
Test Files  1 passed (1)
Tests       20 passed (20)
Duration    887ms
exit 0
```

Composer/App focused doğrulama:

```text
cd app && npm test -- src/screens/Composer.test.tsx src/App.test.tsx
Test Files  2 passed (2)
Tests       42 passed (42)
Duration    1.98s
exit 0
```

Tam npm suite:

```text
cd app && npm test
Test Files  53 passed (53)
Tests       291 passed (291)
Duration    9.22s
exit 0
```

Production build:

```text
cd app && npm run build
✓ 140 modules transformed.
✓ built in 591ms
exit 0
```

### Self-review

- Registry order testi literal `/models`, `/model`, `/mode` sırasını kullanır; exact `/model` ve `/mode` için gönderilen payload'u ve `/models` replacement callback'inin oluşmadığını gözler.
- Unsupported exact test disabled satırın Enter ile gönderilmediğini ve input'un değişmediğini gözler.
- Mutation kontrolü: exact kontrolü autocomplete dalının altına taşınırsa iki collision testi; supported filtresi kaldırılırsa unsupported testi kırılır.
- IME guard exact kontrolün önünde kalır. Prefix ve click davranışları mevcut Composer/App testleriyle doğrulanır; ArrowUp/ArrowDown dalları exact Enter kontrolünün önünde ve değişmeden kaldı.
- Yalnız Composer kaynak/testi ve bu rapor değiştirildi; snapshot, asset, `:memory:.ses` ve kök `index.html` değişmedi.

### Endişeler

Açık endişe yok.
