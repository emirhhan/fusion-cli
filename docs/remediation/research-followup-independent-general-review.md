# Araştırma/dosya takip düzeltmesi: bağımsız genel inceleme

Sabit kaynak: `9b4b8095914ef3d4b79584156ec6bd0d6832a763`.
Kaynak, testler ve `pyproject.toml` ayrı görev snapshot'ında incelendi.
Üretim kodu değiştirilmedi.

Karar: **WARNING — sağlanan statik güncel rapor örneğinde bir MEDIUM kalıyor**.

## Kapanan bulgular

`058e7be8` genel incelemesindeki ortak olumsuzlama bulgusu kapandı. On bir
İngilizce fiil aynı olumlu/olumsuz sözleşmeye bağlanıyor; önceki üç sınıflandırma
RED'i ve gerçek ajan RED'i geçiyor. Ayrı olumlu ikinci cümlecikler korunuyor.

`93100554` Python incelemesinin doğal `Save ... to weather.html` ve statik
araştırma kavramı kontrolleri de bağımsız koşuda geçti. Kaydetme hedefinin
dosya ve araştırma gereksinimleri birlikte korunuyor; araştırmanın ne anlama
geldiğini açıklayan statik metin tek başına web araştırması zorlamıyor.

## MEDIUM: yeni olumlu test örneğinde kaynak okuması dosyanın yerine geçiyor

Dosya: `src/fusion_cli/engines/effects/detect.py:459`.
İstek: `Create a static report.html containing the latest stable Python version.`

Bu, yeni ürün testindeki **aynı** olumlu örnek
(`tests/test_research_artifact_followup.py:60`). Test yalnız
`requires_web_lookup` değerini kontrol ediyor. Doğrudan dosya eşleştiricisinin
izin verdiği ara sözcükler `static` içermediği için gerçek politika birincil
etkiyi `web_lookup` seçiyor; dosya mutasyonu şartı kayboluyor.

Bağımsız gerçek ajan testinde yalnız başarılı `web_fetch` sonrasında
`outcome.ok=True` döndü ve `report.html` oluşmadı. Böylece dosya oluşturma
isteği yalnız kaynak okuyarak tamamlanmış sayılıyor. Bu genel doğal dil
mükemmelliği talebi değil; değişikliğin kendi olumlu fixture'ındaki birleşik
sözleşmenin eksik sınanması.

Düzeltme: bu sınırlı statik çıktı biçiminde mutasyon önceliğini ve bağımsız
araştırma gereksinimini koru. Mevcut olumlu testte iki yükümlülüğü de sınayıp
yalnız yazma / yalnız okuma / ikisi birlikte gerçek ajan kontrollerini ekle.

## Bağımsız kanıt

- 11 ürün modülü ve önceki iki bağımsız test dosyasında **328 test geçti**;
  süreç `70266`, çıkış 0. Günlük `general-current-9b4b-tests.log`.
- Sağlanan statik örneğin politika ve gerçek ajan kontrolleri **2 başarısız**;
  süreç `55135`, çıkış 1. Dosya `test_general_static_current_artifact.py`,
  günlük `general-current-static-9b-red.log`.
- Ek salt-okuma kontrollerinde `What does the word research mean?` web
  araştırması veya mutasyon istemedi; kavram açıklaması dosyası yalnız mutasyon,
  açık tarihsel araştırma + dosyaya kaydetme her iki yükümlülüğü taşıdı.
- Ruff kaynak ve yeni testte, mypy değişen `detect.py` kaynağında geçti;
  süreç `76415`, çıkış 0.

Günlükler görev çalışma alanında `work/reliability-v2/` altında. Bütün inceleyen
süreçleri sonlandı. İncelenen `detect.py` SHA-256:
`b425325c5c8aa45f3966191aa9a82a92b7ea4878afd440c2379539b33ecb9a58`.

## Review Summary

| Severity | Count | Status |
|---|---|---|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 1 | info |
| LOW | 0 | pass |

Verdict: **WARNING** — sağlanan statik çıktı örneğinde dosya gereksinimi
korunmalı. Tam model/ürün kabulü veya bütün ifade biçimlerinde doğruluk iddia edilmiyor.
