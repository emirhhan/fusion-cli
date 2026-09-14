# Platform Dönüşümü Öncesi Başlangıç Durumu

- **Tarih:** 2026-09-14
- **Dal:** `fusion-runtime-hardening-20260827-022831`
- **HEAD:** `20a7d40`
- **Remote farkı:** `origin/fusion-runtime-hardening-20260827-022831` üzerinden 38 commit ileride

## Git Durumu

```
$ git status -sb
## fusion-runtime-hardening-20260827-022831...origin/fusion-runtime-hardening-20260827-022831 [ahead 38]
?? :memory:.ses
?? FUSION_MASTER_PROJE_DOKUMANI.md
?? dagitim/
?? docs/superpowers/plans/2026-09-14-guvenli-baglanti-temeli.md
?? index.html

$ git rev-parse --short HEAD
20a7d40

$ git rev-list --count origin/fusion-runtime-hardening-20260827-022831..HEAD
38
```

İzlenmeyen öğeler (5 adet, brief'te 4 tanesi "izlenmeyen kullanıcı dosyaları" olarak
korunuyor, biri bu görev tarafından commit'e eklenecek plan dosyası):

- `:memory:.ses` — dokunulmaz (RULES/CLAUDE.md kısıtı)
- `FUSION_MASTER_PROJE_DOKUMANI.md` — dokunulmaz
- `dagitim/` — dokunulmaz
- `index.html` — dokunulmaz
- `docs/superpowers/plans/2026-09-14-guvenli-baglanti-temeli.md` — bu commit'e eklendi (plan
  dosyası, "Güvenli Bağlantı Temeli" planının kendisi)

## Kalite Kapıları

### 1. `.venv/bin/ruff check .`

```
All checks passed!
```

### 2. `.venv/bin/mypy`

```
Success: no issues found in 330 source files
```

### 3. `.venv/bin/pytest -q`

Bu ortamda pytest'in `-q` terminal raporlayıcısı çalışma sonunda standart
"N passed, M skipped in X.XXs" özet satırını basmıyor (uyarı özetinden sonra çıktı
kesiliyor; `-p no:warnings` ile de aynı davranış gözlendi, pty altında `script` ile de
doğrulandı). Bu nedenle otoriter sayım için aynı komut `--junit-xml` ile tekrar
çalıştırıldı:

```
$ .venv/bin/pytest -q --junit-xml=/tmp/junit.xml
(çıktı sonu — özet satırı basılmıyor)
$ echo $?
0

$ grep -o '<testsuite[^>]*' /tmp/junit.xml
<testsuite name="pytest" errors="0" failures="0" skipped="4" tests="3820"
time="487.404" timestamp="2026-09-14T03:20:29.768397+03:00" hostname="unknown0e451fb8e944.home">
```

**Sonuç:** 3820 test, 3816 passed, 4 skipped, 0 failed, 0 error — çıkış kodu 0 (yeşil).

### 4. `(cd app && npm test)`

```
> app@0.1.0 test
> vitest run --environment jsdom

 RUN  v4.1.11 /Users/motogate/Desktop/01-Projeler/fusion-cli/app

 Test Files  83 passed (83)
      Tests  605 passed (605)
   Start at  03:28:50
   Duration  15.82s (transform 3.70s, setup 0ms, import 12.14s, tests 34.02s, environment 50.01s)
```

**Sonuç:** 83/83 dosya, 605/605 test geçti — yeşil.

## Kapı Özeti

| Kapı | Sonuç |
|---|---|
| ruff | Yeşil |
| mypy | Yeşil |
| pytest | Yeşil (3816 passed, 4 skipped, 0 failed) |
| frontend (vitest) | Yeşil (605 passed) |

Kırmızı kapı yok; bu görevin commit'i yapılabilir, sonraki fazlar bu rapordaki
sayıları referans alır.

## Codex Oturumunda (13 Eylül) Bulunan, Bu Planın Dışında Kalan Açıklar

- Composer model seçici rol (`agent`, `judge`, adaylar) listeliyor, model listelemiyor
  (`appserver/commands.py::_model_step`, `app/src/screens/ModelPicker.tsx`).
- `config/model_select.py::set_agent_model` eski görev haritasını ve yetenek etiketlerini
  koruyor.
- Web tarayıcı taşıması modeli yok sayıyor
  (`providers/web_browser.py::build_browser_transport`, `del model`).
- `tool_eval_passed` hesap düzeyinde; model/düşünme değişince geçersizleşmiyor.
- `domains.py::adapter_for` üretimde kullanılmıyor; `step_verification.py::verify_plan_acceptance`
  her projede altı Godot kontrolünü doğrudan çağırıyor; `plan_coverage.py` düşman/dövüş
  teslimini global tutuyor.
- `core/artifacts.py::ArtifactStore` sayaç tabanlı ad kullanıyor, ikili artifact/iş devamı yok.
- `appserver/session.py` 1.100+ satır; RULES.md 400 satır sınırını aşıyor.
