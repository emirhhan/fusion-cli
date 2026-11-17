# D01–D04 uygulama raporu

Çalışma kökü: `/Users/motogate/.codex/worktrees/fusion-deep-fixes/fusion-cli`.
Yeni commit oluşturulmadı. Gerçek model/harici ağ, kullanıcı hesabı, kurulum veya
platform kabulü çalıştırılmadı. Yerel MCP stdio ve mevcut loopback HTTP fikstürü
sırsız/sentetik testlerdir. Bağımsız uzman review controller tarafından yapılacak.

## Madde durumları

- **D01 — Yerel ölçüt kusurları düzeltildi; gerçek OAuth ve uygulama sohbet kabulü açık.**
  `print('ping pong')` eski ölçütü gerçekten geçirdi (ilk kırmızı regresyon).
  Artık aday `async smoke(client)` fonksiyonu gerçek MCP stdio oturumunda
  list_tools ve ping çağrısı yapmalı; harness initialize/list/call sonucunu
  gözlemler. Görev adı `mcp-stdio-listele-cagir`; OAuth iddiası kaldırıldı.
  Büyük dosya 47 bayt yerine 141.359 bayt; TARGET ortada. SHA256 kabulü diğer tüm
  baytların korunmasını şart koşar. Kısaltılmış sahte dosya reddedilir. Setup
  loader mevcut tek executor yoluna normal str mapping verir; `segments` ve
  `repeat/count` deterministik tarifi 1MiB sınırından önce boyutu hesaplar.
  Production YAML 85 satırdır; binlerce satır gömülmez.
  İki JSON düzenlemesi `json-dosya-izolasyonu` olarak adlandırıldı. Gerçek
  uygulama sohbet state'i ve canlı OAuth bu yerel görevlerle kanıtlanmış değildir.
- **D02 — Kanıt sözleşmesi sertleştirildi; zorunlu canlı yayın kapısı açık.**
  Manifest schema 2, canlı rapor yoksa `liveAcceptance.status=not_measured` yazar.
  İsteğe bağlı `--live-acceptance` verilirse commit/paket SHA256, güncel suite
  özeti, tam production görev kümesi, sunulan model kimlikleri, source/config
  kimliği, görev başı çağrı/süre bütçesi, üç başarılı tekrar ve en fazla 48 saat
  yaş aranır. Eski, yanlış paketli, eksik görevli veya ölçülememiş rapor reddedilir.
  `claimsReady=false` her durumda korunur. Standard raporda rate_limited bilgisi
  JSON roundtrip sırasında kayboluyordu; kırmızı testle doğrulanıp düzeltildi.
  Source/scorer digest artık production kabul modülü ve fixture kodunu da kapsar.
  Gerçek canlı koşu ve güvenilir yayın ortamında binding alanı üretimi yapılmadı;
  CI'ya gerçek model çağrısı veya zorunlu kapı eklenmedi. D02 tamamen kapalı değildir.
- **D03 — Headless karar yükü ölçülüyor; gerçek kullanıcı ürün ölçümleri açık.**
  `_EvalApproval` her politika talebini ve aynı araç/argüman/izin/risk talebinin
  tekrarını sayar; argümanların kendisi tutulmaz, SHA256 anahtarı tutulur.
  Runner → Observation → TaskExecution → score/merge → JSON hattında taşınır.
  `mode=headless_policy` sayaçların gerçek UI onayı olmadığını açıklar. Gereksiz
  tekrar, insan onay sayısı, yanıt süresi, müdahale, pending recovery ve restart
  devamlılığı ölçülmedikçe null kalır. Aynı isteğin tekrarı otomatik olarak
  gereksiz sayılmaz. Bunlar hâlâ ayrı canlı ürün kabulü gerektirir.
- **D04 — Açık kabul; kapsam ve belgeler dürüstleştirildi.**
  `release/README.md` dağıtımı geliştirici/önizleme kapsamına sınırlar. Mevcut
  macOS/Windows kurulum, izin/DPI/giriş, notarization, mağaza, telefon, OAuth ve
  dayanıklılık boşlukları korunur. known-gaps'e canlı kalite ve insan ürün ölçümü
  eksikleri eklendi. Bu eksikler yapılmış gibi işaretlenmedi.

## Red/green kanıtı

Tüm testlerde Python:
`/Users/motogate/Desktop/all/01-Projeler/fusion-cli/.venv/bin/python`.
Çalışma kökünde `PYTHONPATH=$PWD:$PWD/src` kullanılır; gerçek kaynak bu worktree'dir.

İlk komut `python -m pytest tests/test_deep_eval_remediation.py -q`: **4 failed**.
- MCP stdout sahte çözümünün returncode=0 gelmesi.
- Büyük fixture'ın yalnız 47 bayt olması.
- `_EvalApproval.interactions` bulunmaması.
- Manifestte `liveAcceptance` bulunmaması.

Sonradan ayrı red/green:
- Canlı rapor doğrulayıcısı yok: AttributeError → valid report kabulü ve stale/
  package/calls/provider/missing_task reddi geçti.
- Rate limit roundtrip kaybı: False is True → taşıma/merge/JSON geçti.
- Setup tarifini str(dict) yapma → sınırlı deterministik metin üretimi geçti.
- Production fixture kaynak özetine girmiyordu: () != () başarısız → fixture
  değişiminde kaynak digest değişmesi geçti.

Son ilgili toplu komut:

```sh
PYTHONPATH=$PWD:$PWD/src /Users/motogate/Desktop/all/01-Projeler/fusion-cli/.venv/bin/python -m pytest -o addopts='' -q tests/test_deep_eval_remediation.py tests/test_production_eval.py tests/test_evals.py tests/test_release_manifest.py tests/test_release_gate_contract.py tests/test_eval_executor.py tests/test_professional_execution_eval.py tests/test_eval_acceptance.py tests/test_eval_profiles.py
```

**162 passed, 1 warning in 45.33s.** Mevcut loopback HTTP MCP testinde SDK
`Use streamable_http_client instead` DeprecationWarning var; bastırılmadı.

```sh
PYTHONPATH=$PWD:$PWD/src /Users/motogate/Desktop/all/01-Projeler/fusion-cli/.venv/bin/python -m pytest -o addopts='' -q tests/test_eval_criteria_sound.py -k production
```

**5 passed, 72 deselected in 1.78s.** Bunlar beş production görevinin elle yazılmış
çözümünü kabul eder; gerçek model başarısı değildir.

## Geniş kontrol sırasında görülen geçici entegrasyon hataları

Yukarıdaki 9 test dosyasına tüm `test_eval_criteria_sound.py` eklenen koşuda
19 araştırma referansı kırıldı. Hepsi yeni provider `model_specs` keyword'unu
eski fake factory'nin kabul etmemesiyle ilgiliydi:
`TypeError: patch_providers.<locals>._build() got an unexpected keyword argument 'model_specs'`
(narration.py:72). Kimlikler:
T08, T20, T24, T28, T32, T01, T05, T06, T13, T14, T21, T22, T26, T29,
T30, T03, T07, T15, T31.

B worker'a doğrudan iletildi; worker tests/fakes.py ve ilgili explicit factory
stub'larını düzelttiğini bildirdi. Bu rapor bunların yeniden tam kontrolünü
geçmiş saymaz; controller bütünleşik yeniden koşuyu yapmalıdır.

İlk scoped mypy çalıştırmasında yalnız PYTHONPATH kullanmak editable install
nedeniyle import-untyped verdi. `MYPYPATH=$PWD/src` ile 9 kaynak dosyası temizdi.
Profiles de eklenince B worker'ın eşzamanlı research_evidence.py:29 dosyasında
iki str|None→str dict-item hatası görüldü; worker düzeltildiğini bildirdi.
Son geniş mypy ve kontrol sonucu ayrıca controller'a iletilir.

## Dosya kapsamı ve kurulum

Değişen modüller: evals agent_runner, execution, executor, loader, metrics,
profiles, report, production suite, oauth fixture. Yeni modüller:
`evals/interactions.py`, `evals/setup_content.py`,
`evals/fixtures/production_acceptance.py`. Ayrıca release_manifest.py,
release scope/policy/gaps, YETENEKLER ve üç ilgili test dosyası.

Yeni bağımlılık yok. Gerçek MCP fixture mevcut opsiyonel `mcp` extra'sını kullanır.
Mevcut uygulama kurulumu değiştirilmedi. Production görev adları değiştiği için
eski sonuçlarla ID bazlı karşılaştırma yapılırken yeni yerel ölçüm kapsamı dikkate
alınmalıdır. Canlı CI kapısı ve gerçek platform/insan kabulleri açık kalır.

Son doğrulama: ilgili 14 Python/test dosyasında `ruff check` temiz;
`ruff format --check` **14 files already formatted**. `MYPYPATH=$PWD/src mypy`
ile interactions, agent_runner, execution, executor, metrics, report,
production_acceptance, setup_content, loader ve profiles: **Success: no issues
found in 10 source files**. Son policy/suite uyumu testi: **1 passed in 0.59s**.
