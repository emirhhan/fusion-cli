# Chat görevi — Paket 15: protokol-ve-teshis

Bu chat yalnız aşağıdaki paketi uygulasın. Önceki paketlerin tamamlanmış commitlerini koru. Yeni branch/push/merge yapma; kullanıcı değişikliklerini geri alma. `.env`, cookie veya sır okuma. Repo `/Users/motogate/Desktop/all/01-Projeler/fusion-cli`; Kits gereken paketlerde `/Users/motogate/Desktop/all/01-Projeler/fusion-kits`. Önce CLAUDE.md/RULES.md, bu dosya ve belirtilen ilgili kaynakları oku. Gerçek davranışı incele; iyi mevcut alternatifleri yeniden yazma. Yapılmamış testleri geçmiş sayma. Varsayılan modelleri/bütçeleri tahminle değiştirme.

Tek yürütücüyle ilerle; tüm sohbet geçmişini yeni ajanlara taşıma. Yalnız ilgili kapsam için kısa uzman incelemesi yap. Doğrudan mevcut `.venv/bin/python`, App Node22 `/opt/homebrew/opt/node@22/bin`, Kits Node24 `/Users/motogate/.npm/_npx/538786c08bcb9442/node_modules/node/bin` kullan. `uv run`, toplu bağımlılık sync/update veya rastgele `npx` kurulumu yapma. Yeni bağımlılık gerekiyorsa gerekçesini açıkla. Ağır tam pytest ve `evals.kabul` aynı anda koşmasın; tam App/Kits kapıları da yük kaynaklı süre hatalarını azaltmak için sırayla koşsun. Önce anlamlı hedefli regresyon, sonra son stabil kaynak için gerekli kapı; değişmeyen kaynak için aynı kapıyı tekrar etme. Başarısız koşuları gizleme, eşiği/assertion'ı gevşetme.

Her paketin sonunda Türkçe, küçük yerel commit; gerçek değişiklik/test/atlanan kabul/kalan risk/sonraki interface raporu. Kullanıcı daha sonra adım adım push yapacak. Paket bitince sonraki pakete kendiliğinden geçme.

Kaynak plan: `/Users/motogate/Desktop/all/01-Projeler/fusion-cli/docs/superpowers/plans/2026-10-12-fusion-profesyonel-uygulama.md` içindeki Paket 15 ve Global Constraints.

## Paket şartnamesi

# Paket 15 uygulama şartnamesi

Önceki paket tamamlanıp root tarafından yetki verilmeden ürün edit yok. Kaynak otoritesi task-15-blueprint.md; ana plan Global Constraints ve aşağıdaki bölüm; araştırma raporundaki ilgili kabul sözleşmeleri. Önceki paket raporlarında değişen interface ve deferred bulguları oku.

## Sahiplik ve çalışma sınırı

Blueprint ve aşağıdaki kapsamın dosya/interface sahipliği bu işçiye aittir. Başka ajanlarla aynı repo: onların değişikliklerini geri alma. CLAUDE.md/RULES.md; mevcut branch; Türkçe metinler, typed contracts ve mevcut engine/store otoritesi. Sır/.env okuma, branch/push/merge/commit yok. Root fullgate/commit/review sahibi. .venv doğrudan Python; App Node22; Kits cached Node24.21.0. uv run veya paket yöneticisi sync/install/update yok; gerçekten yeni bağımlılık gerekiyorsa önce gerekçeyi roota bildir. Kendi reviewer/subagent spawn etme.

## Paket 15 — Protokol/dağıtım olgunluğu ve ileri fikirler

**Kapsam:** MCP2026 migration matrix, R34/R36/R39/R40/E34. P2 işlerin hepsi zorunlu ilk yayın değil.

- [ ] Mevcut Python/TS MCP SDK sürümünü lock'tan doğrula; legacy ve yeni stateless adapter için ayrı fixture. Legacy initialize/initialized akışını korur. Yeni 2026-07-28 adapter initialize veya Mcp-Session-Id göndermez; MCP-Protocol-Version, Mcp-Method/Mcp-Name ve _meta taşır; isteğe bağlı server/discover ayrı sınanır. SDK sürümü desteklemiyorsa sürüm-gated experimental adapter/migration gerekir; mevcut istemciye unsupported alan zorla eklenmez.
- [ ] Kaynak/time/observed başarı ve fiyat unknown dataset; routing benchmark. Cost proxy'den gerçek cost'a geçiş tek başına gratuitous default model değişimi yapmaz.
- [ ] Diagnostics export sentinel; recurring restart/delivery duplicate; recorded skill sanitize. Her biri bağımsız küçük paket olarak uygulanır.
- [ ] Yalnız ilgili kapılar ve genişlenen senaryolar. İleri liste kapıları başarısızsa mevcut günlük sürümü kırmadan feature gate/experimental etiketi.


## Teslim

Meaningful TDD RED→GREEN ve hedefli testler: import eksikliği davranış kanıtı değildir, assertion gevşetme/sleep uzatma yok. Mevcut doğru davranışı ölçüp kaydet, yeniden yazma. Beklenmedik failure kök nedenini teşhis et. Rapora exact changed files, commands/results, API/data migration contracts, remaining real/native acceptance ve deferred bulgular yaz. Rapor: task-15-report.md. Full pytest ve evals.kabul root tarafından sıralı; ağır/live koşuyu işçi açmaz. Root yetkili canlı kabul alt görevi ancak ayrı açık mesajla yürür.

## Ayrıntılı kaynak taslağı

`/Users/motogate/Desktop/all/01-Projeler/fusion-cli/docs/superpowers/handoffs/2026-10-13-fusion-paket4-sonrasi/taslaklar/paket-15-kaynak-taslagi.md`. Bu dosya devir paketinde mevcuttur. Bu taslak ilk hazırlık durumudur; önceki paketlerin yeni kod/interface/testleriyle tekrar karşılaştır.

## Tarihsel hazırlık raporu

# Paket 15 — Sınırlı çevrimdışı RED hazırlığı

13 Ekim 2026. Yalnız yeni iki test dosyası ve bu rapor hazırlandı. P14 tamamlanması ve root'un açık ürün yetkisi bekleniyor. Ürün uygulaması, tamamlanmış RED→GREEN düzeltmesi veya Paket 15 kabulü iddiası yok.

## Yeni dosyalar

- `tests/test_task15_diagnostic_sentinels.py`
- `tests/test_task15_recurring_delivery_scope.py`
- `.superpowers/sdd/2026-10-12-fusion-profesyonel-uygulama/task-15-report.md`

CLAUDE.md, RULES.md, plan Global Constraints, task-15-brief/blueprint ve ilgili task-6/task-8 raporları okundu. P6 lifecycle/trust ve P8 checkpoint/effect arayüzleri hâlâ hazırlık kapsamında; onların önerilen yeni sözleşmeleri burada mevcut sayılmadı. P2 donmuş kaynakları, eski testler ve P13 voice işi değiştirilmedi. Commit/branch/push veya alt ajan açma yok.

## Exact komutlar ve sonuçlar

Main `/Users/motogate/Desktop/all/01-Projeler/fusion-cli` kökünde:

```text
.venv/bin/python -m pytest --noconftest -q tests/test_task15_diagnostic_sentinels.py tests/test_task15_recurring_delivery_scope.py
exit 1: .F.FF — 3 FAILED, 2 PASSED

.venv/bin/ruff check tests/test_task15_diagnostic_sentinels.py tests/test_task15_recurring_delivery_scope.py
exit 0: All checks passed!

.venv/bin/ruff format --check tests/test_task15_diagnostic_sentinels.py tests/test_task15_recurring_delivery_scope.py
exit 0: 2 files already formatted

.venv/bin/python -m pytest --noconftest -q tests/test_task15_diagnostic_sentinels.py tests/test_task15_recurring_delivery_scope.py -k 'bearer or json_restart'
exit 0: .. — 2 PASSED, 3 deselected
```

RED gerçek public davranıştan gelir; import/toplama hatası yok. `core.redaction.redact` sentetik multiline PEM'in BEGIN başlığını maskeler fakat gövdedeki sentinel ve END başlığını korur. `schedule_delivery.add_delivery` aynı schedule+due occurrence için `gorev` veya `kok` değiştiğinde ValueError yerine eski teslimi taşıyan yeni item döndürür; item bağlamı ile outbox bağlamı ayrışır. Son byte-preservation assertion bu iki RED örneğinde exception beklentisi kırıldığı için ulaşılmadı; doğrulanmış sayılmaz.

GREEN mevcut davranış: bearer sentinel kaldırılır ve sır olmayan metin korunur. JSON serialize/deserialize restart benzetimi sonrası aynı vade tek occurrence kalır, task_id None olduğu için accepted/completed sonucu uydurulmaz; sonraki farklı vade ayrı teslim ekler. Bu GREEN koşusu ürün düzeltmesi sonrası GREEN değildir, doğru mevcut baseline'dır.

## İzolasyon ve kanıt sınırı

Yalnız sabit sentetik metin/dict ve bellek içi JSON kullanıldı; gerçek kullanıcı teşhis/log/config/env/secrets dosyası veya home verisi toplanmadı. Sentetik yollar disk erişimi yapmaz. Redactor testlerinde builtins.open ve Path.open üzerinden `.env` okuma girişimi AssertionError ile engellenir; iki testte attempts boş kaldığı doğrulandı. Fixture `.env` yaratmaz veya okumaz. Bu guard yalnız bu iki public redactor çağrısının okumasızlığını kanıtlar; henüz olmayan archive exporter'a ait dosya allowlist kabulü değildir.

`--noconftest` ağır ortak fixture'ları devreden çıkardı. Ağ/live/provider/browser/server/subprocess/Chromadb, benchmark, fullgate, uv run, bağımlılık kurulumu ve upgrade yapılmadı. Ruff yalnız iki yeni testte çalıştı. Root tam kalite kapısı ve review sahibidir; bu dosyalar P2 commit/snapshot kapsamına alınmamalı.

## SDK inventory ve protokol ayrımı

Önceden yakalanmış `task-2-current-python-environment.json` içindeki mcp sürümü **1.30.0**. `pyproject.toml` optional aralığı `mcp>=1.9,<2`; Python lock yok. transport docstring'indeki **1.29.1** tarihsel ölçümdür, güncel resolved sürüm değildir. Sibling Kits `package-lock.json` node_modules/@modelcontextprotocol/sdk exact **1.31.0**, resolved URL ve integrity mevcut. Bunlar yerel metadata kanıtıdır; 2026 runtime support kanıtı değildir. Upgrade/lock değişikliği yapılmadı.

Mevcut legacy initialize→initialized/session taşıma sözleşmesi normatif 2025 yoludur. Authorization veya legacy session/version başlıklarının varlığı yeni stateless adapter kusuru diye sınıflandırılmadı. 2026-07-28 stateless adapter ürün yüzeyinde henüz yok; önerilen eksik adapter import edilmedi. Legacy ve yeni yolun fixtures/migration ayrı kalmalı; desteklenmeyen SDK'ya yeni alanlar zorla eklenmemeli. Bu hazırlık yeni protokolü supported ilan etmez.

## Kalan ürün ve gerçek kabul

Birleşik diagnostics exporter/projection/manifest public API'si henüz yok. Public redact sentinel RED bu exporter'ın yerine geçmez. Allowlist, nested key/value, multiline PEM, URL/userinfo/query, path/header/error bytes, destination containment/symlink, bounded event/size, failure redaction, preview/issue URL parity ve App ortam metadata sanitization ayrı kabul gerektirir. Ürün yetkisinde merkezi redaction authority reuse edilmeli; ikinci regex authority açılmamalı.

Recurring scope conflict fail-closed sözleşmesi mevcut add_delivery sınırında hazırlanmıştır; hangi typed error/RPC projection ile sunulacağı ürün aşamasında kesinleştirilmeli. Bellek içi JSON roundtrip gerçek disk restart, atomic durability, iki process, stage/bind/activate crash, lease/stale finish, permission revoke, ack lost veya dış etki exactly-once kanıtı değildir. P2 submission receipts ve P8 OBSERVE_FIRST/effect authority korunmalı; yeni scheduler/outbox veya prompt ledger kopyası kurulmaz.

Protocol experimental acceptance: legacy SDK fake session lifecycle ayrı; stateless no initialize/Mcp-Session-Id, required version/routing header-body consistency, _meta, optional discover, MRTR cancel/late answer, auth/account cache ayrımı ve lost-response no-replay ayrı version-gated fixture gerektirir. SDK API desteği doğrulanmadan gate kapalı/unsupported kalmalı. Native/stdIO/HTTP process, packaged App/Kits bridge ve canlı insan kabulü ayrıca yetki gerektirir. Routing unknown-cost dataset ve recorded skill sanitization da bu bounded teslimde ölçülmedi. P14 tamamlanması ve açık ürün yetkisi gelene kadar burada duruldu.

Hazırlık RED testleri ürün kabulü veya tamamlanma kanıtı değildir. Bu paket çalışma ağacındaki yeni testler yalnız bu pakette etkinleşir; sonraki paketlerin bilinçli RED testlerini bu kapıya katma. Gerçek full-suite kapsamını/exclusion nedenlerini kaydet.

Taşınabilir RED test kaynağı: `red-testleri/paket-15/`. `.txt` uzantısı yanlışlıkla toplanmasını önler; sadece bu pakette ilgili test yoluna aktar. Mevcut aynı dosya varsa önce karşılaştır; üzerine kör yazma.
