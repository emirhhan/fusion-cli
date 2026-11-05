# Sıfatlı dosya nesnesi: bağımsız genel kod incelemesi

Sabit kaynak: `b9267d240c951937400da9597659d31a79109009`.
Kaynak, testler ve `pyproject.toml` ayrı snapshot'ta incelendi; üretim kodu
değiştirilmedi. Karar: **WARNING — bir yeni MEDIUM sınır regresyonu**.

## Önceki bulgular kapandı

Statik güncel raporun dosya gereksinimi (`d578c87c`) artık korunuyor. Eski
statik rapor, olumsuz dosya eylemi, doğal kaydetme hedefi ve araştırma kavramı
RED kontrolleri bağımsız koşuda geçti. Ortak olumlu rapor yardımcısı yalnız
araştırmayı değil mutasyonu ve her iki tek taraflı kanıtın reddini de sınayarak
önceki test açığını kapatıyor. Sıfatlı dört rapor biçiminde gerçek ajan
kontrolleri yalnız okuma/yazmayı reddedip ikisini birlikte kabul ediyor.

## MEDIUM: son dosya adayı, korunması amaçlanan edat sınırını aşabiliyor

Dosya: `src/fusion_cli/engines/effects/detect.py:460`–`:465`.
`_EN_FILE_OBJECT`, edatları yalnız isteğe bağlı sıfatları tüketirken durduruyor.
Son `_FILENAME` adayı ise eski uyumluluk için boşluğu nokta kabul ediyor.
Böylece `about html`, `of html` veya `using html` son dosya adayı olarak
eşleşiyor; edat kontrolü bu konumda uygulanmıyor.

Gerçek sonuçlar:

| İstek | Önceki sabit `9b4b8095` | `b9267d24` |
|---|---|---|
| `Create a summary about HTML.` | etki yok | `workspace_mutation` |
| `Create a short explanation of HTML.` | etki yok | `workspace_mutation` |
| `Create a short guide using HTML.` | etki yok | `workspace_mutation` |

İlk isteğin gerçek ajan yeniden üretimi de `ok=False` ile dosya değiştirme
kanıtı istiyor; hiçbir dosya değişmemiş durumda. Burada kullanıcı bir dosya adı
vermedi; yeni gramer konu/girdi sınırını dosya nesnesi sanıyor. Bu, sınırsız
doğal dil kapsama talebi değil, eklenen ortak sınır kuralının son adayda
uygulanmaması.

Düzeltme: dosya adayının başlangıcında da konu/girdi sınırını koru; kasıtlı
`report.html` ve eski `index html` dosya biçimlerini bozma. Bağımsız bu iki
olumlu kontrol mevcut kaynakta geçiyor ve korunmalı.

## Bağımsız doğrulama

- 12 ürün modülü ve önceki üç bağımsız dosyada **352 test geçti**; süreç
  `6567`, çıkış 0. Günlük `general-current-b926-tests.log`.
- Yeni üç sınır politikası ve gerçek ajan kontrolü **4 başarısız**; iki dosya
  biçimi kontrolü geçti. Süreç `54255`, çıkış 1. Dosya
  `test_general_filename_boundary.py`; günlük `general-filename-boundary-b926-red.log`.
- Değişen kaynak ve testlerde Ruff, `detect.py` üzerinde mypy geçti;
  süreç `50741`, çıkış 0.

Günlükler görev çalışma alanında `work/reliability-v2/` altında. İncelemeye ait
çalışan süreç kalmadı. Bu inceleme yeni model/kurulum/ürün kabulü iddia etmiyor.

## Review Summary

| Severity | Count | Status |
|---|---|---|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 1 | info |
| LOW | 0 | pass |

Verdict: **WARNING** — son dosya adayında edat sınırı korunmalı.
