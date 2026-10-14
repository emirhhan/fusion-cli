# Chat görevi — Paket 16: paketleme-ve-yayin-kapisi

Bu chat yalnız aşağıdaki paketi uygulasın. Önceki paketlerin tamamlanmış commitlerini koru. Yeni branch/push/merge yapma; kullanıcı değişikliklerini geri alma. `.env`, cookie veya sır okuma. Repo `/Users/motogate/Desktop/all/01-Projeler/fusion-cli`; Kits gereken paketlerde `/Users/motogate/Desktop/all/01-Projeler/fusion-kits`. Önce CLAUDE.md/RULES.md, bu dosya ve belirtilen ilgili kaynakları oku. Gerçek davranışı incele; iyi mevcut alternatifleri yeniden yazma. Yapılmamış testleri geçmiş sayma. Varsayılan modelleri/bütçeleri tahminle değiştirme.

Tek yürütücüyle ilerle; tüm sohbet geçmişini yeni ajanlara taşıma. Yalnız ilgili kapsam için kısa uzman incelemesi yap. Doğrudan mevcut `.venv/bin/python`, App Node22 `/opt/homebrew/opt/node@22/bin`, Kits Node24 `/Users/motogate/.npm/_npx/538786c08bcb9442/node_modules/node/bin` kullan. `uv run`, toplu bağımlılık sync/update veya rastgele `npx` kurulumu yapma. Yeni bağımlılık gerekiyorsa gerekçesini açıkla. Ağır tam pytest ve `evals.kabul` aynı anda koşmasın; tam App/Kits kapıları da yük kaynaklı süre hatalarını azaltmak için sırayla koşsun. Önce anlamlı hedefli regresyon, sonra son stabil kaynak için gerekli kapı; değişmeyen kaynak için aynı kapıyı tekrar etme. Başarısız koşuları gizleme, eşiği/assertion'ı gevşetme.

Her paketin sonunda Türkçe, küçük yerel commit; gerçek değişiklik/test/atlanan kabul/kalan risk/sonraki interface raporu. Kullanıcı daha sonra adım adım push yapacak. Paket bitince sonraki pakete kendiliğinden geçme.

Kaynak plan: `/Users/motogate/Desktop/all/01-Projeler/fusion-cli/docs/superpowers/plans/2026-10-12-fusion-profesyonel-uygulama.md` içindeki Paket 16 ve Global Constraints.

## Paket şartnamesi

# Paket 16 uygulama şartnamesi

Önceki paket tamamlanıp root tarafından yetki verilmeden ürün edit yok. Kaynak otoritesi task-14-16-blueprint.md; ana plan Global Constraints ve aşağıdaki bölüm; araştırma raporundaki ilgili kabul sözleşmeleri. Önceki paket raporlarında değişen interface ve deferred bulguları oku.

## Sahiplik ve çalışma sınırı

Blueprint ve aşağıdaki kapsamın dosya/interface sahipliği bu işçiye aittir. Başka ajanlarla aynı repo: onların değişikliklerini geri alma. CLAUDE.md/RULES.md; mevcut branch; Türkçe metinler, typed contracts ve mevcut engine/store otoritesi. Sır/.env okuma, branch/push/merge/commit yok. Root fullgate/commit/review sahibi. .venv doğrudan Python; App Node22; Kits cached Node24.21.0. uv run veya paket yöneticisi sync/install/update yok; gerçekten yeni bağımlılık gerekiyorsa önce gerekçeyi roota bildir. Kendi reviewer/subagent spawn etme.

## Paket 16 — Günlük kullanım sürümü kabulü ve devir

**Kapsam:** L01–L12 ve tamamlanan P0/P1 paketleri. **Dosyalar:** runtime/build/install scripts, existing release reports, continuation record.

- [ ] App Node22 test/build; gerekiyorsa Rust/Tauri check:ci; Kits pinned check/build; Python full gates. Koşular kaynak baskısına göre sıralı.
- [ ] Clean user profile/install fixture ve mevcut kullanıcı upgrade; transcript/checkpoint/draft/asset migration.
- [ ] Native UI klavye/VoiceOver/dark/light/zoom; screenshots güncel. Screenshot threshold'u kusuru gizlemek için artırma.
- [ ] Release manifest: commitler, bundled core+Kits sürümleri, model/connector support, test/acceptance kanıtı, bilinen eksikler, rollback yolu.
- [ ] Kullanıcı günlük üç işi Fusion'da yapar; müdahale ve hatalar ölçülür. Geçmeyen yüzeye “tam hazır” etiketi verilmez.


## Teslim

Meaningful TDD RED→GREEN ve hedefli testler: import eksikliği davranış kanıtı değildir, assertion gevşetme/sleep uzatma yok. Mevcut doğru davranışı ölçüp kaydet, yeniden yazma. Beklenmedik failure kök nedenini teşhis et. Rapora exact changed files, commands/results, API/data migration contracts, remaining real/native acceptance ve deferred bulgular yaz. Rapor: task-16-report.md. Full pytest ve evals.kabul root tarafından sıralı; ağır/live koşuyu işçi açmaz. Root yetkili canlı kabul alt görevi ancak ayrı açık mesajla yürür.

## Ayrıntılı kaynak taslağı

`/Users/motogate/Desktop/all/01-Projeler/fusion-cli/docs/superpowers/handoffs/2026-10-13-fusion-paket4-sonrasi/taslaklar/paket-16-kaynak-taslagi.md`. Bu dosya devir paketinde mevcuttur. Bu taslak ilk hazırlık durumudur; önceki paketlerin yeni kod/interface/testleriyle tekrar karşılaştır.

## Tarihsel hazırlık raporu

# Paket 16 — Kaynak doğrulanmış devir hazırlığı

13 Ekim 2026. **Durum: yalnız hazırlık; release/kabul uygulanmadı.** P15 tamamlanması ve root'un açık P16 uygulama yetkisi beklenir. Tek değişen dosya bu rapordur. Ürün, mevcut test, P2 donmuş kaynak, branch, commit, bağımlılık veya ortam değişmedi. Build/install/test/import/live/server/browser/mikrofon/hardware/fullgate çalıştırılmadı; kullanıcı profili, install çıktısı, `.env` veya credential okunmadı. Aşağıdaki komutlar kaynakta mevcut sonraki koşulardır; başarı kanıtı değildir. Statik cat/sed/rg/ls okumaları kullanıldı; başarısız aramalar veri otoritesi diye sunulmadı.

Otorite: `task-14-16-blueprint.md`, `task-16-brief.md`, ana plan Global Constraints/Paket16, CLAUDE.md/RULES.md. P15 raporu halen bounded RED hazırlığıdır; P8/10/11/13 raporlarının hazırlık/deferred sözleşmeleri tamamlanmış ürün API'si sayılmaz. P16 durdurma koşulu değişmedi.

## Sıralı operasyon matrisi

| Yüzey | Kaynakta exact giriş / runtime | Çıktı ve gereken kanıt | Şimdi |
|---|---|---|---|
| Python | `Makefile`: lint = `.venv/bin/ruff format --check src tests evals prompt_opt desktop_build` + `.venv/bin/ruff check src tests evals prompt_opt desktop_build`; type = `.venv/bin/mypy`; test = `.venv/bin/pytest`; deadlock mevcut DEADLOCK_SUITES | Root sırayla exit/log/full source revision/runtime kaydeder; test sayıları yeniden ölçülür | not_run |
| App | `app/package.json`: `npm test`, `npm run build`, `npm run check:ci`; `scripts/check-runtime.mjs` app-tests için exact major22 zorunlu | test guard build'de ayrı çağrılmaz; check:ci fmt/clippy/test içerir ve **terminal::tests::** skip eder. Native terminal kabulü ayrı | not_run |
| Kits | sibling `package.json`: `npm run kits:check`, cached Node24.21.0; scripts/kits-check.mjs sırayla check-format/lint/typecheck/test/build | handoff/evidence/final-{command}.log + checks.json node/results/code/error/log. Paket scripti npx kullanır; hazırlıkta npx/install yok, gelecekte root cached seçimi doğrular | not_run |
| Core runtime | App `npm run runtime:build`; `npm run runtime:smoke`; run-python.mjs FUSION_BUILD_PYTHON, yoksa repo .venv, yoksa platform system Python seçer | resources/runtime/runtime-manifest.json, fusion-runtime.tar.gz, unpacked/fusion (Windows fusion.exe); revision+selected interpreter+target+health receipt gerekir | not_run |
| Listen | `npm run listen:build:mac` / `listen:build:win`; build_adapter.py macOS swiftc, Windows dotnet | resources/fusion-listen / fusion-listen.exe; gerçek compile ve nested signing ayrı; compiler/SDK sürümü burada tahmin edilmedi | not_run |
| Mac App | `npm run bundle:mac`: listen→runtime build→smoke→tauri build --config src-tauri/tauri.bundle.conf.json --bundles app,dmg→stable_sign_bundle.py | src-tauri/target/release/bundle/macos/Fusion.app ve dmg/*.dmg; config beforeBuildCommand npm run build | not_run |
| Mac App+Kits | `npm run bundle:mac:kits`: kits:prepare önce, aynı zincir; ek tauri.kits.conf.json | prepare-kits.mjs FUSION_KITS_DIR yoksa sibling fusion-kits; FUSION_KITS_NODE yoksa process.execPath. Seçilen Node >=24 kontrolü; resources/kits silinip app bundle ve Node kopyalanır. App22 ile varsayılan Node seçimi başarısız olabilir; explicit cached Kits Node şart | not_run |
| Kits dağıtım | `kits:package`, `kits:bundle`, `kits:install` | package ZIP ayrı; bundle dist/client mevcut build'e dayanır, server esbuild target node24. install gerçek home data-root'a yazar ve mevcutsa repo .env'i yeni target'a kopyalar; hazırlıkta yasak | not_run |
| Mac updater | desktop_build/macos/build_update.py --app --output [--key] [--repository] | final aynı imzalı App'ten Fusion-{version}-darwin-{architecture}.app.tar.gz, .sig, latest.json; updater key güvenli release ortamında. Native code signing/notarization ile aynı kapı değildir | not_run |
| Windows | App bundle:win listen→runtime→smoke→tauri windows config --bundles nsis; desktop_build/windows/build_update.py/smoke_core.py blueprint otoritesi | Windows installer/signature/platform ve gerçek Windows çalışması ayrıca gerekir; Mac'ten geçti sonucu çıkarılmaz | not_run |

`Makefile app-check/app-visual` npm ci; runtime-bundle/app-package install dependency içerir. Bu hazırlığın sınırlarıyla uyumlu koşular değildir. İleride bağımlılık mutasyonu için root ayrı karar verir; scriptlerin varlığı yürütme yetkisi değildir.

## Paket kimliği ve checksum eşleme

- Core tek version kaynağı `src/fusion_cli/__init__.py::__version__` şu an 0.7.0. App `src-tauri/tauri.conf.json` 0.7.0/com.fusion.desktop; frontend package.json 0.1.0 farklı kimliktir, desktop sürümüyle karıştırılmaz. Kits package.json 0.1.0 source metadata'dır; artifact observed version henüz unknown.
- `desktop_build/runtime/build_runtime.py::build_manifest`: schema1, runtime_version, target, archive, archive_sha256, entrypoint, files; her file path/kind/mode/sha256, symlink path/kind/mode/target. Arşiv adına veya runtime sürümüne bakmak embedded core revision kanıtı değildir.
- Tauri bundle config runtime manifest/arşivi `Contents/Resources/runtime/` mapping'ine, helper'ı `fusion-listen` mapping'ine; Kits ek config resources/kits/→kits/ mapping'ine alır. Artifact üretilince manifest↔arşiv↔bundle bytes ve target eşleşmesi ölçülür; hazırlık mevcut kurulu artifact'i okumadı/hashlemedi.
- Kits `scripts/kits-package.mjs`: release/fusion-kits.zip, MANIFEST.json, fusion-kits.zip.sha256; MANIFEST product/version/upstream ve files path/bytes/sha256; handoff/upstream.json source girdisidir. Symlink reddeder; data/node_modules/.git/.env (example hariç)/SQLite dışlar. Kaynak ZIP ile embedded bundle aynı dosya listesi değildir.
- `scripts/kits-bundle.mjs` embedded package.json yalnız name=fusion-kits-bundle/private/type yazar; **Kits version/full commit/checksum ledger üretmez**. dist/server/package.json CopilotKit channels metadata'sıdır, Kits sürümü değildir. Playwright/playwright-core yanına kopyalanır; packaged browser runtime çalışması hâlâ ayrı kanıt ister. prepare-kits Node binary'sinin version+hash'i ve bundle file inventory ayrıca aggregate manifest'e bağlanmalıdır.
- Aggregate audit manifest blueprint schema1 önerisidir, mevcut installer manifestlerinin yerine geçmez. Main/Kits full commit+dirty/public digest, explicit artifact path/size/SHA, app/core/runtime/Kits versions+target ve producer receipt gerekir. Şu hazırlıkta full commits/dirty snapshot/artifact digest ölçülmedi; alanlar unknown kalır.

## Clean install / upgrade veri matrisi

| Veri | Mevcut kaynak otoritesi | İzole fixture girdisi ve istenen readback | Açık kanıt |
|---|---|---|---|
| Clean runtime | runtime_manifest.rs / runtime_installer.rs; macos/smoke_app_bundle.py inspect_bundle/launch_clean | Yeni boş HOME/profile; iki launch, active runtime marker sabitliği, corrupted executable repair, bundle hash/target | Clean HOME smoke provider/native onboarding başarısı değildir; gerçek fixture hiç koşulmadı |
| Transcript | src/fusion_cli/cli/repl/transcript_store.py | base/transcripts/<workspace digest>/events.jsonl; conversation/session/message IDs ve tombstone; sentetik iki sohbet/root, export count/hash ve load_transcript_messages readback | Version upgrade migration runner bu kaynak okumalarından doğrulanmadı; workspace taşınmasıyla release migration aynı şey değildir |
| Checkpoint | memory/checkpoint_store.py JsonCheckpointStore | base/<safe plan_id>.json; writer schema_version4, plan schema ayrı; eski supported fixture→aday load; task/root/conversation/steps/revision/evidence/effect continuity | temp+replace atomik save mevcut, full previous→candidate compatibility/failed migration restore ölçülmedi |
| Draft / submission | App sessions/persistence.ts ve submissionPersistence.ts | fusion.session-view version1; fusion.submissions:<sessionId> request/session/root/task/attachments/state/turnId. Pending submission aynı requestID ile restore; yanlış root/task'a kaymama | Submission snapshot tamamlanmamış composer draft yerine geçmez. Kalıcı unsent composer draft authority bu bounded okumada doğrulanamadı; önce source owner'dan gerçek yol/sürüm/restore API gerekir |
| Asset | appserver/image_create.py→image_flows.gallery_dir/write_sidecar; core/assets.py inventory doğrulaması | Sentetik decode edilebilir image+sidecar+flow JSON, public IDs/refIDs/hash/MIME/dimensions/alpha; before/after load/render/export; yanlış root kaçışı reddi | Image sidecar/flow kaydı asset migration ledger değildir; P10/P12 authority finalized old→new fixture ayrıca gerekir |
| Kits belge | P11 PageAutosave/review current authority, expectedRevision | iki page/space, stale revision conflict, pending draft/save ve restart readback; source/bundle version eşleme | P11 hazırlık controller baseline'ı tüm native autosave/migration davranışını kanıtlamaz |

Girdi önceki **doğrulanmış** release paketi+public sentetik snapshot, aday paketi+source manifest ve support schema range'dir. Önce fixture üzerinde backup/hash/readback/restore prosedürü ölçülmeden mevcut kullanıcı upgrade'i başlatılmaz. Credential snapshot'a alınmaz. Veri migration exception/crash'te eski bytes korunur; success sonrası no duplicate external effect/OBSERVE_FIRST receipt sürekliliği gerekir. Root manuel veri tamiri müdahale olarak kaydedilir.

## Backup / rollback / signing sınırı

runtime_installer.rs staging extract/hash/path/symlink/health kapısından sonra atomic replace yapar. replace_version_atomically eski destination'ı quarantine'a taşır; staging rename başarısızsa eskiyi geri koyar, başarılıysa quarantine silinir. **Başarılı upgrade sonrası kalıcı eski paket backup'u değildir.** Binary rollback için explicit previous artifact path/hash ve data schema compatibility; uyumsuzsa matching snapshot restore receipt gerekir. Transcript/checkpoint/draft/assets complete backup orchestration bu bounded kaynaklarda doğrulanmadı. External effect geri alma iddiası kurulmaz.

tauri.bundle.conf.json signingIdentity="-"; stable_sign_bundle.py com.fusion.desktop stable designated requirement ile ad-hoc sign, nested executable verify ve DMG payload replace/verify yapar. Bu developer distribution certificate veya Apple notarization kanıtı değildir. “Unsigned” ifadesi ad-hoc code signature yokmuş gibi kullanılmamalıdır: developer-signed/notarized unknown/not_run; updater .sig ayrı anahtar mekanizmasıdır. Native Gatekeeper/permission davranışı gerçek cihazda ayrıca gözlenir.

write_runtime_report.py kaynakta fixed Python/React/Rust sayıları, clean HOME, rollback ve kalite pass satırları yazıyor; max mtime DMG ve short HEAD seçiyor. Bunlar ölçüm receipt'i değildir. P16 yetkisinde bu writer en küçük receipt adapter değişimiyle missing→unknown/not_run üretmeli; explicit artifact/full SHA identity olmadan ready yazmamalı.

## Önerilen en küçük saf verifier sözleşmeleri

Henüz API/dosya uygulanmadı. Blueprint'e bağlı küçük desktop_build audit modülü ve mevcut writer adapter yeterli; yeni installer/store/engine yok.

1. Public aggregate manifest'i parse/validate: schema1 only, strict type/finite values, duplicate release/gate/attempt IDs, required fields; evidence refs yalnız açık public root altında, traversal/symlink escape yasak. Auth değeri veya auth hash'i kabul edilmez.
2. Explicit artifacts doğrulaması: bytes/SHA-256, runtime schema1 archive hash ve file/symlink contract, App version/target/core version eşleme, Kits source identity ile embedded inventory+Node version/hash ilişkilendirme. Mtime/newest veya package name PASS oluşturmaz.
3. Gate receipt adapter: actual command/runtime/full source revision/start/end/exit/evidence hash; eksik veya null exit→unknown/not_run. check:ci skip kapsamı açık. Eski test sayısı yeni gate yerine geçmez.
4. Migration/rollback verifier: old/candidate IDs/schema/count/hash/readback refs, backup restore+failed migration old-byte preservation; supported schema range yoksa rollback unverified. İlk launch veya staging health tek başına migration PASS değildir.
5. Ready aggregation mevcut RunRecord/Inspection/classify otoritesini tüketir; required checks false, missing receipt, driver error, unknown native rubric veya pending L01–L12'yi gizlemez. Usage/cost unknown kalır; requested/observed/fallback distinct. No success calculator kopyası.

Yetki gelince regression adayları: hardcoded writer pass→missing receipt unknown; wrong artifact/SHA/version; duplicate/ref traversal/symlink; unknown future schema; migration mismatch/failed restore; missing native evidence. Hazırlıkta test dosyası yazılmadı veya RED→GREEN iddiası kurulmadı.

## L12 ve gerçek insan devir adımları

P13 ve blueprint'teki mevcut voice helper/UI otoriteleri korunur; yeni native probe/flag icat edilmez. Cihazda kullanıcı mikrofon deny→allow, kısa Türkçe utterance, duyulur TTS ve interrupt, hangup owned task cleanup/text preservation; her adım call/question/task ID ve build/evidence refs ile gözlenir. Mock/helper smoke mikrofonun duyulduğu veya TTS'nin işitildiği kabulü değildir. Kullanıcı login/2FA'yı kendi browser profilinde yapar; visible window, takeover/resume, kapanış/cancel sınırı insan gözlemi ister.

Native App/Kits dark/light/system, narrow/wide/zoom, Tab/Shift+Tab popup/modal focus-return, VoiceOver isimleri/tek status duyurusu ve gerçek screenshots ayrı pending kabul. Screenshot threshold kusuru kapatmak için artırılmaz. Kullanıcının seçtiği üç günlük iş için task/output/receipt, süre, hata ve müdahale ölçülür; root katkısı ayrı provenance'tır. Diğer makine kapıları bu hardware pending satırları yüzünden durdurulmaz, fakat genel günlük sürüm hazır etiketi verilmez.

## Devam önkoşulları

P15 complete + root explicit P16 implementation authorization; finalized P2–P15 interface/review/fullgate receipts; cached App22/Kits24.21.0 binary seçim kaydı; kaynak attestation ve explicit candidate/previous artifacts; sentetik clean/upgrade profiles+backup/readback fixtures; secure signer ortamı; L01–L12 registered entry/rubric ve ayrı live/hardware yetkisi. Hiçbiri bu raporda fulfilled varsayılmadı. Hazırlık burada durdu.

Hazırlık RED testleri ürün kabulü veya tamamlanma kanıtı değildir. Bu paket çalışma ağacındaki yeni testler yalnız bu pakette etkinleşir; sonraki paketlerin bilinçli RED testlerini bu kapıya katma. Gerçek full-suite kapsamını/exclusion nedenlerini kaydet.
