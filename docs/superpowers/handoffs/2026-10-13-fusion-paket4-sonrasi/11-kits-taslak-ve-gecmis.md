# Chat görevi — Paket 11: kits-taslak-ve-gecmis

Bu chat yalnız aşağıdaki paketi uygulasın. Önceki paketlerin tamamlanmış commitlerini koru. Yeni branch/push/merge yapma; kullanıcı değişikliklerini geri alma. `.env`, cookie veya sır okuma. Repo `/Users/motogate/Desktop/all/01-Projeler/fusion-cli`; Kits gereken paketlerde `/Users/motogate/Desktop/all/01-Projeler/fusion-kits`. Önce CLAUDE.md/RULES.md, bu dosya ve belirtilen ilgili kaynakları oku. Gerçek davranışı incele; iyi mevcut alternatifleri yeniden yazma. Yapılmamış testleri geçmiş sayma. Varsayılan modelleri/bütçeleri tahminle değiştirme.

Tek yürütücüyle ilerle; tüm sohbet geçmişini yeni ajanlara taşıma. Yalnız ilgili kapsam için kısa uzman incelemesi yap. Doğrudan mevcut `.venv/bin/python`, App Node22 `/opt/homebrew/opt/node@22/bin`, Kits Node24 `/Users/motogate/.npm/_npx/538786c08bcb9442/node_modules/node/bin` kullan. `uv run`, toplu bağımlılık sync/update veya rastgele `npx` kurulumu yapma. Yeni bağımlılık gerekiyorsa gerekçesini açıkla. Ağır tam pytest ve `evals.kabul` aynı anda koşmasın; tam App/Kits kapıları da yük kaynaklı süre hatalarını azaltmak için sırayla koşsun. Önce anlamlı hedefli regresyon, sonra son stabil kaynak için gerekli kapı; değişmeyen kaynak için aynı kapıyı tekrar etme. Başarısız koşuları gizleme, eşiği/assertion'ı gevşetme.

Her paketin sonunda Türkçe, küçük yerel commit; gerçek değişiklik/test/atlanan kabul/kalan risk/sonraki interface raporu. Kullanıcı daha sonra adım adım push yapacak. Paket bitince sonraki pakete kendiliğinden geçme.

Kaynak plan: `/Users/motogate/Desktop/all/01-Projeler/fusion-cli/docs/superpowers/plans/2026-10-12-fusion-profesyonel-uygulama.md` içindeki Paket 11 ve Global Constraints.

## Paket şartnamesi

# Paket 11 uygulama şartnamesi

Önceki paket tamamlanıp root tarafından yetki verilmeden ürün edit yok. Kaynak otoritesi task-11-blueprint.md; ana plan Global Constraints ve aşağıdaki bölüm; araştırma raporundaki ilgili kabul sözleşmeleri. Önceki paket raporlarında değişen interface ve deferred bulguları oku.

## Sahiplik ve çalışma sınırı

Blueprint ve aşağıdaki kapsamın dosya/interface sahipliği bu işçiye aittir. Başka ajanlarla aynı repo: onların değişikliklerini geri alma. CLAUDE.md/RULES.md; mevcut branch; Türkçe metinler, typed contracts ve mevcut engine/store otoritesi. Sır/.env okuma, branch/push/merge/commit yok. Root fullgate/commit/review sahibi. .venv doğrudan Python; App Node22; Kits cached Node24.21.0. uv run veya paket yöneticisi sync/install/update yok; gerçekten yeni bağımlılık gerekiyorsa önce gerekçeyi roota bildir. Kendi reviewer/subagent spawn etme.

## Paket 11 — Kits sohbet ve belge dayanıklılığı

**Kapsam:** K01–K17/K23/K25, R30/R31. **Dosyalar Kits:** ThreadList, Chat, SpaceWorkspace/SpaceLibrary/PageDocument/PageReviewCard, editor autosave, api, local-threads/page-service/local-computer-bridge. **Tüketir:** paket2 task receipt; paket5 question; varsa mevcut host bridge adapter.

- [ ] A25–A27: remote-only page2 thread, delayed poll, area switch, double create, draft restart, stale expectedRevision, agent patch conflict.
- [ ] Fail test; real merged pagination, scoped async load with AbortSignal, pending create, Turkish search.
- [ ] Draft persistent key conversation/page+revision; storage failure visible; successful save retires only matching draft. Conflict diff/merge explicit.
- [ ] Host calls cancelled on teardown; keyboard Tabs. Büyük library için önce5.000 ölçüm, gerekliyse sunucu paginated search; 10.000 galeri ayrı paket12.
- [ ] Kits type/lint/unit/build/format ve gerçek host integration smoke. Node22 kullanma; Kits kendi pinned scriptini kullan. Main App code değişmediyse bütün Rust build'i burada tekrar etme.


## Teslim

Meaningful TDD RED→GREEN ve hedefli testler: import eksikliği davranış kanıtı değildir, assertion gevşetme/sleep uzatma yok. Mevcut doğru davranışı ölçüp kaydet, yeniden yazma. Beklenmedik failure kök nedenini teşhis et. Rapora exact changed files, commands/results, API/data migration contracts, remaining real/native acceptance ve deferred bulgular yaz. Rapor: task-11-report.md. Full pytest ve evals.kabul root tarafından sıralı; ağır/live koşuyu işçi açmaz. Root yetkili canlı kabul alt görevi ancak ayrı açık mesajla yürür.

## Ayrıntılı kaynak taslağı

`/Users/motogate/Desktop/all/01-Projeler/fusion-cli/docs/superpowers/handoffs/2026-10-13-fusion-paket4-sonrasi/taslaklar/paket-11-kaynak-taslagi.md`. Bu dosya devir paketinde mevcuttur. Bu taslak ilk hazırlık durumudur; önceki paketlerin yeni kod/interface/testleriyle tekrar karşılaştır.

## Tarihsel hazırlık raporu

# Paket 11 — bounded RED hazırlığı

13 Ekim 2026. Ürün aşaması açılmadı; P10 tamamlanması ve açık root ürün yetkisi bekleniyor. Main/Kits ürün dosyaları ve mevcut testler değiştirilmedi. Yalnız iki NEW task11 test dosyası ve bu rapor yazıldı. P2 commit bu gelecek paket testlerini dışarıda bırakmalı. Paket 12 asset authority kapsamına girilmedi.

## Dosyalar ve kaynak eşlemesi

- Kits `tests/task11-thread-pagination.test.tsx`: gerçek exported `ThreadList` React server rendering; yalnız SDK `useThreads` offline fake. İlk ve ikinci fetched page sonuçları aynı hook listesine eklenir. Remote-only page2 görünürlüğü ve birleşik listeye göre empty-state iki gerçek assertion RED. `src/client/ThreadList.tsx` yalnız local.map çiziyor ve boşluğu local.length ile belirliyor. Hook pagination transport/fetchMore/select/transcript bağlantısı bu testte sınanmadı.
- Kits `tests/task11-draft-conflict-scope.test.ts`: gerçek `Pages` geçici `DatabaseSync(':memory:')` CAS + gerçek `PageAutosave` ile agent revision ardından eski expectedRevision flush'ın 409/conflict vermesi ve yerel taslağı koruması GREEN. Gerçek page-tools authorization yolunu çalıştırmaz; aynı Pages.update authority'nin çatışmasını kanıtlar.
- Aynı dosya: injected deferred save API; farklı page/space receive eski signal'ı abort eder, geç completion B sayfasına yazamaz GREEN. Bu controller baseline'dır; `usePageAutosave` callback veya SpaceWorkspace poll scope güvenliğini kanıtlamaz.
- Aynı dosya: gerçek `loadChatDraft/saveChatDraft`, Map storage fake. Yeni draft bilerek boşaltıldığında önceki belirsiz submission/runId gözlem için korunur GREEN. P2 minor retained-observation bulgusu kaydedildi: boş görünür metin submission metadata'yı otomatik temizlemiyor. Bu mevcut bilinçli observation davranışının ölçümüdür; UI observation flow kabulü değildir.

## Exact commands / results

Çalışma dizini `/Users/motogate/Desktop/all/01-Projeler/fusion-kits`; her komutta cached Node24.21.0 kullanıldı. Package manager/install yok.

```sh
/Users/motogate/.npm/_npx/538786c08bcb9442/node_modules/node/bin/node node_modules/prettier/bin/prettier.cjs --write tests/task11-thread-pagination.test.tsx tests/task11-draft-conflict-scope.test.ts
/Users/motogate/.npm/_npx/538786c08bcb9442/node_modules/node/bin/node node_modules/vitest/vitest.mjs run tests/task11-thread-pagination.test.tsx tests/task11-draft-conflict-scope.test.ts
/Users/motogate/.npm/_npx/538786c08bcb9442/node_modules/node/bin/node node_modules/eslint/bin/eslint.js tests/task11-thread-pagination.test.tsx tests/task11-draft-conflict-scope.test.ts
/Users/motogate/.npm/_npx/538786c08bcb9442/node_modules/node/bin/node node_modules/prettier/bin/prettier.cjs --check tests/task11-thread-pagination.test.tsx tests/task11-draft-conflict-scope.test.ts
```

- Prettier write: yalnız iki NEW test biçimlendirildi.
- Vitest: 2 files, 5 tests; **2 behavior FAIL / 3 PASS**, exit 1; duration 539ms. İki FAIL beklenen uzak sohbet metni yok / yanlış empty-state hâlâ var. Missing import/export failure yok; assertion gevşetilmedi.
- Changed-test ESLint: exit 0, PASS.
- Changed-test Prettier check: exit 0, PASS.

## Remaining / test edilemeyen sözleşmeler

Yeni merged projection, durable page draft storage, explicit three-way conflict merge, scoped polling/create controller ve host abort API için önerilen yeni exports henüz mevcut değil. Missing export import testi eklenmedi; bunlar davranış RED sayılmadı. Mevcut React hook callback stale onSaved, SpaceWorkspace delayed polling/old create navigation, chat workspace/profile qualified draft key, draft restart/matching revision retirement, storage failure UI, real remote transcript selection, double-create idempotence, review decision replay ve host cancel ack ayrı ürün yetkisi sonrası küçük regresyonlara ihtiyaç duyar.

Browser/network/server/live/heavy/full-suite/5000 benchmark/uv/package manager/commit çalıştırılmadı; sır/.env okunmadı; subagent açılmadı. API/data migration yapılmadı. Gerçek/native acceptance ve full gate iddiası yok. Bounded hazırlık burada durdu.

### P2 minor açık — component observation failure/reload

`task-2-kits-rereview2.md` Minor follow-up aynen açık kalır: gerçek `Chat.tsx` observe handler `draft || text` saklıyor. Kullanıcı edited draft'ı bilerek boşaltır, eski submission observation başarısız olursa storage boş draft yerine özgün task'ı geri koyabilir; reload eski metni getirir. Bu hazırlığın helper empty roundtrip GREEN'i o component yolunu kapsamaz ve bulguyu düzeltmez/kapatmaz. Ürün yetkisi sonrası gerçek Chat empty-observe failure + reload regresyonu gerekli; observation exact draft (boş string dahil) saklamalı, initialPrompt fallback kendi yolunda kalmalı.

Hazırlık RED testleri ürün kabulü veya tamamlanma kanıtı değildir. Bu paket çalışma ağacındaki yeni testler yalnız bu pakette etkinleşir; sonraki paketlerin bilinçli RED testlerini bu kapıya katma. Gerçek full-suite kapsamını/exclusion nedenlerini kaydet.

Taşınabilir RED test kaynağı: `red-testleri/paket-11/`. `.txt` uzantısı yanlışlıkla toplanmasını önler; sadece bu pakette ilgili test yoluna aktar. Mevcut aynı dosya varsa önce karşılaştır; üzerine kör yazma.
