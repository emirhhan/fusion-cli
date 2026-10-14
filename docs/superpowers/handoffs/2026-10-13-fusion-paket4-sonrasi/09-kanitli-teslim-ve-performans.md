# Chat görevi — Paket 9: kanitli-teslim-ve-performans

Bu chat yalnız aşağıdaki paketi uygulasın. Önceki paketlerin tamamlanmış commitlerini koru. Yeni branch/push/merge yapma; kullanıcı değişikliklerini geri alma. `.env`, cookie veya sır okuma. Repo `/Users/motogate/Desktop/all/01-Projeler/fusion-cli`; Kits gereken paketlerde `/Users/motogate/Desktop/all/01-Projeler/fusion-kits`. Önce CLAUDE.md/RULES.md, bu dosya ve belirtilen ilgili kaynakları oku. Gerçek davranışı incele; iyi mevcut alternatifleri yeniden yazma. Yapılmamış testleri geçmiş sayma. Varsayılan modelleri/bütçeleri tahminle değiştirme.

Tek yürütücüyle ilerle; tüm sohbet geçmişini yeni ajanlara taşıma. Yalnız ilgili kapsam için kısa uzman incelemesi yap. Doğrudan mevcut `.venv/bin/python`, App Node22 `/opt/homebrew/opt/node@22/bin`, Kits Node24 `/Users/motogate/.npm/_npx/538786c08bcb9442/node_modules/node/bin` kullan. `uv run`, toplu bağımlılık sync/update veya rastgele `npx` kurulumu yapma. Yeni bağımlılık gerekiyorsa gerekçesini açıkla. Ağır tam pytest ve `evals.kabul` aynı anda koşmasın; tam App/Kits kapıları da yük kaynaklı süre hatalarını azaltmak için sırayla koşsun. Önce anlamlı hedefli regresyon, sonra son stabil kaynak için gerekli kapı; değişmeyen kaynak için aynı kapıyı tekrar etme. Başarısız koşuları gizleme, eşiği/assertion'ı gevşetme.

Her paketin sonunda Türkçe, küçük yerel commit; gerçek değişiklik/test/atlanan kabul/kalan risk/sonraki interface raporu. Kullanıcı daha sonra adım adım push yapacak. Paket bitince sonraki pakete kendiliğinden geçme.

Kaynak plan: `/Users/motogate/Desktop/all/01-Projeler/fusion-cli/docs/superpowers/plans/2026-10-12-fusion-profesyonel-uygulama.md` içindeki Paket 9 ve Global Constraints.

## Paket şartnamesi

# Paket 9 uygulama şartnamesi

Önceki paket tamamlanıp root tarafından yetki verilmeden ürün edit yok. Kaynak otoritesi task-9-blueprint.md; ana plan Global Constraints ve aşağıdaki bölüm; araştırma raporundaki ilgili kabul sözleşmeleri. Önceki paket raporlarında değişen interface ve deferred bulguları oku.

## Sahiplik ve çalışma sınırı

Blueprint ve aşağıdaki kapsamın dosya/interface sahipliği bu işçiye aittir. Başka ajanlarla aynı repo: onların değişikliklerini geri alma. CLAUDE.md/RULES.md; mevcut branch; Türkçe metinler, typed contracts ve mevcut engine/store otoritesi. Sır/.env okuma, branch/push/merge/commit yok. Root fullgate/commit/review sahibi. .venv doğrudan Python; App Node22; Kits cached Node24.21.0. uv run veya paket yöneticisi sync/install/update yok; gerçekten yeni bağımlılık gerekiyorsa önce gerekçeyi roota bildir. Kendi reviewer/subagent spawn etme.

## Paket 9 — Kanıtlı kapanış ve çalışma akışı

**Kapsam:** R11–R16/R24, U22/U23/U25, E35. **Dosyalar:** core artifacts/events, existing turn/completion report, Conversation/ActivityLine/PreviewPanel/ChangesPanel; no new agent engine.

- [ ] Wrong-success, NoFileChanges, partial, stale screenshot, duplicate final, future schema ve rejected candidate transcript testleri.
- [ ] Fail test; mevcut runtime `TurnOutcome` ve verifier otoritesiyle teslim kartı. Modelin “bitti” metni status değiştirmez.
- [ ] Teslimde dosya/URL açma, screenshot viewport, source, verification receipt; yukarı okuyan kullanıcı scroll korunur, yeni mesaj düğmesi.
- [ ] Uzun geçmiş performansı ölçülür; mevcut perf test karşılaştırılır. Gerekliyse bounded render; erişilebilirliği bozan kör virtualization yok.
- [ ] Completion/unit/UI+visual/full gates. E35 loop modülerleştirme davranış snapshot'ıyla ayrı alt değişiklik; yeni özellik refactor'a karıştırılmaz.


## Teslim

Meaningful TDD RED→GREEN ve hedefli testler: import eksikliği davranış kanıtı değildir, assertion gevşetme/sleep uzatma yok. Mevcut doğru davranışı ölçüp kaydet, yeniden yazma. Beklenmedik failure kök nedenini teşhis et. Rapora exact changed files, commands/results, API/data migration contracts, remaining real/native acceptance ve deferred bulgular yaz. Rapor: task-9-report.md. Full pytest ve evals.kabul root tarafından sıralı; ağır/live koşuyu işçi açmaz. Root yetkili canlı kabul alt görevi ancak ayrı açık mesajla yürür.

## Ayrıntılı kaynak taslağı

`/Users/motogate/Desktop/all/01-Projeler/fusion-cli/docs/superpowers/handoffs/2026-10-13-fusion-paket4-sonrasi/taslaklar/paket-09-kaynak-taslagi.md`. Bu dosya devir paketinde mevcuttur. Bu taslak ilk hazırlık durumudur; önceki paketlerin yeni kod/interface/testleriyle tekrar karşılaştır.

## Tarihsel hazırlık raporu

# Paket 9 — sınırlı RED hazırlığı

13 Ekim 2026. Ürün uygulaması başlamadı. Paket 8 tamamlanması ve root'un açık uygulama yetkisi bekleniyor. Bu hazırlık mevcut Paket 2 tam kapısının veya commit kapsamının parçası değildir.

## Yeni dosyalar

- `tests/test_task9_completion_evidence_redprep.py`
- `.superpowers/sdd/2026-10-12-fusion-profesyonel-uygulama/task-9-report.md`

Mevcut ürün ve test dosyaları değiştirilmedi. Diğer işçilerin çalışma ağacı korundu.

## Davranış kanıtı

Mevcut public `TurnReport`, `CommandRun`, `evidence_payload`, `VerificationResult`, `TaskExecution` ve `score_task` arayüzleri kullanıldı. Önerilen/yok export import edilmedi. Testler küçük bellek içi kayıtlarla ağsız çalışır; sağlayıcı, sunucu, tarayıcı veya depo başlatmaz.

RED: başarısız toplam doğrulama kapısı ile son mutasyondan sonra geçen tek davranış komutu birlikte verilince payload `engelliyor=True` fakat `dogrulandi=True` üretir. Beklenen `dogrulandi=False` assertion'ı kırılır. Bu, import/collection hatası değil, mevcut public tamamlanma kanıtının çelişkisini gösterir. `TurnReport.is_verified` başarılı komutları değerlendirirken başarısız `gate` sonucunu bu dalda önceliklendirmiyor; `blocks_success` kapıyı doğru biçimde engelliyor.

Mevcut doğru GREEN davranışlar:

- Boş `render()` başarısız gate'in public payload'daki başarı engelini kaldırmıyor.
- Son mutasyondan önceki başarılı test güncel teslimi doğrulamıyor.
- Bilinmeyen çıkış kodu gerekli davranış kanıtı yerine geçmiyor.
- Gerekli dosya değişikliği gözlenmeden tamamlanma iddiası `false_success=True`, `success=False` olarak ölçülüyor.

Ek salt okunur kaynak boşluğu: `loop.py::_apply_turn_report`, boş `report.render()` dalında `outcome.completion_report` atayıp `report.blocks_success` uygulanmadan dönüyor. Bu runtime dalı saf public test kapsamına alınmadı; heavy loop/deps import veya kaynak-metni assertion'ı eklenmedi. Public boş rapor testi yalnız payload otoritesini kanıtlar, runtime `outcome.ok` doğruluğunu kanıtlamaz.

## Exact komutlar ve sonuçları

Repo kökünde:

```sh
.venv/bin/pytest --noconftest -q tests/test_task9_completion_evidence_redprep.py
```

Exit 1; `.F...`, tek davranış assertion'ı başarısız, dört test geçti. Proje varsayılan kısa çıktısı toplam süreyi göstermedi.

```sh
.venv/bin/ruff check tests/test_task9_completion_evidence_redprep.py
.venv/bin/ruff format --check tests/test_task9_completion_evidence_redprep.py
```

İlk lint exit 1: `I001` import grupları arasında boş satır eksikti. İlk format exit 0: dosya zaten biçimli.

```sh
.venv/bin/ruff check --fix tests/test_task9_completion_evidence_redprep.py
.venv/bin/ruff check tests/test_task9_completion_evidence_redprep.py
.venv/bin/ruff format --check tests/test_task9_completion_evidence_redprep.py
.venv/bin/pytest --noconftest -q -o addopts='' tests/test_task9_completion_evidence_redprep.py
```

Sırasıyla exit 0 (bir import düzenleme düzeltildi), exit 0 (`All checks passed!`), exit 0 (`1 file already formatted`), exit 1 (`1 failed, 4 passed in 0.38s`). Son failure `test_failed_gate_never_projects_verified_delivery_despite_successful_command`: `True is False`.

## Sınırlar ve sonraki yetkili aşama

API/veri migration yok. Yeni receipt/schema tasarlanmadı. Model yanlış beyanı, runtime boş rapor engeli, partial/remote effect, screenshot freshness, accepted/rejected candidate, duplicate/future schema, correlated App projection, scroll, gerçek artifact opening ve context-source metadata tam kabulü sonraki uygulama aşamasında ele alınmalı. Bu beş küçük fixture bütün Paket 9 kabulü değildir.

Performans/render benchmark, 10k fixture, full pytest, evals.kabul, browser/live/server/Chromadb, paket kurulumu, uv, secret/.env okuma, branch/commit/push ve alt ajan çalıştırılmadı. Ruff yalnız yeni Python dosyasını kontrol etti. Root review ve sonraki tam kapı bu raporla geçilmiş sayılmaz. RED kasıtlı olarak açık bırakıldı; ürün düzeltmesi yapılmadı.

Hazırlık RED testleri ürün kabulü veya tamamlanma kanıtı değildir. Bu paket çalışma ağacındaki yeni testler yalnız bu pakette etkinleşir; sonraki paketlerin bilinçli RED testlerini bu kapıya katma. Gerçek full-suite kapsamını/exclusion nedenlerini kaydet.

Taşınabilir RED test kaynağı: `red-testleri/paket-09/`. `.txt` uzantısı yanlışlıkla toplanmasını önler; sadece bu pakette ilgili test yoluna aktar. Mevcut aynı dosya varsa önce karşılaştır; üzerine kör yazma.
