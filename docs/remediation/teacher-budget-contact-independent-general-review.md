# Otomatik öğretmen bütçesi ve iletişim bulgusu: bağımsız genel onay

Karar: **APPROVE**. Kapsam yalnız `f023b8a5` üretim kodu,
`ab6502ce` test izolasyonu ve `0ef12118` + `0a6b4344` iletişim düzeltmeleridir.
Çalışma ağacında gelişmekte olan karma araştırma/dosya üretimi değişiklikleri ve
henüz commit edilmemiş ek test düzenlemeleri bu onaya dahil değildir.
İnceleyen üretim kodu değiştirmedi.

## Sabit kaynakla doğrulama

`git archive` ile `f023b8a5` kaynakları, testleri ve `pyproject.toml` ayrı görev
dizinine çıkarıldı. Böylece paylaşılan çalışma ağacındaki yeni değişiklikler
test sonucuna karışmadı. Son tekrarda yalnız
`tests/test_teacher_auto_phase_budget.py`, commit edilmiş `ab6502ce` sürümüyle
değiştirildi; üretim kodunun `f023b8a5` ile bayt eşitliği ayrıca doğrulandı.
İletişim testleri ayrı `0a6b4344` snapshot'ında çalıştı.

## Öğretmen bütçesi

Otomatik plan fazı, yeniden deneme ve JSON biçim onarımı için aynı monoton bitiş
anını kullanıyor. Otomatik son denetimin kendi tek faz bütçesi var. Yetkili tur
bitişi varsa kalan sürenin dörtte biri üst sınır oluyor; sağlayıcının istek
zaman aşımı kalan tur süresi sayılmıyor. Her deneme mevcut öğretmen zaman aşımı
ile fazda kalan sürenin küçüğünü kullanıyor.

Bütçe dolunca geç plan/todo uygulanmıyor; öğretmen bu sebeple küresel olarak
devre dışı bırakılmıyor. Gerçek kullanıcı iptali, sağlayıcının iptali yutması
veya `TimeoutError` sonucuna çevirmesi halinde de temizlik sonrasında yayılıyor.
Bu bir çalışma bütçesi; işbirliği yapmayan temizliğin aynı anda zorla bitmesi
garantisi değil. Mevcut doğrudan/model başlatmalı `ask_teacher` yolu ve istek
zaman aşımı korunuyor. Yeni ayar dosyadan ve programmatik kurulumda pozitif,
sonlu sayı gerektiriyor; sıfır, negatif, Boolean, NaN ve sonsuz değerler reddediliyor.

İlk bağımsız 11 modüllük koşu 205 geçti / 1 başarısız sonucuyla bitti:
yeni test 70 ms bütçenin içine gerçek soğuk proje bağlamı taramasını da alıp her
zaman iki deneme bekliyordu. Dar tekrar geçti; üretim hatası bulunmadı.
`ab6502ce`, zamanlama testinin kapsamı dışındaki bu bağlam üretimini sabitledi.
Aynı 11 modülün yeniden koşusunda **206 test geçti**, çıkış 0.
Önceki başarısız günlük korundu.

Üç bağımsız doğrudan sarmalayıcı testi de geçti: deneme başına zaman aşımının
faz sınırından önce iptal/temizlik yapması, zaten dolmuş fazın hiç araç
başlatmaması ve faz sınırı verilmediğinde mevcut yeniden deneme davranışı.

## Önceki iletişim MEDIUM bulgusunun kapanışı

`064646fc` incelemesindeki iki gerçek tarayıcı RED kontrolü artık geçiyor:
`could not be sent` ve `was not delivered` olumlu teslim iddiası sayılmıyor.
Python incelemesinin `No message was sent/delivered` kontrolleri de geçiyor.
Öznenin ve yüklemin olumsuzluğu ilgili eşleşmeye bağlanıyor; ayrı bir olumlu
teslim iddiası hâlâ engelleniyor. Bu sınırlı dil sezgiseli genel form ya da
gerçek teslim doğrulaması sayılmıyor.

Ayrı sabit snapshot'ta **33 seçili kontrol geçti**: önceki dört bağımsız RED,
olumsuz özne/yüklem, ayrı olumlu iddia, gerçek olumlu zamanlayıcı ve desteklenmeyen
service worker davranışı. Tam taşıma güvenlik düzeneği yeniden koşturulmadı;
incelemede mevcut sınırların korunması da kaynak üzerinden kontrol edildi.

## Kanıt

Günlükler görev çalışma alanında `work/reliability-v2/` altında:

| Günlük | Sonuç | Sonlanmış süreç |
|---|---|---|
| `general-teacher-budget-f023.log` | 205 geçti / 1 zamanlamaya bağlı başarısız | `51991`, çıkış 1 |
| `general-teacher-budget-shared-recheck.log` | 2 geçti | `71610`, çıkış 0 |
| `general-teacher-budget-ab650-green.log` | 206 geçti | `23988`, çıkış 0 |
| `general-teacher-budget-direct.log` | 3 geçti | doğrudan çıkış 0 |
| `general-contact-negative-0a-green.log` | 33 geçti | `51120`, çıkış 0 |

Öğretmen kapsamının üç kaynak dosyası ve yeni testinde Ruff; üç kaynak dosyasında
mypy geçti (`3944`, çıkış 0). İletişim modülünde Ruff ve mypy geçti (`52821`,
çıkış 0). İncelemeye ait çalışan test süreci kalmadı.

Sabit kaynak SHA-256 parmak izleri:

| Dosya | SHA-256 |
|---|---|
| `config/models.py` | `574c7d5c9d890baf89e969c5b780d492b30ac3e75e9731c049b95941fbd2de62` |
| `config/loader.py` | `3644927922d621e4f3185fb4e192fde66d443a4b04a2ac22b1f9b3f7f7808d99` |
| `config/defaults.yaml` | `c3587d97dbe92401f5b2b7657dc2c5e9773efbd4c3734852d0940e1d37d69da4` |
| `engines/agent/teacher_flow.py` | `2aee436337736940baa5a83a7b7e0719f2b3a848e16e822632d30ae962a5e018` |
| `tests/test_teacher_auto_phase_budget.py` (`ab6502ce`) | `8f891eb3cd1f2d1de22d20cd2863f83dd2026c014a39e33958945cbae362a250` |
| `engines/agent/contact_form_probe.py` (`0a6b4344`) | `616e24e364d8a211e6610825dfe322b3073a19774f6e014c8342c2ce83f0494e` |

## Review Summary

| Severity | Count | Status |
|---|---|---|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: **APPROVE** — belirtilen sabit kapsam. Yeni tam model koşusu,
paketleme/kurulum veya ürünün bütünü için kabul iddiası değildir.
