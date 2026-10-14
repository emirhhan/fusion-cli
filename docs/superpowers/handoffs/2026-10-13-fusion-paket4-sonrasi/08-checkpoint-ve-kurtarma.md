# Chat görevi — Paket 8: checkpoint-ve-kurtarma

Bu chat yalnız aşağıdaki paketi uygulasın. Önceki paketlerin tamamlanmış commitlerini koru. Yeni branch/push/merge yapma; kullanıcı değişikliklerini geri alma. `.env`, cookie veya sır okuma. Repo `/Users/motogate/Desktop/all/01-Projeler/fusion-cli`; Kits gereken paketlerde `/Users/motogate/Desktop/all/01-Projeler/fusion-kits`. Önce CLAUDE.md/RULES.md, bu dosya ve belirtilen ilgili kaynakları oku. Gerçek davranışı incele; iyi mevcut alternatifleri yeniden yazma. Yapılmamış testleri geçmiş sayma. Varsayılan modelleri/bütçeleri tahminle değiştirme.

Tek yürütücüyle ilerle; tüm sohbet geçmişini yeni ajanlara taşıma. Yalnız ilgili kapsam için kısa uzman incelemesi yap. Doğrudan mevcut `.venv/bin/python`, App Node22 `/opt/homebrew/opt/node@22/bin`, Kits Node24 `/Users/motogate/.npm/_npx/538786c08bcb9442/node_modules/node/bin` kullan. `uv run`, toplu bağımlılık sync/update veya rastgele `npx` kurulumu yapma. Yeni bağımlılık gerekiyorsa gerekçesini açıkla. Ağır tam pytest ve `evals.kabul` aynı anda koşmasın; tam App/Kits kapıları da yük kaynaklı süre hatalarını azaltmak için sırayla koşsun. Önce anlamlı hedefli regresyon, sonra son stabil kaynak için gerekli kapı; değişmeyen kaynak için aynı kapıyı tekrar etme. Başarısız koşuları gizleme, eşiği/assertion'ı gevşetme.

Her paketin sonunda Türkçe, küçük yerel commit; gerçek değişiklik/test/atlanan kabul/kalan risk/sonraki interface raporu. Kullanıcı daha sonra adım adım push yapacak. Paket bitince sonraki pakete kendiliğinden geçme.

Kaynak plan: `/Users/motogate/Desktop/all/01-Projeler/fusion-cli/docs/superpowers/plans/2026-10-12-fusion-profesyonel-uygulama.md` içindeki Paket 8 ve Global Constraints.

## Paket şartnamesi

# Paket 8 uygulama şartnamesi

Önceki paket tamamlanıp root tarafından yetki verilmeden ürün edit yok. Kaynak otoritesi task-8-blueprint.md; ana plan Global Constraints ve aşağıdaki bölüm; araştırma raporundaki ilgili kabul sözleşmeleri. Önceki paket raporlarında değişen interface ve deferred bulguları oku.

## Sahiplik ve çalışma sınırı

Blueprint ve aşağıdaki kapsamın dosya/interface sahipliği bu işçiye aittir. Başka ajanlarla aynı repo: onların değişikliklerini geri alma. CLAUDE.md/RULES.md; mevcut branch; Türkçe metinler, typed contracts ve mevcut engine/store otoritesi. Sır/.env okuma, branch/push/merge/commit yok. Root fullgate/commit/review sahibi. .venv doğrudan Python; App Node22; Kits cached Node24.21.0. uv run veya paket yöneticisi sync/install/update yok; gerçekten yeni bağımlılık gerekiyorsa önce gerekçeyi roota bildir. Kendi reviewer/subagent spawn etme.

## Paket 8 — Checkpoint, devam ve gerçek iptal

**Kapsam:** E27–E32, R10/R14. **Dosyalar:** checkpoint_store, core/checkpoint, plan_checkpoint/recovery/liveness, tools/jobs, appserver cancellation. **Tüketir:** paket2/5 kimlik ve izin sonucu.

- [ ] A22–A24: same-job polling, iki plan adı collision, aynı PID parallel save, crash before replace, stale revision, v999, external executed-response-lost.
- [ ] Fail test; unique temp+atomic replace, durability yalnız platformda desteklenen fsync; revision karşılaştırması lock/protokol ile korunur. Eski path migration read gerekir.
- [ ] Resume completed effect'i yeniden çalıştırmadan observation; kaynak değişimi dependent step invalidation. Ham source/prompt checkpoint'e ekleme.
- [ ] Stop gerçek owned process/task temizliğini bekler ve sonucunu UI'ya yollar; bağımsız başka session'a dokunmaz.
- [ ] Checkpoint/recovery/jobs unit+subprocess fixture; full gate; crash/reopen gerçek native smoke paket16'da.


## Teslim

Meaningful TDD RED→GREEN ve hedefli testler: import eksikliği davranış kanıtı değildir, assertion gevşetme/sleep uzatma yok. Mevcut doğru davranışı ölçüp kaydet, yeniden yazma. Beklenmedik failure kök nedenini teşhis et. Rapora exact changed files, commands/results, API/data migration contracts, remaining real/native acceptance ve deferred bulgular yaz. Rapor: task-8-report.md. Full pytest ve evals.kabul root tarafından sıralı; ağır/live koşuyu işçi açmaz. Root yetkili canlı kabul alt görevi ancak ayrı açık mesajla yürür.

## Ayrıntılı kaynak taslağı

`/Users/motogate/Desktop/all/01-Projeler/fusion-cli/docs/superpowers/handoffs/2026-10-13-fusion-paket4-sonrasi/taslaklar/paket-08-kaynak-taslagi.md`. Bu dosya devir paketinde mevcuttur. Bu taslak ilk hazırlık durumudur; önceki paketlerin yeni kod/interface/testleriyle tekrar karşılaştır.

## Tarihsel hazırlık raporu

# Paket 8 — sınırlı RED hazırlığı

13 Ekim 2026. Root P2 gate sırasında yalnız NEW hazırlık için yetki verdi.
Ürün uygulaması başlamadı; P7 tamamlanması ve açık root yetkisi bekleniyor.
Tam iki yeni dosya: `tests/test_task8_checkpoint_contract.py` ve bu rapor.
Mevcut ürün/test dosyaları değiştirilmedi; commit/branch/push yapılmadı.

## Kaynak ve interface eşlemesi

- CLAUDE.md, RULES.md, ana plan Global Constraints/Paket 8, task-8-brief.md,
  task-8-blueprint.md ve task-2-report.md okundu.
- `memory/checkpoint_store.py::JsonCheckpointStore.save/load/find_resumable`
  gerçek public yüzeydir. `save` None döndürür; `load` checkpoint veya None.
  `_path` sanitize ettiği için `a/b` ve `a_b`, ayrıca `.` ve `..` çakışır.
  `_from_dict` dış schema_version alanını okumaz. `save` replace öncesi
  hata durumunda temporary dosyasını finally ile temizler.
- `core/checkpoint.py::WorkflowCheckpoint` storage_revision taşımaz;
  `CheckpointStore.save` expected_revision kabul etmez. CAS için henüz
  testlenebilir public interface yok. Eksik önerilen import yazılmadı;
  interface yokluğu davranış RED kanıtı sayılmadı.
- P2 shared ownership: SubmissionKey profile/root/conversation/request;
  SubmissionReceipt attempt/state; OS owner epoch ve terminal attempt/state CAS
  mevcut otoritedir. Submission dedup tool-effect idempotency garantisi değildir.
  Bu hazırlık P2 interface veya owner uygulamasını değiştirmez.

## Exact komutlar ve sonuçlar

Repo kökünde çalıştırıldı:

```text
.venv/bin/pytest --noconftest -q -o addopts='' tests/test_task8_checkpoint_contract.py
exit 1: 5 failed, 2 passed in 0.18s
.venv/bin/ruff check tests/test_task8_checkpoint_contract.py
exit 0: All checks passed!
.venv/bin/ruff format --check tests/test_task8_checkpoint_contract.py
exit 0: 1 file already formatted
```

- İki identity collision assertion RED: birinci kimlik load edildiğinde ikinci
  checkpoint döner; gerçek save/load çalıştı, import/fixture failure yok.
- Üç dış schema assertion RED: 999, bool True, negatif -1 kayıtları load ile
  geçerli checkpoint kabul edilir. Future/corrupt typed diagnostic henüz yok.
  İlk load assertion kırıldığı için aynı testteki find_resumable/byte-preservation
  assertions bu RED koşusunda ulaşılmadı; bunlar kanıtlanmış diye sunulmuyor.
- Public round-trip + scoped find_resumable GREEN baseline.
- Path.replace noktasındaki kontrollü OSError GREEN: eski checkpoint korunur,
  writer temporary dosyası temizlenir. Gerçek kill/crash, fsync veya concurrency
  kabulü değildir; yalnız rename öncesi fault invariant'ıdır.

## İzolasyon ve kalan kapsam

Yalnız tmp_path diski ve stdlib fixture kullanıldı. `--noconftest` mevcut ortak
autouse fixture'ların Chroma/web/config importlarını devreden çıkardı; pytest
yerleşik tmp_path/monkeypatch fixture'ları kullanıldı. Ağ, browser, subprocess,
Chroma, ağır/full pytest, paket yöneticisi, kurulum, sır/.env ve default değişimi
yok. P7 child/skill/liveness alanına girilmedi.

Storage revision/CAS, unique-temp same-PID threads/processes, typed schema
migration/identity validation, directory fsync/durability uncertainty,
owned process cancellation, OBSERVE_FIRST düşük bütçe ve external lost-response
senaryoları testlenmedi. Profile/conversation scoped checkpoint anahtarı yeni
sözleşmesi de bu legacy plan_id yüzeyinde henüz yok. Yeni observation/effect
receipt interface uydurulmadı. Native crash/reopen kabulü Paket 16 ve root
otoritesinde kalır. Ruff yalnız yeni test dosyasında çalıştı; mypy/full kalite
kapısı ve reviewer entegrasyonu root'a aittir. Bu yeni dosyalar P2 snapshot/commit
kapsamına dahil değildir. İki anlamlı dosya sınırında duruldu.

Hazırlık RED testleri ürün kabulü veya tamamlanma kanıtı değildir. Bu paket çalışma ağacındaki yeni testler yalnız bu pakette etkinleşir; sonraki paketlerin bilinçli RED testlerini bu kapıya katma. Gerçek full-suite kapsamını/exclusion nedenlerini kaydet.

Taşınabilir RED test kaynağı: `red-testleri/paket-08/`. `.txt` uzantısı yanlışlıkla toplanmasını önler; sadece bu pakette ilgili test yoluna aktar. Mevcut aynı dosya varsa önce karşılaştır; üzerine kör yazma.
