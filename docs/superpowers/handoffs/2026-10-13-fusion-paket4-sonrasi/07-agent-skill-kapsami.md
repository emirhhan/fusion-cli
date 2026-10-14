# Chat görevi — Paket 7: agent-skill-kapsami

Bu chat yalnız aşağıdaki paketi uygulasın. Önceki paketlerin tamamlanmış commitlerini koru. Yeni branch/push/merge yapma; kullanıcı değişikliklerini geri alma. `.env`, cookie veya sır okuma. Repo `/Users/motogate/Desktop/all/01-Projeler/fusion-cli`; Kits gereken paketlerde `/Users/motogate/Desktop/all/01-Projeler/fusion-kits`. Önce CLAUDE.md/RULES.md, bu dosya ve belirtilen ilgili kaynakları oku. Gerçek davranışı incele; iyi mevcut alternatifleri yeniden yazma. Yapılmamış testleri geçmiş sayma. Varsayılan modelleri/bütçeleri tahminle değiştirme.

Tek yürütücüyle ilerle; tüm sohbet geçmişini yeni ajanlara taşıma. Yalnız ilgili kapsam için kısa uzman incelemesi yap. Doğrudan mevcut `.venv/bin/python`, App Node22 `/opt/homebrew/opt/node@22/bin`, Kits Node24 `/Users/motogate/.npm/_npx/538786c08bcb9442/node_modules/node/bin` kullan. `uv run`, toplu bağımlılık sync/update veya rastgele `npx` kurulumu yapma. Yeni bağımlılık gerekiyorsa gerekçesini açıkla. Ağır tam pytest ve `evals.kabul` aynı anda koşmasın; tam App/Kits kapıları da yük kaynaklı süre hatalarını azaltmak için sırayla koşsun. Önce anlamlı hedefli regresyon, sonra son stabil kaynak için gerekli kapı; değişmeyen kaynak için aynı kapıyı tekrar etme. Başarısız koşuları gizleme, eşiği/assertion'ı gevşetme.

Her paketin sonunda Türkçe, küçük yerel commit; gerçek değişiklik/test/atlanan kabul/kalan risk/sonraki interface raporu. Kullanıcı daha sonra adım adım push yapacak. Paket bitince sonraki pakete kendiliğinden geçme.

Kaynak plan: `/Users/motogate/Desktop/all/01-Projeler/fusion-cli/docs/superpowers/plans/2026-10-12-fusion-profesyonel-uygulama.md` içindeki Paket 7 ve Global Constraints.

## Paket şartnamesi

# Paket 7 uygulama şartnamesi

Önceki paket tamamlanıp root tarafından yetki verilmeden ürün edit yok. Kaynak otoritesi task-7-blueprint.md; ana plan Global Constraints ve aşağıdaki bölüm; araştırma raporundaki ilgili kabul sözleşmeleri. Önceki paket raporlarında değişen interface ve deferred bulguları oku.

## Sahiplik ve çalışma sınırı

Blueprint ve aşağıdaki kapsamın dosya/interface sahipliği bu işçiye aittir. Başka ajanlarla aynı repo: onların değişikliklerini geri alma. CLAUDE.md/RULES.md; mevcut branch; Türkçe metinler, typed contracts ve mevcut engine/store otoritesi. Sır/.env okuma, branch/push/merge/commit yok. Root fullgate/commit/review sahibi. .venv doğrudan Python; App Node22; Kits cached Node24.21.0. uv run veya paket yöneticisi sync/install/update yok; gerçekten yeni bağımlılık gerekiyorsa önce gerekçeyi roota bildir. Kendi reviewer/subagent spawn etme.

## Paket 7 — Ajan ekipleri ve skill doğruluğu

**Kapsam:** E09–E14/E23–E26, R19–R21. R22/R23 bu paketin zorunlu kapsamına dahil değil; P2 ayrı teslim. **Dosyalar:** team, capabilities/expertise, existing subagent card/UI and MemoryPanel. **Ürettiği:** scope-normalized child result ve skill origin evidence.

- [ ] A20/A21: alias/symlink scope çakışması, child parent dışına çıkış, bir child exception ve bütçe. Skill collision/unknown tool/hash değişimi testleri.
- [ ] Fail test; root kanonik çözümlerini mevcut path validator üzerinden birleştir; child yalnız parent kapsamını daraltır.
- [ ] Child terminal sonucu exception/cancel durumunda da bir kez; independent sibling korunur, parent cancel hepsini durdurur. Çağrı/doğrulama/süre bütçesi mevcut TurnBudget otoritesine bağlı. Token sayacı henüz yok; provider usage destekli additive sayaç ayrı E12 alt işi. Usage bilinmiyorsa kesin token tavanı garantisi verilmez.
- [ ] Skill katalogunda origin/version, explicit/implicit loading receipt. Remote allowed-tools grant sayılmaz. Tek yüksek güvenli skill otomatik ipucu yaklaşımı korunur.
- [ ] team/capability unit+full gate; UI team fixture. R22/R23 öğretmen açıklaması ve ders invalidation bu pakette uygulanmaz; P2 ayrı küçük görev olarak planlanır.


## Teslim

Meaningful TDD RED→GREEN ve hedefli testler: import eksikliği davranış kanıtı değildir, assertion gevşetme/sleep uzatma yok. Mevcut doğru davranışı ölçüp kaydet, yeniden yazma. Beklenmedik failure kök nedenini teşhis et. Rapora exact changed files, commands/results, API/data migration contracts, remaining real/native acceptance ve deferred bulgular yaz. Rapor: task-7-report.md. Full pytest ve evals.kabul root tarafından sıralı; ağır/live koşuyu işçi açmaz. Root yetkili canlı kabul alt görevi ancak ayrı açık mesajla yürür.

## Ayrıntılı kaynak taslağı

`/Users/motogate/Desktop/all/01-Projeler/fusion-cli/docs/superpowers/handoffs/2026-10-13-fusion-paket4-sonrasi/taslaklar/paket-07-kaynak-taslagi.md`. Bu dosya devir paketinde mevcuttur. Bu taslak ilk hazırlık durumudur; önceki paketlerin yeni kod/interface/testleriyle tekrar karşılaştır.

## Tarihsel hazırlık raporu

# Paket 7 bounded RED hazırlığı

Ürün uygulaması başlamadı. P2 snapshot sırasında NEW-only yetkisiyle toplam iki yeni dosya oluşturuldu; eski test/ürün/config/default dosyası değiştirilmedi. Yeni test P2 gate/commit kapsamına alınmaz. P6complete sonrası root açık uygulama yetkisi bekleniyor.

## Dosyalar

- `tests/test_task7_scope_skill_redprep.py`
- `.superpowers/sdd/2026-10-12-fusion-profesyonel-uygulama/task-7-report.md`

CLAUDE/RULES, ana plan Global Constraints/Paket 7, task-7 brief/blueprint ve önceki paket raporlarının interface/deferred kayıtları incelendi. P1 raporu bu workspace yolunda yok. P5 remote target resolver ve P6 trust/revision/revoke sözleşmeleri henüz ürün uygulaması bekliyor; bu hazırlık onlardan hayali import üretmedi.

## Exact komutlar ve sonuçlar

Repo kökü: `/Users/motogate/Desktop/all/01-Projeler/fusion-cli`.

```sh
.venv/bin/pytest -q tests/test_task7_scope_skill_redprep.py
```

Exit 1: `FFFFF..F.`; **6 FAIL / 3 PASS**, yalnız davranış assertion failure, collection/import error yok.

- `test_task7_canonical_alias_writers_use_separate_waves[src/../target]`: beklenen `[[0], [1]]`, gerçek `[[0, 1]]`.
- `test_task7_canonical_alias_writers_use_separate_waves[alias]`: aynı RED; gerçek symlink tmp_path içinde.
- `test_task7_child_cannot_expand_parent_scope[child_scope0/1/2]`: parent `src/ui`, child sırasıyla `tests`, `src/ui+tests`, `src`; üçünde de beklenen PathAccessError oluşmuyor.
- `test_task7_distinct_skill_contents_keep_distinct_origins`: farklı içerikli aynı ad için beklenen iki katalog kaydı, gerçek bir kayıt ve `claude+proje` etiketi.
- PASS: child parent alanını daraltıyor ve writable_path dış sibling hedefini reddediyor; başladıktan sonra dışarı çevrilen symlink validator tarafından reddediliyor; unknown-only araç empty set, known+unknown known araçları koruyor, boş/* legacy full set.

```sh
.venv/bin/ruff check tests/test_task7_scope_skill_redprep.py
.venv/bin/ruff format --check tests/test_task7_scope_skill_redprep.py
```

İkisi exit 0: `All checks passed!`, `1 file already formatted`. Format mutasyonu gerekmedi.

## Kaynak eşlemesi ve migration sınırı

- `team.py::schedule_waves`: ham Path örtüşmesi canonical alias çakışmasını kaçırıyor. Test absolute tmp_path scope ile root parametresi olmayan mevcut API üzerinden davranışı ölçüyor; relative scope canonical hazırlığı run_team parent context ile uygulama sırasında ayrıca doğrulanacak.
- `team.py::derive_sub_context`: child bildirimi parent write_scope yerine geçiyor; explicit reject eksik. Test yalnız gerçek mevcut ToolContext/SubTask kullanıyor.
- `files.py::writable_path/resolve_path`: dar child hedef enforcement ve dış symlink ret zaten doğru; yeniden yazım için gerekçe yok. `restrict_to_root=False` canonical dönüşü burada ölçülmedi.
- `capabilities.py::CapabilityRegistry.skills/_merge`: farklı içerik kontrol edilmeden bare name üstünde source birleştiriliyor. OfflineRegistry yalnız discovery köklerini tmp_path ile sınırlar; gerçek registry parsing/merge çalışır, kullanıcı kataloğu/kurulu kaynak okunmaz.
- `capabilities.py::map_tools`: boş/* ile unknown-only compatibility davranışı doğru. Unknown diagnostic görünürlüğü ayrı normatif eksik, bu PASS bunu varmış gibi göstermiyor.

API/data migration yapılmadı. Qualified-id, origin-id, version/revision/hash ve ambiguous bare-name çözümü yeni sözleşme gerektirir; yok interface importu RED kanıtı sayılmadı. Mevcut source etiketi origin identity/revision kanıtı değildir.

## Kalan kabul

Child exception/cancel terminali, sibling survival, ortak bütçe/deadline/atomic admission, parent cancel, actual changed_paths ownership; read-only zero write grant ve extra_root/symlink canonical child hazırlığı; skill aynı-içerik birleşimi, qualified seçim, manifest version/hash ayrımı, değişen sayfa revision, explicit/implicit/reference receipt ve Türkçe arama; UI/native team/skill fixture henüz ölçülmedi. Token unknown ayrımı additive E12 işi, R22/R23 ayrı P2 kapsamıdır.

Fullgate, live/native, browser, ChromaDB, dış süreç/ağ, package install/sync, commit/branch/push çalıştırılmadı. Bu rapor Paket 7 tamamlandı iddiası değildir; RED→GREEN ürün aşaması açık root yetkisine bağlıdır.

Hazırlık RED testleri ürün kabulü veya tamamlanma kanıtı değildir. Bu paket çalışma ağacındaki yeni testler yalnız bu pakette etkinleşir; sonraki paketlerin bilinçli RED testlerini bu kapıya katma. Gerçek full-suite kapsamını/exclusion nedenlerini kaydet.

Taşınabilir RED test kaynağı: `red-testleri/paket-07/`. `.txt` uzantısı yanlışlıkla toplanmasını önler; sadece bu pakette ilgili test yoluna aktar. Mevcut aynı dosya varsa önce karşılaştır; üzerine kör yazma.
