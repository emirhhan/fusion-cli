# Chat görevi — Paket 6: mcp-guven-ve-yasam-dongusu

Bu chat yalnız aşağıdaki paketi uygulasın. Önceki paketlerin tamamlanmış commitlerini koru. Yeni branch/push/merge yapma; kullanıcı değişikliklerini geri alma. `.env`, cookie veya sır okuma. Repo `/Users/motogate/Desktop/all/01-Projeler/fusion-cli`; Kits gereken paketlerde `/Users/motogate/Desktop/all/01-Projeler/fusion-kits`. Önce CLAUDE.md/RULES.md, bu dosya ve belirtilen ilgili kaynakları oku. Gerçek davranışı incele; iyi mevcut alternatifleri yeniden yazma. Yapılmamış testleri geçmiş sayma. Varsayılan modelleri/bütçeleri tahminle değiştirme.

Tek yürütücüyle ilerle; tüm sohbet geçmişini yeni ajanlara taşıma. Yalnız ilgili kapsam için kısa uzman incelemesi yap. Doğrudan mevcut `.venv/bin/python`, App Node22 `/opt/homebrew/opt/node@22/bin`, Kits Node24 `/Users/motogate/.npm/_npx/538786c08bcb9442/node_modules/node/bin` kullan. `uv run`, toplu bağımlılık sync/update veya rastgele `npx` kurulumu yapma. Yeni bağımlılık gerekiyorsa gerekçesini açıkla. Ağır tam pytest ve `evals.kabul` aynı anda koşmasın; tam App/Kits kapıları da yük kaynaklı süre hatalarını azaltmak için sırayla koşsun. Önce anlamlı hedefli regresyon, sonra son stabil kaynak için gerekli kapı; değişmeyen kaynak için aynı kapıyı tekrar etme. Başarısız koşuları gizleme, eşiği/assertion'ı gevşetme.

Her paketin sonunda Türkçe, küçük yerel commit; gerçek değişiklik/test/atlanan kabul/kalan risk/sonraki interface raporu. Kullanıcı daha sonra adım adım push yapacak. Paket bitince sonraki pakete kendiliğinden geçme.

Kaynak plan: `/Users/motogate/Desktop/all/01-Projeler/fusion-cli/docs/superpowers/plans/2026-10-12-fusion-profesyonel-uygulama.md` içindeki Paket 6 ve Global Constraints.

## Paket şartnamesi

# Paket 6 uygulama şartnamesi

Önceki paket tamamlanıp root tarafından yetki verilmeden ürün edit yok. Kaynak otoritesi task-6-blueprint.md; ana plan Global Constraints ve aşağıdaki bölüm; araştırma raporundaki ilgili kabul sözleşmeleri. Önceki paket raporlarında değişen interface ve deferred bulguları oku.

## Sahiplik ve çalışma sınırı

Blueprint ve aşağıdaki kapsamın dosya/interface sahipliği bu işçiye aittir. Başka ajanlarla aynı repo: onların değişikliklerini geri alma. CLAUDE.md/RULES.md; mevcut branch; Türkçe metinler, typed contracts ve mevcut engine/store otoritesi. Sır/.env okuma, branch/push/merge/commit yok. Root fullgate/commit/review sahibi. .venv doğrudan Python; App Node22; Kits cached Node24.21.0. uv run veya paket yöneticisi sync/install/update yok; gerçekten yeni bağımlılık gerekiyorsa önce gerekçeyi roota bildir. Kendi reviewer/subagent spawn etme.

## Paket 6 — MCP dayanıklılığı ve bağlantı merkezi

**Kapsam:** E01–E08, R17/R18/R19. **Dosyalar:** mcp_bridge tool_effect/client/pool/service/oauth/tokens, config trust metadata, connectors/control.

- [ ] A17–A19: annotation conflict, trusted/untrusted read, asılı list/call, refresh yarış, close cancel. Kırmızı testleri gör.
- [ ] Fusion için çelişkide destructive/unknown kararı uygula; bunun daha ihtiyatlı ürün politikası olduğunu dokümante et. Var olan Codex read-first davranışı standardı ihlal ediyor diye iddia etme.
- [ ] D02 yeni sunucuda unreviewed trust ve legacy explicit scope migration uygula. Server bazlı connect/list/call/close bütçesi ve bounded backoff; token single-flight, typed health/provenance metadata; sır loglama yok.
- [ ] UI bağlandı/parked/degraded/auth gerekli ayrımı ve retry. Bir sunucu fail tüm listeyi boşaltmaz.
- [ ] Yerel STDIO+HTTP fixture connect/list/read/cancel/close smoke; unit/full gate. **Yeni MCP sürüm geçişi bu pakette bütün eski handshake'i silmez.** Ayrı protocol matrix işi paket15'tedir.


## Teslim

Meaningful TDD RED→GREEN ve hedefli testler: import eksikliği davranış kanıtı değildir, assertion gevşetme/sleep uzatma yok. Mevcut doğru davranışı ölçüp kaydet, yeniden yazma. Beklenmedik failure kök nedenini teşhis et. Rapora exact changed files, commands/results, API/data migration contracts, remaining real/native acceptance ve deferred bulgular yaz. Rapor: task-6-report.md. Full pytest ve evals.kabul root tarafından sıralı; ağır/live koşuyu işçi açmaz. Root yetkili canlı kabul alt görevi ancak ayrı açık mesajla yürür.

## Ayrıntılı kaynak taslağı

`/Users/motogate/Desktop/all/01-Projeler/fusion-cli/docs/superpowers/handoffs/2026-10-13-fusion-paket4-sonrasi/taslaklar/paket-06-kaynak-taslagi.md`. Bu dosya devir paketinde mevcuttur. Bu taslak ilk hazırlık durumudur; önceki paketlerin yeni kod/interface/testleriyle tekrar karşılaştır.

## Tarihsel hazırlık raporu

# Paket 6 — sınırlı NEW-only RED hazırlığı

Durum: ürün uygulaması başlamadı. P5 tamamlanması ve root'un açık ürün yetkisi bekleniyor. İki yeni test dosyası sınırında duruldu; bu rapor ek teslim kaydıdır.

## Değişen dosyalar

- `tests/test_mcp_trust_contract.py` — annotation çelişkisi ve mevcut ihtiyatlı durumlar.
- `tests/test_mcp_lifecycle_contract.py` — gerçek `McpClient` public enter/list/call/exit yolları; tamamen çevrimdışı SDK session/transport doubles.
- `.superpowers/sdd/2026-10-12-fusion-profesyonel-uygulama/task-6-report.md` — bu kayıt.

Ürün dosyası, eski test, branch ve commit değiştirilmedi. Tam Python kapısı ve snapshot root'a aittir; bu çalışma onları güncellemedi. Başka ajanların dosyaları korunur.

## Gerçek komut ve sonuç

Çalışma dizini: `/Users/motogate/Desktop/all/01-Projeler/fusion-cli`.

```text
.venv/bin/pytest tests/test_mcp_trust_contract.py tests/test_mcp_lifecycle_contract.py -q
exit: 1
7 test: 4 FAILED, 3 PASSED
```

Gerçek assertion RED:

1. `test_conflicting_read_and_destructive_hints_are_destructive`: `readOnlyHint=True, destructiveHint=True` gerçek helper'da `REMOTE_READ` döndürüyor; Fusion ihtiyatlı politika beklenen `REMOTE_DESTRUCTIVE`.
2. `test_hanging_operation_has_its_own_deadline[list]`: keşif dış test emniyet iptaline kadar sonlanmıyor.
3. `test_hanging_operation_has_its_own_deadline[call]`: çağrı dış test emniyet iptaline kadar sonlanmıyor.
4. `test_hanging_operation_has_its_own_deadline[close]`: kapanış dış test emniyet iptaline kadar sonlanmıyor.

Mevcut doğru davranış: annotations yokken read izni verilmez; açık destructive korunur; başarılı public offline istemci çağrısında normalize edilmiş `ok/output` korunur.

Test zamanı 0.01s constructor bütçesi ve 0.1s dış watchdog yalnız çevrimdışı fixture ölçümüdür; ürün için varsayılan değer önermez. Mevcut constructor bu bütçeyi yalnız connect'e uyguluyor. List/call/close için yeni ayrı bütçe sözleşmesi henüz yok; additive config tamamlandığında fixture yeni açık budget alanlarına geçirilmelidir. Hanging doubles Event bekler; sabit sleep yok. Watchdog ürün timeout'u yerine başarı sayılmaz. Dış iptal edilen tüm test task'ları gather ile beklenir ve release sonrası client kapanır.

## Kaynak kanıtı

- `src/fusion_cli/mcp_bridge/tool_effect.py:26–29`: readOnly dalı destructive dalından önce.
- `src/fusion_cli/mcp_bridge/client.py:158–162`: `__aexit__` stack kapanışını deadline olmadan bekliyor.
- Aynı dosya `list_tools:257–282`: SDK her sayfa await'i sınırsız; repeated cursor mevcut guard korunmalı.
- Aynı dosya `call:284–294`: SDK çağrısı deadline olmadan bekleniyor; otomatik retry yok.
- `src/fusion_cli/mcp_bridge/oauth.py::oauth_provider_for`: her factory kendi callback/storage/SDK provider'ını yaratıyor; refresh işlemi repo public API'sinde değil, SDK auth-flow içinde.

## Test edilmeyen sözleşmeler ve kalan işler

Trust state, explicit scoped allow, revision/revoke ve schema fingerprint mevcut public MCP sözleşmesinde yok. P5 onay/scope sözleşmesinin sahipliği P5'te; eksik yeni interface importu RED davranış kanıtı olarak kullanılmadı.

Refresh single-flight/rotating-token race bu teslimde doğrulanmadı. `KeyringTokenStorage.get/set` yarışını sahte refresh diye göstermek gerçek SDK transaction'ını test etmez. Mevcut public factory'de shared owner/coordinator injection yok. Ürün yetkisi geldiğinde SDK resmi public auth-flow extension/reuse yolu ve existing pool/service owner üzerinden transaction sınırı seçilmeli; ardından gerçek SDK auth-flow fake HTTP ile on concurrent waiter/cancel/logout-generation testi kurulmalı. Private SDK monkeypatch veya yeni global singleton eklenmedi.

Partial discovery, total pagination deadline, ambiguity/no-replay, cancellation cleanup owner, fake clock backoff, stale probe merge, UI metadata, gerçek local STDIO/HTTP process/socket reap ve protocol matrix bu iki dosyalık hazırlıkta ölçülmedi. Ağ, subprocess, canlı sunucu, tarayıcı, secrets/.env, package install, full pytest veya ağır fixture çalıştırılmadı. Yeni dosyalarda mevcut ağır bellek autouse temizleyicisi yerel no-op fixture ile gölgelendi.

İzlenen yöntem: mevcut şartname/blueprint ve `superpowers:test-driven-development` test yazma ilkeleri; yalnız RED hazırlığı yetkisi nedeniyle GREEN, tam gate ve reviewer adımları yapılmadı.

## Root isteğiyle yalnız biçim düzeltmesi

`tests/test_mcp_lifecycle_contract.py` içindeki iki `McpServerConfig` constructor'ı ruff ile biçimlendirildi. Davranış değişmedi; ürün/başka test dosyası değiştirilmedi, pytest tekrar çalıştırılmadı.

```text
.venv/bin/ruff format tests/test_mcp_lifecycle_contract.py
exit: 0 — 1 file reformatted
.venv/bin/ruff check tests/test_mcp_lifecycle_contract.py
exit: 0 — All checks passed!
.venv/bin/ruff format --check tests/test_mcp_lifecycle_contract.py
exit: 0 — 1 file already formatted
```

P5 tamamlanması ve açık ürün yetkisi hâlâ bekleniyor.

Hazırlık RED testleri ürün kabulü veya tamamlanma kanıtı değildir. Bu paket çalışma ağacındaki yeni testler yalnız bu pakette etkinleşir; sonraki paketlerin bilinçli RED testlerini bu kapıya katma. Gerçek full-suite kapsamını/exclusion nedenlerini kaydet.

Taşınabilir RED test kaynağı: `red-testleri/paket-06/`. `.txt` uzantısı yanlışlıkla toplanmasını önler; sadece bu pakette ilgili test yoluna aktar. Mevcut aynı dosya varsa önce karşılaştır; üzerine kör yazma.
