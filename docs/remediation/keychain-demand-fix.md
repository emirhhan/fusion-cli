# E10 — Gereksiz credential erişimini kaldırma

## Kapsam ve kök neden

Mac kilitliyken canlı PID36936 TCP kabul ediyor ama `/status` yanıtlamıyordu. İki saniyelik native sample ana thread'i 180/180 örnekte `asyncio task_step → ctypes → SecItemCopyMatching → SecurityServer::decrypt → mach_msg2_trap` zincirinde gösterdi. Secret veya sohbet içeriği okunup raporlanmadı.

`agent/loop.py` model çağrısı hazırlanırken `web_registry_for(config)` kullanır. Eski helper, yalnız yapılandırılmış web session bulunmasını yeterli sayarak koşulsuz `secret_key()` çağırıyordu. Seçilen API modelinin web session ile eşleşmemesi bile bu I/O'yu önlemiyordu. Factory bütün fallback leaf'lerini önceden kurduğu için kullanılmayan web yedeği de aynı riski taşıyordu.

## Dar düzeltme

- Registry oluşturulurken credential I/O yoktur. Registry kendi memoized store factory'sinin sahibidir; yeni global cache yoktur.
- API eşleşmeme, HTTP `auth_env` ve credentialrefsiz browser yolları Keychain'e hiç erişmez.
- `credential_ref` kullanan browser credential'ı adaptör oluşturulurken değil, gerçek transport kullanılacağı zaman çözülür. Kullanılmayan web fallback Keychain açmaz; gerçekten aktive olan fallback çözer.
- Injected store önceliklidir. Factory exception'ı cache'lenmez. Cookie güncellemeleri sonraki çağrıda okunur; yeni registry/config refresh ve master-key rotasyonu eski global cache'e bağlanmaz.

## Açık sınır

Bu, gözlenen API akışındaki **gereksiz Keychain I/O** düzeltmesidir; bütün Keychain blokajlarını çözmüş sayılmaz. Gerçek credentialref browser erişimi hâlâ senkron olabilir; native credential çağrısı adaptör timeout'u tarafından öldürülmez. Yeni thread, timeout, orphan worker veya auth prompt policy değişikliği eklenmedi. Kullanıcının gerçek credential'ı, izni veya hesabı değiştirilmedi.

## Test ve inceleme

İlk altı regresyon eski kaynakta **6 failed**, düzeltme sonrası **6 passed**. Fallback aktive olma, injected store ve master-key refresh dâhil son dokuz yeni vaka geniş transport setinde çalıştı:

```sh
PYTHONPATH=$PWD/src MYPYPATH=$PWD/src /Users/motogate/Desktop/all/01-Projeler/fusion-cli/.venv/bin/python -m pytest -o addopts='' -q tests/test_web_credentials_on_demand.py tests/test_web_browser.py tests/test_web_control.py tests/test_web_registry.py tests/test_web_session.py tests/test_web_call_context.py
```

Sonuç: **96 passed / 9.35 sn**. Agent-loop/model contract ek seti: **168 passed / 26.84 sn**, mevcut Pydantic uyarısı. Ruff/format temiz; ilgili iki kaynak dosyasında mypy temiz. Gerçek ağ/model/Keychain kullanılmadı; yalnız tmp_path içinde sentetik Fernet kasası kullanıldı.

Genel code review ve bağımsız Python review bu dar kapsam için **APPROVE**. Python kanıtı `e10-python-review.md`; genel reviewer, inactive API/HTTP/fallback yollarında sıfır credential I/O ve genuine browser credential yolunun açık senkron sınırını ayrı doğruladı. Ham test kayıtları `validation/e10-*.txt` dosyalarında.

## E11 salt okunur bulgu

`_run_turn` normal sonucunda sıfır tool çağrısı için `_retry_safe` üretir; `CancelledError` dönüşünde bu alan yoktur. Submission terminal kaydı bu durumda `no_tool_effect` yerine genel cancellation/executor kodu taşır; `SubmissionStore.retry` yalnız `no_tool_effect` veya `before_execution_failed` kabul eder. Bu, araçsız iptalin de retry guard'a takılabileceği somut yoldur. Cancellation sırasında henüz journal'a yazılmamış bir dış etkiyi güvenli ayırmak durable tool-start/effect kanıtı ister; guard gevşetilmedi ve E11 bu dalgada açık bırakıldı. E12 teslim kartı ve masaüstü foreground sorunları bu kapsamda değiştirilmedi.

Build/kurulum yapılmadı; parent yalnız bu dar kaynak deltasını uygular. İlk24 düzeltmeleri ve başka worker'ın E13 değişiklikleri korunmuştur.
