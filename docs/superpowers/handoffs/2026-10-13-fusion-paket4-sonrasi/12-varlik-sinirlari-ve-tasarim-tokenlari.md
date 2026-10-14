# Chat görevi — Paket 12: varlik-sinirlari-ve-tasarim-tokenlari

Bu chat yalnız aşağıdaki paketi uygulasın. Önceki paketlerin tamamlanmış commitlerini koru. Yeni branch/push/merge yapma; kullanıcı değişikliklerini geri alma. `.env`, cookie veya sır okuma. Repo `/Users/motogate/Desktop/all/01-Projeler/fusion-cli`; Kits gereken paketlerde `/Users/motogate/Desktop/all/01-Projeler/fusion-kits`. Önce CLAUDE.md/RULES.md, bu dosya ve belirtilen ilgili kaynakları oku. Gerçek davranışı incele; iyi mevcut alternatifleri yeniden yazma. Yapılmamış testleri geçmiş sayma. Varsayılan modelleri/bütçeleri tahminle değiştirme.

Tek yürütücüyle ilerle; tüm sohbet geçmişini yeni ajanlara taşıma. Yalnız ilgili kapsam için kısa uzman incelemesi yap. Doğrudan mevcut `.venv/bin/python`, App Node22 `/opt/homebrew/opt/node@22/bin`, Kits Node24 `/Users/motogate/.npm/_npx/538786c08bcb9442/node_modules/node/bin` kullan. `uv run`, toplu bağımlılık sync/update veya rastgele `npx` kurulumu yapma. Yeni bağımlılık gerekiyorsa gerekçesini açıkla. Ağır tam pytest ve `evals.kabul` aynı anda koşmasın; tam App/Kits kapıları da yük kaynaklı süre hatalarını azaltmak için sırayla koşsun. Önce anlamlı hedefli regresyon, sonra son stabil kaynak için gerekli kapı; değişmeyen kaynak için aynı kapıyı tekrar etme. Başarısız koşuları gizleme, eşiği/assertion'ı gevşetme.

Her paketin sonunda Türkçe, küçük yerel commit; gerçek değişiklik/test/atlanan kabul/kalan risk/sonraki interface raporu. Kullanıcı daha sonra adım adım push yapacak. Paket bitince sonraki pakete kendiliğinden geçme.

Kaynak plan: `/Users/motogate/Desktop/all/01-Projeler/fusion-cli/docs/superpowers/plans/2026-10-12-fusion-profesyonel-uygulama.md` içindeki Paket 12 ve Global Constraints.

## Paket şartnamesi

# Paket 12 uygulama şartnamesi

Önceki paket tamamlanıp root tarafından yetki verilmeden ürün edit yok. Kaynak otoritesi task-12-blueprint.md; ana plan Global Constraints ve aşağıdaki bölüm; araştırma raporundaki ilgili kabul sözleşmeleri. Önceki paket raporlarında değişen interface ve deferred bulguları oku.

## Sahiplik ve çalışma sınırı

Blueprint ve aşağıdaki kapsamın dosya/interface sahipliği bu işçiye aittir. Başka ajanlarla aynı repo: onların değişikliklerini geri alma. CLAUDE.md/RULES.md; mevcut branch; Türkçe metinler, typed contracts ve mevcut engine/store otoritesi. Sır/.env okuma, branch/push/merge/commit yok. Root fullgate/commit/review sahibi. .venv doğrudan Python; App Node22; Kits cached Node24.21.0. uv run veya paket yöneticisi sync/install/update yok; gerçekten yeni bağımlılık gerekiyorsa önce gerekçeyi roota bildir. Kendi reviewer/subagent spawn etme.

## Paket 12 — Ortak artefakt köprüsü ve birleşik tasarım

**Kapsam:** K26/K32/K33, R25/R28/R35. **Dosyalar:** core/artifacts, appserver image/library, App library/preview/ui/theme; Kits host api/editor/generated theme scripts. **Önerilen additive interface:** mevcut artefakt tipine `asset_id`, `kind`, `mime`, `relative_path`, `created_by_task_id`, `parent_asset_ids`, `metadata_version`. Boyut/alpha/model/seed yalnız biliniyorsa alan; yoksa null/unknown. Host resolver projenin allowlist kökleriyle path çözümlemeli.

- [ ] Aynı asset chat/gallery/page roundtrip; migration eski path; root escape; missing file; parent deleted; unknown metadata; A34 backward host testleri.
- [ ] Fail test; tek artefact authority; mevcut gallery sidecar ile migration. Galeri index/pagination total order; gerektiğinde corruption recovery scan.
- [ ] Ortak token'lar tek kaynaktan üretilir; shared davranış şartnamesi App/Kits adapter'a taşınır. React major'larını aynı pakete zorla birleştirme.
- [ ] Yeni image comments/compare ayrı küçük UI alt görevi; mask edit unsupported capability açık. Unit/browser/visual; iki repo gate; packaged bridge smoke.


## Teslim

Meaningful TDD RED→GREEN ve hedefli testler: import eksikliği davranış kanıtı değildir, assertion gevşetme/sleep uzatma yok. Mevcut doğru davranışı ölçüp kaydet, yeniden yazma. Beklenmedik failure kök nedenini teşhis et. Rapora exact changed files, commands/results, API/data migration contracts, remaining real/native acceptance ve deferred bulgular yaz. Rapor: task-12-report.md. Full pytest ve evals.kabul root tarafından sıralı; ağır/live koşuyu işçi açmaz. Root yetkili canlı kabul alt görevi ancak ayrı açık mesajla yürür.

## Ayrıntılı kaynak taslağı

`/Users/motogate/Desktop/all/01-Projeler/fusion-cli/docs/superpowers/handoffs/2026-10-13-fusion-paket4-sonrasi/taslaklar/paket-12-kaynak-taslagi.md`. Bu dosya devir paketinde mevcuttur. Bu taslak ilk hazırlık durumudur; önceki paketlerin yeni kod/interface/testleriyle tekrar karşılaştır.

## Tarihsel hazırlık raporu

# Paket 12 — Sınırlı RED hazırlık raporu

Durum: yalnız yeni test hazırlığı tamamlandı. P11 tamamlanması ve root'un açık ürün yetkisi bekleniyor; ürün uygulaması veya paket kabulü yok.

## Yeni dosyalar

- `tests/test_task12_asset_boundaries.py`
- `tests/test_task12_gallery_provenance.py`
- `.superpowers/sdd/2026-10-12-fusion-profesyonel-uygulama/task-12-report.md`

Ürün, eski testler, P2 donmuş kaynakları ve diğer işçilerin dosyaları değiştirilmedi. Bu gelecek paket testleri P2 commit kapsamına alınmamalı. Branch/commit/push, bağımlılık kurulumu, sır veya `.env` okuma yok.

## Komutlar ve sonuçlar

Main repo kökünde çalıştırıldı:

```text
.venv/bin/python -m pytest --noconftest -q tests/test_task12_asset_boundaries.py tests/test_task12_gallery_provenance.py
.venv/bin/ruff check tests/test_task12_asset_boundaries.py tests/test_task12_gallery_provenance.py
.venv/bin/ruff format --check tests/test_task12_asset_boundaries.py tests/test_task12_gallery_provenance.py
```

Son pytest çıkış 1: 11 örnek, 5 PASS, 6 FAIL (`FFF...FFF..`). Ruff çıkış 0: `All checks passed!`; format çıkış 0: `2 files already formatted`. İlk test koşusu galeri/kitaplık dış symlink örneği iki API için ayrılmadan önce 10 örnekte 5 PASS, 5 FAIL gösterdi; son koşu iki public API'yi bağımsız ölçüyor. Import/toplama başarısızlığı yok.

Gerçek davranış RED:

- `library.record_generated` proje dışındaki göreli `..`, mutlak yol ve dış symlink için 0 yerine 1 kayıt döndürüyor. Kanonik çözümleme var fakat proje-kökü containment kontrolü yok.
- `image_flows.list_gallery` ve `library.list_library` galeri dışındaki dosyaya giden symlink'i ayrı ayrı listeliyor. Stat/is_file dış hedefi takip ediyor.
- `image_flows.list_gallery` kopuk `.png` symlink için boş liste yerine sıralama sırasında `FileNotFoundError` yükseltiyor; filtrede dosya varlığı ve stat hata sınırı yok.

Mevcut doğru GREEN baseline:

- `workspace.resolve_workspace_path` göreli kök kaçışını ve dış symlink'i reddediyor.
- Kaydedildikten sonra silinen generated dosya kitaplık görünümünden düşüyor.
- `write_sidecar` → `list_gallery` eski istem/sağlayıcı alanlarını aynen koruyor; sidecar içeriği de doğrulandı.
- Sidecar olmayan görsel için bilinmeyen istem/sağlayıcı boş kalıyor; provenance icat edilmiyor.

Testler yalnız `tmp_path` altında küçük dosyalar oluşturuyor. `.png` uzantılı baytlar listeleme sınırını ölçen örneklerdir; geçerli decode veya görsel üretim kanıtı sayılmaz. Gerçek kullanıcı verisi, HTTP/sağlayıcı, server, browser/native, Chromadb, 10000 galeri benchmark, fullgate ve `uv run` kullanılmadı.

## Sözleşme ve kalan kabul

API/data migration uygulanmadı. Testler mevcut public API'leri çağırıyor; önerilen asset index import'u veya henüz mevcut olmayan interface bir RED gerekçesi değildir. Scope dışı generated kayıtlar atlanmalı; galeri allowlist dışı ve missing symlink yayımlamamalı. Mevcut workspace resolver doğru sınır için reuse adayıdır; library'nin izinli mutlak proje içi yolları eski sözleşmeye göre ayrıca korunmalıdır.

Asset ID, metadata version, namespace/revision, parent tombstone, sidecar/index tek otorite migration, sahip/session izinleri ve typed missing state henüz uygulanmadı. Güncel legacy listede missing kaydın gizlenmesi typed tombstone/lineage kabulü sayılmaz. Corrupt/future schema recovery, aynı asset chat/gallery/Kits page/export roundtrip, A34 backward host capability/cancel/nonce matrix, shared token manifest/generator ve comments/compare kabulü bu hazırlıkta test edilmedi. P11 pagination/draft ayrı işçinin kapsamındadır; P9/P10/P11 interface değişiklikleri ürün yetkisinden sonra yeniden okunmalıdır.

Native kalan kabul: paketlenmiş App/Kits bridge eski/yeni host matrisi, allowlist resolver ile gerçek dosya açma ve MIME/hash/dimension kanıtı, canlı tema değişiminde draft korunması, keyboard/focus ve missing retry. Root tam kalite kapısı ve merkezi review sahibidir; alt ajan açılmadı. Bu rapor ürün uygulamasına geçiş yetkisi vermiyor.

Hazırlık RED testleri ürün kabulü veya tamamlanma kanıtı değildir. Bu paket çalışma ağacındaki yeni testler yalnız bu pakette etkinleşir; sonraki paketlerin bilinçli RED testlerini bu kapıya katma. Gerçek full-suite kapsamını/exclusion nedenlerini kaydet.

Taşınabilir RED test kaynağı: `red-testleri/paket-12/`. `.txt` uzantısı yanlışlıkla toplanmasını önler; sadece bu pakette ilgili test yoluna aktar. Mevcut aynı dosya varsa önce karşılaştır; üzerine kör yazma.
