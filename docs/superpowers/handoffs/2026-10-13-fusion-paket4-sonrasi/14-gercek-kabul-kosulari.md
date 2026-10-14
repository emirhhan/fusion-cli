# Chat görevi — Paket 14: gercek-kabul-kosulari

Bu chat yalnız aşağıdaki paketi uygulasın. Önceki paketlerin tamamlanmış commitlerini koru. Yeni branch/push/merge yapma; kullanıcı değişikliklerini geri alma. `.env`, cookie veya sır okuma. Repo `/Users/motogate/Desktop/all/01-Projeler/fusion-cli`; Kits gereken paketlerde `/Users/motogate/Desktop/all/01-Projeler/fusion-kits`. Önce CLAUDE.md/RULES.md, bu dosya ve belirtilen ilgili kaynakları oku. Gerçek davranışı incele; iyi mevcut alternatifleri yeniden yazma. Yapılmamış testleri geçmiş sayma. Varsayılan modelleri/bütçeleri tahminle değiştirme.

Tek yürütücüyle ilerle; tüm sohbet geçmişini yeni ajanlara taşıma. Yalnız ilgili kapsam için kısa uzman incelemesi yap. Doğrudan mevcut `.venv/bin/python`, App Node22 `/opt/homebrew/opt/node@22/bin`, Kits Node24 `/Users/motogate/.npm/_npx/538786c08bcb9442/node_modules/node/bin` kullan. `uv run`, toplu bağımlılık sync/update veya rastgele `npx` kurulumu yapma. Yeni bağımlılık gerekiyorsa gerekçesini açıkla. Ağır tam pytest ve `evals.kabul` aynı anda koşmasın; tam App/Kits kapıları da yük kaynaklı süre hatalarını azaltmak için sırayla koşsun. Önce anlamlı hedefli regresyon, sonra son stabil kaynak için gerekli kapı; değişmeyen kaynak için aynı kapıyı tekrar etme. Başarısız koşuları gizleme, eşiği/assertion'ı gevşetme.

Her paketin sonunda Türkçe, küçük yerel commit; gerçek değişiklik/test/atlanan kabul/kalan risk/sonraki interface raporu. Kullanıcı daha sonra adım adım push yapacak. Paket bitince sonraki pakete kendiliğinden geçme.

Kaynak plan: `/Users/motogate/Desktop/all/01-Projeler/fusion-cli/docs/superpowers/plans/2026-10-12-fusion-profesyonel-uygulama.md` içindeki Paket 14 ve Global Constraints.

## Paket şartnamesi

# Paket 14 uygulama şartnamesi

Önceki paket tamamlanıp root tarafından yetki verilmeden ürün edit yok. Kaynak otoritesi task-14-16-blueprint.md; ana plan Global Constraints ve aşağıdaki bölüm; araştırma raporundaki ilgili kabul sözleşmeleri. Önceki paket raporlarında değişen interface ve deferred bulguları oku.

## Sahiplik ve çalışma sınırı

Blueprint ve aşağıdaki kapsamın dosya/interface sahipliği bu işçiye aittir. Başka ajanlarla aynı repo: onların değişikliklerini geri alma. CLAUDE.md/RULES.md; mevcut branch; Türkçe metinler, typed contracts ve mevcut engine/store otoritesi. Sır/.env okuma, branch/push/merge/commit yok. Root fullgate/commit/review sahibi. .venv doğrudan Python; App Node22; Kits cached Node24.21.0. uv run veya paket yöneticisi sync/install/update yok; gerçekten yeni bağımlılık gerekiyorsa önce gerekçeyi roota bildir. Kendi reviewer/subagent spawn etme.

## Paket 14 — Günlük işler ve üretim kalitesi

**Kapsam:** L02–L11, R24/R37/R38. **Dosyalar:** existing `evals/suite/production.yaml`, `evals/kabul`, skills and actual product tool/engine paths where evidence points.

- [ ] Aynı brief/input/provider/izin ile taban kaydı; günlük araştırma, kod düzeltme, MCP taslak ve belge senaryoları.
- [ ] Site/game/video işler sıralı boş output kökünden Fusion üretimi. Başarısız output'u root elle düzeltip Fusion başarısı sayma.
- [ ] Ürün kusuruna source regresyon; kabul ölçerindeki kusursa evaluator düzeltmesi ayrı. İkisini parite kanıtı diye birleştirme.
- [ ] Gerçek viewport/kare/etkileşim+insan rubriği. Başarısız denemeler ve unavailable ayrı ama saklanmaz.
- [ ] Kalite kapısı ve tekrar aynı kabul. “ChatGPT yerine kullanım” kararı başarısızlık/data-loss/false success matrisiyle verilir; yüzde uydurma.


## Teslim

Meaningful TDD RED→GREEN ve hedefli testler: import eksikliği davranış kanıtı değildir, assertion gevşetme/sleep uzatma yok. Mevcut doğru davranışı ölçüp kaydet, yeniden yazma. Beklenmedik failure kök nedenini teşhis et. Rapora exact changed files, commands/results, API/data migration contracts, remaining real/native acceptance ve deferred bulgular yaz. Rapor: task-14-report.md. Full pytest ve evals.kabul root tarafından sıralı; ağır/live koşuyu işçi açmaz. Root yetkili canlı kabul alt görevi ancak ayrı açık mesajla yürür.

## Ayrıntılı kaynak taslağı

`/Users/motogate/Desktop/all/01-Projeler/fusion-cli/docs/superpowers/handoffs/2026-10-13-fusion-paket4-sonrasi/taslaklar/paket-14-kaynak-taslagi.md`. Bu dosya devir paketinde mevcuttur. Bu taslak ilk hazırlık durumudur; önceki paketlerin yeni kod/interface/testleriyle tekrar karşılaştır.

## Tarihsel hazırlık raporu

# Paket 14 — kaynak doğrulanmış koşu hazırlığı

13 Ekim 2026. Yalnız statik kaynak okundu ve bu rapor yazıldı. Ürün, mevcut/yeni test, build, import probe, model, MCP sunucusu, tarayıcı, native cihaz veya job çalıştırılmadı. Sır ve `.env` okunmadı. P2 donmuş kaynakları değiştirilmedi. P13 raporu hâlâ sınırlı RED hazırlığı bildiriyor; P13 complete ve root'un açık P14 ürün yetkisi gelmeden aşağıdaki komutlar çalıştırılmayacak. Blueprint otoritesi korunur; bu rapor onun mevcut parser ayrıntılarını tamamlar.

## Komut ve kanıt kontratı

Aşağıdaki `<...>` değerleri planlama yer tutucularıdır; aynen çalıştırılacak komut değildir. CWD Main repo kökü; Python mevcut `.venv/bin/python`. Her baseline/candidate ve senaryo için ayrı yeni boş public kök gerekir. Kaynak digest/revision, brief, asset/license, provider/model, izin ve kriter sürümü dondurulmadan parite iddiası yok. Gerçek provider/config hazırlığı root'un güvenli akışına aittir; hazır durumu burada unknown.

**P (mevcut beş production işi):** `.venv/bin/python -m evals run evals/suite/production.yaml --profile production --workspace <yeni-is-koku> --out <yeni-rapor.json> --repeat 3 --enforce`. Parser `--model` ve `--seed` de destekler; bu koşucu `--config`, `--timeout`, `--alan` veya görev-ID filtresi desteklemez. `production` ve `fusion-full` aynı `FusionAgentRunner` yoluna gider; her ikisi `interactive_asker`, `persistent_lessons`, `cross_run_recall` hariç tutar. Profil adı gerçek interaktif parity kanıtı değildir.

**K(alan):** `.venv/bin/python -m evals.kabul --alan <kayitli-alan> --tekrar 3 --paralel 1 --cikti <yeni-public-kok>`. Preflight açık kalır. Kayıtlı adlar yalnız `site_kopyasi`, `site_kopyasi_2`, `animasyon`, `remotion`, `html_oyun`, `kendini_gelistirme`, `tarayici`. Parser `--config <guvenli-config-yolu>` kabul eder. Açık motor karşılaştırmasında `--engine-source <source>` ve `--engine-manifest <manifest>` birlikte gerekir; `--require-remotion-kit`, `--remotion-browser-executable <executable>` ve `--remotion-browser-mode headless-shell|chrome-for-testing` ancak bu motor seçimiyle kullanılabilir. `--onkontrolu-atla` mevcut olsa da kabul planında kullanılmaz. CLI sonuç statülerini JSON'a yazar; koşu sonu normal CLI exit tek başına alan PASS kanıtı değildir.

**D (yalnız sonraki özel canlı fixture taslağının mevcut transport'u):** `.venv/bin/python -m evals.live_drive --kok <izole-kok> --mod auto --gorev <dondurulmus-gorev> --sure <onaylanmis-butce> --stderr <public-kok/cekirdek.err> --olaylar <public-kok/olaylar.jsonl>`. `--gorev` tekrarlanabilir. `--soru-cevabi ilk|atla` ve `--onay once|deny` gerçek parser değerleridir; insan seçim/izin kabulünü otomatik yanıtla kapatmaz. D bir L02/L04/L05 evaluator'ı değildir; fixture ve criteria eklenmeden yalnız transport sağlar. Stdout sürücü JSON'udur; dosyaya kayıt çağıranın sorumluluğudur.

Kaynak otoriteleri: `evals/cli.py::main/_run`, `evals/profiles.py::EvalProfile/build_runner/exclusions_for`, `evals/kabul/cli.py::_parser/main`, `evals/kabul/areas/__init__.py::AREA_MODULES`, `evals/kabul/runner.py::_driver_command`, `evals/live_drive.py::main/drive`.

## L01–L12 operasyon matrisi

| Senaryo | Mevcut komut/girdi → çıktı ve kanıt otoritesi | Eksik yüzey / prerequisites / timeout ve insan kanıtı |
|---|---|---|
| L01 temiz paket | `.venv/bin/python desktop_build/macos/smoke_app_bundle.py <Fusion.app> --inspect-only`; launch yetkisinden sonra aynı komut flagsiz. Girdi build paketi; `inspect_bundle` manifest/hash/target, `launch_clean` temiz kullanıcı launch/repair assertions. | Statik inspect ilk/ikinci gerçek launch değildir. Flagsiz yol native süreç başlatır. Paketlenmiş runtime, macOS ve hazır App gerekir; App build/test destek profili Node22, smoke itself Node gerektirmez. Smoke'un CLI timeout/cancel bayrağı yok. Onboarding, terminal kullanmadan kurulum, Gatekeeper ve gerçek provider cevabı insan kabulü. |
| L02 günlük araştırma | P şu an araştırma fixture'ı içermiyor. Sonraki dondurulmuş çok-turlu görev D'nin tekrar `--gorev` girdileriyle mevcut `fusion app` otoritesine bağlanabilir. `olaylar.jsonl`, gerçek kaynak/tool receipts, authoritative outcome gerekir. | Araştırma brief/source/preference/question fixture ve inspector eklenmeli; mevcut beş göreve L02 denemez. Network/search capability ve provider hazır durumu unknown. D bütçe + kapanış kontratı aşağıda; kaynak doğruluğu, belirsizlik ve kullanıcı tercihinin korunması insan rubriği. |
| L03 kod düzeltme | P: `yanlis-hedefte-yeniden-planla`, `buyuk-artifact-korumali-duzenleme`, `sohbet-izolasyonu`. Ayrı kapsam K(kendini_gelistirme): mevcut `self_improve.prepare` HEAD detached worktree üretir, çıktı `fusion-degisikligi.diff`; inspect gerçek pytest/ruff/mypy/config writer kontrollerini ölçer. | Üç sabitli `large.py` büyük payload kanıtı değildir. P YAML verifier kodu `core.assets.inspect_image_asset/validate_asset_manifest` mevcut sembolleridir; import varlığı davranış başarısı değildir. K self-improve çalışma ağacındaki uncommitted candidate'ı HEAD'e taşımaz; candidate snapshot kontratı çözülmeli. Git ve mevcut venv gerekir; alan 3600 s, verifier komutu 900 s. Root elle patch'i tamamlarsa Fusion attempt failed/partial kalır. İnsan brief/diff ve kullanıcı edit korunmasını inceler. |
| L04 MCP taslak | P `oauth-mcp-yasam-dongusu`: setup yalnız `TOOLS={ping: lambda: pong}` dosyası; çıktı Fusion'ın `smoke_test.py` dosyası ve verifier stdout. Mevcut test genişletme otoriteleri `tests/test_mcp_lifecycle_contract.py`, `test_mcp_oauth.py`, `test_mcp_pool.py`, `test_mcp_trust_contract.py`, `test_mcp_tool_effect.py`. | Dict smoke iki gerçek server/OAuth/list/read/refresh/degraded/izin kanıtı değil. CLI'da `--mcp-server` veya `--draft` kabul bayrağı yok. Dar test-target, preview/question receipts, iki server fixture ve kesinti izolasyonu eklenmeli. Connector readiness unknown; gerçek dış yazma öncesi mevcut izin otoritesi. Taslak doğruluğunu insan inceler; P timeout aşağıda. |
| L05 belge/skill | Mevcut P suite içinde belge yok; D gerçek task transport'u sağlar. Mevcut skills `src/fusion_cli/config/skills`, scoped-skill fixtures `tests/test_task7_scope_skill_redprep.py`; çıktı gerçek belge/hash/MIME/açılabilirlik, origin/version/source receipts olmalı. | Belge alanı CLI kayıt defterinde yok; `.docx`/PDF başarı kontrolü ve origin evidence eklenmeli. Skill bulunması doc üretim capability kanıtı değildir. Skill/backend/provider support unknown; gereken renderer bağımlılıkları seçilen format doğrulanınca dondurulur. D bütçesi, insan içerik/layout/source rubriği. |
| L06 crash/restart | Ürün authority `memory/checkpoint_store.py`, `checkpoint_evidence.py`, `checkpoint_repair.py`; fixtures `tests/test_task8_checkpoint_contract.py`, `test_checkpoint_repair.py`. Özel kabul command/area mevcut değil. | D'nin yeniden başlatılması OBSERVE_FIRST, draft retention veya dış işin tekrarlanmaması kanıtı değildir. Crash fixture, revision/task/effect receipt before/after ve completed effect observation eklenmeli. Bütçe/cancel fixture kapsamıyla belirlenmeli; kişisel data-root kullanılmaz. |
| L07 Kits belge/diff | Kits kökünde mevcut script adları `npm run kits:local-chat-smoke`, `npm run kits:fusion-smoke`; source `scripts/kits-local-chat-smoke.mjs`, `scripts/kits-fusion-smoke.mjs`. Fixture otoritesi `tests/page-context.test.ts`, `page-snapshots.test.ts`, `page-review.test.tsx`, `page-service.test.ts`. | Package scriptleri npx Node24.21.0 ister ve cache yoksa network/install başlatabilir; hazırlıkta koşulmaz. Sonraki koşu cached desteklenen runtime ile script argümanları ayrıca doğrulanarak planlanmalı. Smoke page edit/conflict/restart insan kabulünün tamamı değil; expectedRevision/save/stale receipt ve gerçek UI edit gerekir. L07 özel eval area/timeout/cancel bayrağı yok. |
| L08 görsel | Ürün `tests/test_image_create_flow.py`, `test_image_flows.py`, `test_task10_image_payload_redprep.py`, `test_image_tools.py` fixture sınırları; P yalnız lisanslı Godot PNG dar görevi. K kayıtlı image area yok. | Live image create/edit/reference/partial/cancel fixture + provider receipt/assetID/refID/decode/MIME/size/alpha bağlanmalı. Sahte/placeholder veya model adından support çıkarmak yok. Provider image support unknown; insan doğru referans/edit rubriği, owned cancel gerçek receipt. |
| L09 iki site | Önce K(site_kopyasi), sonra ayrı boş kökte K(site_kopyasi_2). `site_clone.py::make_area` ortak TASK_TEMPLATE/inspect; ikinci source `site_clone_second.py` (`https://www.desa.com.tr`). WordPress output root `_site_root`; `RunRecord.inspection` ürün/menu/checkout checks. | `php`, `wp`, Playwright/browser + source network gerekir; preflight yalnız declared executable kontrolü bütün browser readiness değildir. İki alan 5400 s. Aynı kaynak viewport/mobile interaction ve saklanan screenshot+insan rubriği ayrıca; iki ayrı run aynı site brief'i değildir. |
| L10 oyun | K(html_oyun); `html_game.py::TASK`, `inspect`, `measure`, `_game_probe.py`. Çıktı `index.html`/assets; file URI ve browser probes start/control/pause/gameover/restart. | Alan 3600 s; Playwright/browser bağımlılığı preflight executables listesinde kapsamlı doğrulanmaz. `platform_game.py` CLI kayıtlı değil; `--alan platform_oyun` uydurulamaz. Gerçek asset kullanım, konsol ve oynanış screenshot + insan oynama rubriği gerekir. |
| L11 video/animasyon | Önce K(remotion), sonra K(animasyon), ayrı boş köklerde. Remotion prepare `fusion-tanitim/` içine logo/README/YETENEKLER/KITS kopyalar; çıktı `out/video.mp4`, `remotion.inspect` ffprobe/ffmpeg duration/resolution/fps/nonblank/logo checks. Animasyon `index.html`, hareket/reduced-motion probes. | Remotion 5400 s, ffprobe/ffmpeg araç timeout 120 s; declared executables node,npx,ffprobe,ffmpeg. Animasyon 3600 s + Playwright/browser. Remotion Node path/runtime/kit seçimi receipt gerekir; App Node22 ile Kits Node24 ayrı, global Node destek kanıtı değil. Eksik prepare asset sessiz atlandığından run öncesi hash/presence kaydı eklenmeli. Kareler bellekten kontrol edilirse saklanmış PNG diye sunulmaz. Tempo/taşma/son bölüm insan rubriği. |
| L12 voice/browser | Main `tests/test_voice.py`, `test_voice_context.py`, `test_voice_text.py`; Kits `tests/voice.test.ts`, `local-voice.test.ts` ve P13 RED hazırlığı. Browser mevcut K(tarayici): `browser.prepare/inspect`, Chrome pairing ve `chrome.json`. | Browser area 1800 s, pairing 120 s; gerçek Chrome extension/session gerektiği için kişisel profile hazırlıkta kullanılmaz. `chrome.json` pairing anahtarı içerir: public artifact diye yayımlanmaz. L12 voice kabul command yok. Gerçek microphone deny→allow/STT/duyulur Türkçe TTS/interrupt/owned hangup/window/profile/login insan cihazında gerekir. P13 henüz complete değil. |

## Output, timeout ve iptal sınırları

P `AgentTaskExecutor._prepare_workspace` mevcut task/run dizinini silip yeniden kurar; bu yüzden yeni boş kök zorunludur. `_transkript.jsonl`, `_acceptance.stdout.txt`, `_acceptance.stderr.txt` gerçek executor artifact adlarıdır; aggregate JSON `--out` ile yazılır. RateLimited/EvaluationUnavailable `_run` exit 2 verir ve report yazmaz: attempt meta/başarısızlık kaydı dış receipt ile korunmalı, kaybolmuş JSON başarı sayılmaz. `--enforce` acceptance fail için exit 1 üretir. Verifier shell timeout `SHELL_TIMEOUT_S=120`; agent için CLI seviyesinde timeout bayrağı yok. `_run_suite_and_close` browser cleanup finally çağırır, ancak tüm job/effect iptalinin kanıtı değildir.

K `<kok>/rapor.json`, `<kok>/<alan>-<tekrar>/surucu.json`, `cekirdek.err`, `olaylar.jsonl` yollarını üretir. `RunRecord.inspection` aggregate içinde; ayrı inspection.json uydurulmaz. Explicit engine `comparison-proof.json`/config evidence yolları mevcut engine/run_manifest otoritesine bağlıdır. Preflight disk >=5 GB + declared executable + gerçek model probe (240 s) yapar; hazırlıkta çalıştırmak zaten canlı model çağrısı olur.

K driver tur süreleri tabloda kaynak sabitleridir; dış `_drive` communicate sınırı alan+`DRIVER_GRACE_S=120`. Timeout dış sürücüyü kill/wait yapar; child cleanup veya external job cancellation tamamlandı iddiası taşımaz. D normal finally önce core stdin kapatır, 20 s bekler, sonra kill/wait eder; CLI'da task-scoped cancel bayrağı yok. Operator Ctrl-C/kill sahipli task/effect iptali makbuzu değildir. Sonraki kabul iptalinde ürünün mevcut owned cancel otoritesi, pending/partial receipts ve dış etki observation ayrıca bağlanmalı; bitmiş dış iş kör retry edilmez.

## Açık uygulama işleri ve iddia sınırı

1. Mevcut EvalTask/Area/RunRecord/report içinde kriter sürümü, public input/output digest, authoritative outcome, task/effect receipts, interventions ve human evidence refs additive bağlanmalı. Yeni engine veya ayrı başarı hesaplayıcı yok.
2. L02/L04/L05/L06/L07/L08/L12 eksik canlı fixture/inspector yüzeyleri tasarlanmalı; mevcut dar production işleri gerçek adı/kapsamıyla kalmalı. İnsan rubriği gözleyen/zaman/build/task/criterion refs ve dolu ölçütlerle ayrı record olmalı.
3. Source regression ve evaluator false-positive düzeltmesi ayrı kanıtla yürütülmeli; root manual output düzeltmesi Fusion başarısına dönüştürülmemeli. Unavailable/invalid/teacher-assisted ayrı tutulmalı; missing usage unknown kalmalı.
4. `evals.cli::_matrix` `_run` için kurduğu Namespace içinde `enforce` alanını vermiyor; `_run` bu alana başarısız acceptance sonunda erişiyor. Bu statik şüphe ürün/test çalıştırılmadan kaydedildi; matrix command hazır/güvenli karşılaştırma yolu sayılmadı. P komutu mevcut explicit `--enforce` yolunu kullanır.
5. Günlük kullanım kararı; false success, data loss, duplicate/wrong-target/unapproved effect ve failed/partial/unavailable attempt tablosu dolmadan verilemez. Site/game/video output'u gerçek Fusion tarafından sıralı üretilmeden, viewport/kare/etkileşim ve insan rubriği incelenmeden P14 complete veya “ChatGPT yerine kullanılabilir” iddiası yok.

Değişen tek dosya bu rapordur; test/ürün gate sonucu yoktur. API/data migration yapılmadı. Hazırlık burada durur; P13 complete ve root'un açık ürün yetkisi beklenir.

Hazırlık RED testleri ürün kabulü veya tamamlanma kanıtı değildir. Bu paket çalışma ağacındaki yeni testler yalnız bu pakette etkinleşir; sonraki paketlerin bilinçli RED testlerini bu kapıya katma. Gerçek full-suite kapsamını/exclusion nedenlerini kaydet.
