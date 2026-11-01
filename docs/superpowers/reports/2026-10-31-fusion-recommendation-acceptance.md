# Fusion önerileri kabul durumu

**Son güncelleme: 2026-11-01 — yerel yazılım doğrulaması tamamlandı; iki canlı kabul açık.** Bu derleme anında F01–F36 için **34/36 görev kapsamlı kabul** vardır. Açık maddeler yalnız F03’ün gerçek 200 kaydı ve F06’nın gerçek 100 olumlu örneği için canlı kabuldür. F04’ün yerel kod/referans kabulü Task 6b FIX2 bağımsız incelemesiyle onaylandı; canlı baseline ayrıca ölçülmedi. F31 FIX1 onaylandı; F13, IN02 Fix2 sonrasında yeniden kabul edildi. Bu sayı canlı başarı, bütün dal onayı, commit veya kurulum sayısı değildir.

Başlıklar chat kökündeki `outputs/fusion-oneriler.json` ile birebirdir. Çağrı noktaları mevcut kaynakta tanım ve çağıran üzerinden kontrol edildi; `core/original_trace.py` protokolü tek başına çalışan üretici diye sayılmadı. Dosya ve işlev adları mevcut kaynakta yeniden doğrulandı; kayabilecek satır numaraları kaldırıldı. Test sayıları adlandırılan kayıtların kendi kapsamıdır; birbirine eklenmez. Bu belge hazırlanırken test veya canlı araştırma çalıştırılmadı.

[CFG], gerçek `RuntimeConfig` alanları ile paket varsayılanlarını; [MODEL], model/çalıştırma politikasının opsiyonel alanlarını gösterir. `False`/`True` Python değeridir; YAML karşılığı `false`/`true` olur. Kapatma alanı olmayan doğruluk düzeltmeleri normal yoldadır; geri alması commit sonrası ilgili diff’in revert’idir. Teslim kaynağı, koordinatörün kaydettiği Git commit’iyle tanımlanır; görev provenance’ı aşağıdaki dondurulmuş ürün farkına bağlıdır. Bir özelliği kapatmak daha önce yazılmış kalıcı veriyi otomatik geri almaz.

| ID | Kanonik öneri | Gerçek üretim dosyası ve işlevi | Kod / inceleme / test kapsamı | Gerçek varsayılan, geri alma ve kabul sınırı |
|---|---|---|---|---|
| F01 | JSON onarımında metin içeriğini koru | `src/fusion_cli/core/tool_emulation.py:parse_tool_calls` | Task 1 [R1] onaylı: 133-test kayıt kapsamı; ayrı 800 dize, 7 ret ve 9 şema kontrolü. Dize dışı onarım doğrulandı. | Normal JSON parse yolu; onarımda metin koruması Task 1 diff’iyle değişir. Geri alma commit sonrası bu diff’in revert’i (hash bekliyor). |
| F02 | Şema doğrulama alt kümesini açık ve doğru yap | `src/fusion_cli/tools/emulation.py:validate_arguments` | Task 1 [R1] onaylı: aynı 133-test kapsamı; yanlış tür/eksik alan ve desteklenen alt küme sınandı. Tam JSON Schema desteği iddiası yok. | Normal şema doğrulama yolu; ayrı flag yok. Geri alma commit sonrası Task 1 doğrulama diff’inin revert’i (hash bekliyor). |
| F03 | Kayıtlı web yanıtlarından araç protokolü regresyon korpusu kur | `evals/cli.py:_emulation_replay`; `src/fusion_cli/tools/emulation_corpus.py:load_corpus` | Task 3 [R3] ve capture/admission [R13] kodu onaylı. Gerçek kayıt **0/200**, gerekli 160/40 ayrımı **OPEN**. | Yalnız açık replay/capture komutuyla çalışır; genel feature flag yok. Replay durdurulabilir; kod geri alma Task 3/13 diff revert’i (commit hash bekliyor). Gerçek kayıt **0/200**, 160/40 ayrımı OPEN. |
| F04 | Bağımsız yerel eval ve ölçüm tabanını dondur | `evals/metrics.py:score_task`; gerçek çalıştırıcı `evals/agent_runner.py:run` | Task 6a [R6a] ve 6b FIX2 [R6b] onaylı. 32 insan referansı, 16/8/8 split, 18 runtime senaryosu mevcut. Dört özgün ve iki kalan/yeni bulgu kapalı; 142 hash eşleşmiş, 10 seçili test ve ayrı 6 loader kontrolü doğrulanmış. | Eval açık komutla başlar. Çalıştırmayı durdurmak ölçümü kapatır; kod geri alma Task 6 diff revert’i commit sonrası. Yerel kod/referans kabulü onaylı; kaynaktaki `task6_complete=false`, `live_baseline=null` canlı baseline ölçülmediği için korunur. |
| F05 | Karma ayrıştırma sonucunda kayıp çağrıyı görünür kıl | `src/fusion_cli/core/tool_emulation.py:parse_tool_calls` | Task 3 [R3] onaylı: karma parse uyarısı public provider/loop hattında taşınır; mutation erteleme ve hedefli onarım testli. | Normal parser→provider→loop uyarı yolu; ayrı flag yok. Geri alma Task 3 diff revert’i commit sonrası (hash bekliyor). Gerçek taşıma korpusu F03’e bağlı. |
| F06 | Örnek amaçlı araç bloğunun eyleme dönüşmesini sınırla | `src/fusion_cli/core/tool_emulation.py:parse_tool_calls` | Task 13 [R13] kod onayı: 49 covering-test kaydı; ayrı 8 hedefli test. V1-only kapanış reddi ve eşleştirilmiş V2 recall sınırı doğrulandı. | `runtime.emulation_protocol="v1"` [CFG]; V2 yalnız `"v2"` seçilirse. Geri alma `"v1"`. Gerçek pozitif **0/100**, F03 **0/200**; DOM/recall kabulü OPEN. |
| F07 | Araç yüzeyini görev aşamasına ve erişilebilirliğe göre sırala | `src/fusion_cli/engines/agent/loop.py:_publish_surface` | Task 8b [R8] onaylı: gerçek discovery/LOCALIZE ve flag-off davranışı. 259-test teslim kaydı; ayrı 14 seçili inceleme testi. | `runtime.external_tool_selection="registration_order"` [CFG]. Deneysel sıralamadan geri alma bu değere dönmek; erişim/policy sınırı korunur. |
| F08 | Hata yerelleştirmesini ölçülen bir ara ürün yap | `src/fusion_cli/engines/agent/loop.py:_run_tools` | Task 8b [R8] onaylı: source digest/kriter kimliği, top5 ve 8192 karakter sınırı; gerçek search ve kontrollü LSP üreticileri sınandı. | `runtime.localization_cards=False` [CFG]; geri alma `False`. Canlı hata yerelleştirme doğruluğu artışı ölçülmedi. |
| F09 | Hata düzeltmede kırmızı→yeşil davranış kanıtı iste | `src/fusion_cli/engines/agent/reproduction.py:evaluate_reproduction`; çağıran `src/fusion_cli/engines/agent/step_verification.py:_evaluate_check` | Task 5 [R5] onaylı: gerçek pytest→checkpoint→final hattında komut/hedef/ortam bağı. 155 scoped-test kaydı; ayrı 16-test fix kontrolü. Eval süreç kabulü bağı [R6b] FIX2 incelemesinde ayrıca kapatıldı. | Normal REPRODUCTION kriter yolu; ayrı flag yok. Geri alma Task 5 diff revert’i commit sonrası (hash bekliyor). |
| F10 | Tamamlanmayı kabul maddesi–kanıt matrisiyle kapat | `src/fusion_cli/engines/agent/completion_evidence.py:evidence_payload`; çağıran `src/fusion_cli/engines/agent/plan_runner.py:_turn_report` | Task 5 [R5] onaylı: criterion/step kimliği ve PASSED/FAILED/UNVERIFIED istemciye taşınır. 155 scoped-test kaydı; genel başarı beyanı kriteri yükseltmez. | Normal TurnReport/istemci kanıt projeksiyonu; ayrı flag yok. Geri alma Task 5 diff revert’i commit sonrası (hash bekliyor). |
| F11 | Sıkıştırma sonrası aktif iş durumunu yeniden doğrula | `src/fusion_cli/engines/agent/loop.py:_compact_before_call` | Task 9b [R9] onaylı: 113-test runtime kaydı; ayrı 11-test inceleme seçimi. İki compaction yolu, aktif kriter ve kullanıcı mesajı koruması sınandı. | `runtime.context_restore_state=False` [CFG]; geri alma `False`. Gerçek web konuşma devri ölçülmedi. |
| F12 | Maskelemede sonluk yanında kanıt değerini kullan | `src/fusion_cli/engines/agent/context_projection.py:_bounded_evidence` | Task 9b [R9] onaylı: aynı 113-test bağlam kapsamı. Son assistant grubunun bütün paralel sonuçları ve kanıt bütçesi testli. | `runtime.context_evidence_pins=False` [CFG]; geri alma `False`. Mevcut `runtime.tool_output_window=8`; yeni kanıt pinleme bu pencereden ayrıdır. |
| F13 | Özeti tekrar özetlemek yerine orijinal izden yeniden kur | `src/fusion_cli/memory/turn_journal.py:read_original`; çağıran `src/fusion_cli/engines/agent/context_projection.py:compact_context` | Task 9b [R9] ve journal temeli [R9a] onaylı. [IN02] numeric/nested ve eski secret alias düzeltmesini onayladı; F13 yeniden kabul edildi. IN02: 46 covering kayıt; ayrı 9 gerçek journal testi. | `runtime.context_original_trace=False` [CFG]; geri alma `False`. Kaynak kapsamı eksikse açık fallback; tam ham geçmiş vaadi yok. Canlı kalite bilinmiyor. |
| F14 | Bağlam eşiğini Türkçe ve görev doğruluğuyla kalibre et | `src/fusion_cli/engines/agent/loop.py:_effective_threshold` | Task 9b [R9] onaylı: yanlış model/sağlayıcı profili uygulanmaz ve manifestte etkin görünmez. 113-test bağlam kapsamı. | Boolean flag yok: `ModelSpec.context_profile=None` [MODEL]; geri alma profili `None` yapmak. Mevcut `runtime.weak_model_compaction_ratio=0.2` [CFG]. Türkçe 4k/8k/16k canlı kalibrasyonu OPEN. |
| F15 | İstem bütçesinde kural kaybını görünür yap | `src/fusion_cli/core/prompt_manifest.py:PromptManifest`; üretici `src/fusion_cli/engines/agent/prompt_manifest.py:publish_manifest` | Task 9b [R9] onaylı: gerçek request/transport ölçümü, estimated/unknown ayrımı ve sistem altbileşenleri testli. 113-test bağlam kapsamı. | `runtime.prompt_manifest=True` [CFG]; geri alma `False`. Manifest ölçümdür; canlı görev kazanımı ölçülmedi. |
| F16 | Ders erişimini çağrı sayısı yerine yararla değerlendir | `src/fusion_cli/engines/agent/lesson_attribution.py:settle` | Task 10b/11 [R10] onaylı: gerçek Lesson.id, offered/use/outcome ve bilinmeyen kullanım ayrımı. İlk incelemenin ders kabulü fix incelemesinde korunur. | `runtime.lesson_recall_hints=False`, `runtime.lesson_attributed_feedback=False` [CFG]. Geri alma: ilgili alanları `False` yapmak deneysel ipucu/atıf yolunu kapatır; canlı ders yararı ölçülmedi. |
| F17 | Ders güvenini yalnız tur sonucuna bağlamayı gevşet | `src/fusion_cli/engines/agent/lesson_attribution.py:settle` | Task 10b/11 [R10] onaylı: kapanışta tek settlement, kimlikli çağrı/kriter bağı ve ilgisiz sağlayıcı hatasının dersi cezalandırmaması doğrulandı. | `runtime.lesson_attributed_feedback=False` [CFG]; geri alma `False`. Başarılı tur tek başına ders faydası sayılmaz; gerçek model etkisi bilinmiyor. |
| F18 | Çelişkili ve eskimiş dersleri sürümle karantinaya al | `src/fusion_cli/memory/lessons.py:set_quarantined` | Task 10a temeli ve 10b/11 runtime [R10] onaylı: sürüm/split/source ve karantina gerçek store/caller hattında. Kayıt geri alma ayrı store işlevinde mevcut. | `runtime.lesson_conflict_quarantine=False` [CFG]; geri alma `False`. Ayar mevcut karantina kayıtlarını silmez; kayıt geri alma `set_quarantined(..., quarantined=False)` yoludur. |
| F19 | Başarılı rutinleri sınanmış küçük beceriye dönüştür | `src/fusion_cli/engines/agent/routine_observer.py:stage_routine`; çağıran `src/fusion_cli/engines/agent/plan_runner.py:finish` | Task 10b/11 [R10] onaylı: altı public routine testi gerçek producer→store→CLI apply→registry/invoker→dosya executor yolunu doğruladı. Stale/checkpoint replay yeni proof sayılmaz. | `runtime.verified_skill_proposals=False` [CFG]; geri alma `False` ile yeni önerileri kapatmak. Önceden açıkça uygulanmış beceri ayrı kalıcı kayıttır; flag onu silmez. |
| F20 | Alt ajan devrinde tüm geçmiş yerine kanıt paketi kullan | `src/fusion_cli/engines/agent/evidence_handoff.py:compile_handoff`; çağıran `src/fusion_cli/engines/agent/team.py:run_subagent` | Task 11 [R10] onaylı: bounded paket, parent TurnBudget/InvocationBudget ve write/read sınırları. Ayrı süreçte paylaşılamayan parent bütçesi açık reddedilir. | `runtime.subagent_context_mode="existing"` [CFG]; `"evidence_bundle"` opt-in. Geri alma `"existing"`; canlı bütçeli görev kolu ölçülmedi. |
| F21 | Kod aramasında lexical aday havuzunu bağımsız üret | `src/fusion_cli/memory/code_index.py:_lexical_candidates_for`; kurulum `src/fusion_cli/memory/factory.py:build_memory` | Task 7b [R7] onaylı: config→factory→gerçek indeks aday birleşimi. 331-test temel runtime kaydı; fix’in ayrı 46-test kaydı aynı toplam değildir. | `runtime.code_lexical_candidates=0` [CFG]; bu ağırlık değil aday tavanıdır. Geri alma `0`; gerçek embedding/model kazancı ölçülmedi. |
| F22 | Sabit satır blokları yerine sembol sınırında parçala | `src/fusion_cli/memory/chunking.py:chunk_text`; çağıran `src/fusion_cli/memory/code_index.py:_reindex` | Task 7a güvenli okuma ve 7b factory bağlantısı [R7] onaylı: AST chunk, lines/legacy kimlik uyumu ve gerçek indeks etkisi doğrulandı. | `runtime.code_chunk_strategy="lines"` [CFG]; `"symbols"` opt-in. Geri alma `"lines"` ve stratejiye uygun yeniden indeksleme; canlı kod görevi kazanımı bilinmiyor. |
| F23 | LSP tanım/başvuru ve diagnostics’i dar araç yüzeyiyle ekle | `src/fusion_cli/engines/agent/loop.py:_run_tools` | Task 8b [R8] onaylı: kontrollü LSP definition/reference/diagnostics, izinler, snapshot güncelliği ve sır maskeleme. 259-test teslim kaydı; ayrı 14 seçili test. | `runtime.symbol_query_enabled=False`, `runtime.lsp_server.command=[]` [CFG]. Geri alma `False` ve boş komut; gerçek kullanıcı LSP sunucusu kabulü yapılmadı. |
| F24 | Depo haritasını sorguya göre yeniden sırala | `src/fusion_cli/engines/agent/loop.py:_repo_map_for_turn` | Task 7b [R7] onaylı: 149 karakterlik Türkçe görevde açık sembol gerçek run_agent haritasında öne alınır. 46-test fix kaydı; ayrı 17-test inceleme seçimi. | `runtime.repo_map_focused=False` [CFG]; geri alma `False`. 32 sorguluk yerel Chroma replay sentetik mekanizma kanıtıdır; model başarısı değildir. |
| F25 | Düzenleme biçimini doğrulanmış model profiliyle seç | `src/fusion_cli/engines/agent/loop.py:_call_model`; politika `src/fusion_cli/engines/agent/execution_policy.py:policy_for` | Task 12b ilk incelemesinde F25 PASS; [R12b] kararı korur. 24 düzenleme fixture’ı iki biçimde 48 yerel uygulama; gerçek outgoing tercih ve executor guard testli. | `ModelSpec.recommended_edit_format=None`, `ExecutionPolicy.edit_format=None` [MODEL]. `"exact"`/`"whole"` opt-in; geri alma tavsiyeyi `None` yapmak. Canlı format üstünlüğü ölçülmedi. |
| F26 | Çok dosyalı yamayı işlem olarak dene ve geri al | `src/fusion_cli/engines/agent/plan_runner.py:restore_changes`; `src/fusion_cli/core/changeset.py:restore` | Task 12a [R12a] onaylı: 75-test fix kaydı. Snapshot/sahiplik çakışması ve çok turlu rewind korumaları mevcut üretim yolunda doğrulandı. | Mevcut ChangeSet/undo/rewind yolu + doğrulandı; yeni kapatma flag’i yok. Kod geri alma Task 12a diff revert’i commit sonrası (hash bekliyor). Shell sahipliği ve disk I/O için atomik transaction garantisi yok. |
| F27 | Test seçimini bağımlılık kapsamı ve emniyet örneğiyle yap | `src/fusion_cli/engines/agent/verify_discovery.py:related_test_command` | Task 5 [R5] onaylı: bağımlılık/fixture belirsizliğinde tam komuta dönüş ve flag-off cache ayrımı. 155-test scoped kayıt. | `runtime.related_test_selection=False` [CFG]; geri alma `False`. Yalnız ara Python/pytest kapısı daralır; final tam doğrulama yoludur. |
| F28 | Aynı modelden en çok iki yamayı testlerle seç | `src/fusion_cli/engines/agent/attempts.py:choose_attempt`; çağıran `src/fusion_cli/engines/agent/plan_runner.py:run_candidates` | Task 12b [R12b] onaylı: 148-test fix kaydı; ayrı 14 seçili test ve gerçek motor karşı örnekleri. Görev finali ve bağımsız ikinci aday kanıtı metrikleri sınırlar. | Eval `--attempt-arm` varsayılanı `None` [ARM]; `candidates` veya `serial` açık seçilir. Geri alma argümanı kaldırmak. İki slot ortak sabit çağrı tavanını paylaşır; canlı A/B yok. |
| F29 | Sıkışmayı yeni kanıt ve hata ailesi üzerinden değerlendir | `src/fusion_cli/engines/agent/progress.py:progress_fingerprint`; çağıran `src/fusion_cli/engines/agent/plan_runner.py:run_step` | Task 4 [R4] onaylı: 142-test fix kapsamı. Yeni kanıt ve hata ailesi mevcut recovery ilerleme parmak izine girer. | Normal recovery/parmak izi yolu; ayrı flag yok. Geri alma Task 4 ilerleme diff revert’i commit sonrası (hash bekliyor). |
| F30 | Test kanıtının anahtarına ortam ve bağımlılık kimliğini kat | `src/fusion_cli/engines/agent/gate_cache.py:workspace_key`; çağıran `src/fusion_cli/engines/agent/step_verification.py:_gate_result` | Task 4 [R4] onaylı: 142-test fix kapsamı. Üst/ara dizin config ve lock değişimi gerçek pytest kapısını yeniden ölçtürür. | Normal gate/cache anahtarı yolu; ayrı flag yok. Geri alma Task 4 cache diff revert’i commit sonrası (hash bekliyor). Eski ortam başarısı yeni ortama taşınmaz. |
| F31 | İstem optimizasyonunu kör setli küçük evrime çevir | `src/fusion_cli/cli/prompt_opt_commands.py:run_round_command` | Task 14 FIX1 [R14] **onaylı**: H1/H2/M1 kapalı. 75 covering-test kaydı; ayrı 13 taze inceleme kontrolü. [IN03] iki satırlık gerçek mutating producer bağı ayrıca doğrulandı. | Otomatik etkinleşme flag’i yok; açık `prompt-opt calistir`, `--aday=3`, üst sınır 4 [OPT]. Komut proposal kaydeder; uygulama ayrıdır. Prompt geri alması mevcut `prompt-opt geri-al`; kod geri alma commit sonrası Task 14 diff revert’i. Canlı dev/validation ve final kör sekiz görev yapılmadı. |
| F32 | Olay kaydını eksiksiz korelasyon ve gözlenebilir paydalarla güçlendir | `src/fusion_cli/observability/json_sink.py:_fields` | Task 3 [R3] onaylı: receipt/call/turn/candidate korelasyonu ve replay. Callback arızası için 19-test son fix kaydı; gerçek CLI wire/JSONL/sink kimlik eşliği önceki fix’te doğrulandı. | Korelasyon normal event yoludur; yeni boolean flag yok. JSON çıktı mevcut `--json` ile seçilir. Kod geri alma Task 3 diff revert’i (commit hash bekliyor); eksik ölçüm null kalır. |
| F33 | Sabit model modunu değerlendirmede zorunlu tut | `evals/profiles.py:prepare_eval_config` | Task 6a [R6a] ve koşullu otomatik fallback düzeltmesi [IN01] onaylı. IN01: dört taze kontrol ve önceki 48-test kapsamı. F33 kod kabulü F04 toplam kabulünden ayrıdır. | Açık eval yolu strict tek model kurar: `teacherless=True`, `teacher=None`, `tiers=()`, `auto_web_fallback=False`. Kullanıcı config’i yazılmaz. Geri alma eval’i durdurmak; kod geri alma Task 6/IN01 diff revert’i commit sonrası. |
| F34 | Öğretmeni küçük tanı paketine ve açık kotaya bağla | `src/fusion_cli/engines/agent/engine_tools.py:_ask_teacher_tool`; `src/fusion_cli/engines/agent/teacher_brief.py:compile_brief` | Task 11 [R10] onaylı: tavsiye aynı linked FAILED→PASSED kriterle terfi eder. Fix incelemesinin ayrı 14 seçili testi öğretmen/review varyantlarını kapsar. | `teacher` varsayılanı yok; `runtime.teacher_max_brief_chars=25000`, `teacherless=False` [CFG]. Geri alma/kapatma: `teacherless=True` veya `teacher` seçimini kaldırmak. Mevcut tur kotası korunur; tek danışmalı canlı fayda kolu OPEN. |
| F35 | Çalışma ortamını görevden önce küçük bir tanı ile ayır | `src/fusion_cli/engines/agent/verify_discovery.py:evidence_environment` | Task 4 [R4] onaylı: 142-test fix kapsamı. Ortam/sağlayıcı arızası ürün kusurundan ayrılır; karma kapıdaki gerçek web kusuru mevcut tek onarım hakkını korur. | Normal verification ortam tanısı; ayrı flag yok. Geri alma Task 4 ortam diff revert’i commit sonrası (hash bekliyor). Canlı ortam karşılaştırması ölçülmedi. |
| F36 | Bağımsız son incelemeyi dar diff ve karşı örneğe odakla | `src/fusion_cli/engines/agent/review.py:review_turn`; çağıran `src/fusion_cli/engines/agent/loop.py:_self_review` | Task 11 [R10] onaylı: gerçek root caller güncel verification/kriter/hata aktarır. Üç özgün karşı örnek ve ayrı 14 seçili fix testi; tek judge ve timeout→None korunur. | `runtime.review_diff_only=False`; mevcut `runtime.self_review=True` [CFG]. Yeni dar review’dan geri alma `review_diff_only=False`; review’u tümden kapatmak `self_review=False`. Precision/ek çağrı ve canlı yarar ölçülmedi. |

## Son kapılar ve ölçüm sınırı

- F04’ün 32 insan referansı **16 development / 8 validation / 8 blind** olarak uygulanmıştır; ilk 14 dosya sözleşmesine 18 runtime senaryosu eklenmiştir. Referansların geçmesi model skoru değildir. Task 6b FIX2 [R6b] yerel kod/referans kabulünü onaylamıştır: dört özgün ve iki kalan/yeni bulgu kapalıdır. Bu yerel onay canlı baseline ölçümü değildir; `task6_complete=false` ve `live_baseline=null` korunur.
- F03 genuine **0/200**, F06 genuine olumlu **0/100**. 200 sentetik negatif gerçek kayıt değildir. Eşleştirilmiş canlı recall, DOM pilotu, dondurulmuş canlı baseline, dev/validation A/B ve final kör sekiz görev sonucu bilinmiyor. F14 Türkçe eşik, F25 canlı format, F34 tek öğretmen ve F36 review precision kazanımları ayrıca ölçülmedi.
- UI tipografi ve video yer tutucusu/vaadinin kaldırılması [R2] ile onaylıdır; Remotion korunmuştur. Son [frontend kapısı][FG] Node 22 altında lint, **276 dosyada 2233 test** ve build için exit 0 kaydeder. Font public lisans varlıklarının gerçek build çıktısına dağıtımı [FONT] ile ayrıca onaylıdır. Native paketleme veya kullanıcı kurulumunu kapsamaz.
- İlk [tam Python statik kapısı][PG] mypy için **5 dosyada 9 hata**, lint/format için exit 1 kaydetmiştir; IN04 düzeltmesi [IN04] onaylıdır. [Güncel tam Python kapısı v5][PG5] metadata, Ruff, format, mypy ve pytest için **exit 0** kaydeder. Tam pytest sonucu: **12954 passed / 0 failed / 0 errors / 6 skipped / 7 warnings**; stdout özeti ile JUnit toplamları eşleşir. Koşu 6 işçi ve `--maxfail=0` ile tamamlanmıştır.
- Önceki [v3 tam koşu][PG3] **8916 passed / 1 failed / 2 skipped** sonrasında Remotion hint yolunun kırpılması nedeniyle kesilmiştir; başarı sayılmaz. [Remotion FIX1 incelemesi][REM3] 3995→3186 karakter kısaltmayı ve dört kurulum-yolu vakasını onayladı. Son FIX2 yalnız `asla ` sözcüğünü geri koyar: beceri 3191 karakter, sınır 4000 karakter; gerçek 700 karakter kurulum yolunda hint boyları 3867/3969 karakterdir.
- [V4 tam koşu][PG4] **12943 passed / 11 failed / 6 skipped**, exit 1 ile tamamlanmıştır. On bir hata üç donmuş pakette düzeltildi: bir branding vakası için beş karakterlik `asla ` geri eklemesiyle Markdown FIX2; üç runtime test dosyasında yedi hatanın gerçek request/policy uyumuyla giderilmesi; iki REPL/TUI test dosyasında üç hatanın `record_applied` ve `TERM` uyumuyla giderilmesi. Bu sayılar yeni v5 sonucu yerine geçmez. [V4 runtime/Remotion incelemesi][REM4] iki paketi, [REPL/undo incelemesi][REPL4] üçüncü paketi bağımsız olarak SPEC PASS / QUALITY APPROVE ile onayladı; bu kesin deltalarda yeni engelleyici bulgu yoktur.
- V4’teki mevcut altı skip: desteklenmeyen bir `npm -v` parametre kontrolü, resmi ağ erişimi gerektiren bir wheel kontrolü ve macOS’ta `csc` bulunmadığı için dört Windows native adapter kontrolüdür. Yeni skip/xfail eklenmedi; bunlar geçirilmiş test diye sayılmaz.
- Tam Python sonucu mevcut macOS yorumlayıcısı, Node 22 ve yerel Playwright önbelleğiyle, ağ engelleme/çevrimdışı harness ortamında alınmıştır. Mevcut altı skip yukarıdaki kapsam sınırlarıdır; resmi ağdan wheel kurulumu ve macOS’ta bulunmayan Windows `csc` adapter doğrulaması bu geçişin kapsamına girmez. Gerçek sağlayıcı/model başarısı, canlı baseline veya kullanıcı kurulumu ölçülmemiştir.
- [Bütün dal FIX1 incelemesi][WB] kod/spec entegrasyonunu onayladı; **WB-01/WB-02/WB-03 kapalıdır**. Ayrı [uyumluluk][COMPAT], [boş dosya okuma/yazma bütünleşmesi][EMPTY] ve [font lisansı dağıtımı][FONT] incelemeleri de onaylıdır. Bu onaylar tam pytest sonucu veya canlı model kazanımı değildir. Taşıma/devam kaydı, nihai kapı sonucu ve commit koordinatördedir. **Kullanıcı kurulumu: 0.** Teslim edilen kaynak için koordinatörün kaydettiği Git commit’i esas alınır.
- [Son ürün envanteri][INV5] onaylı hash’lerle eşleşen **518 ürün yolu ve sıfır beklenmeyen drift** kaydeder; bu rapor ayrı 519. teslim yoludur. Dondurulmuş ürün farkı SHA-256: `79729eda85ac9b367fff5b0f8071f90dddc6090048166bd08970d7eab4f9ac59`. Teslim kaynağını koordinatörün kaydettiği Git commit’i tanımlar; bu rapor kendine ait commit hash’i üretmez. Kullanıcı kurulumu ve main’e push yapılmamıştır.
- Ayrı 453 öneri kümesinde **uygulanan 0**; HIGH parity listesinin **83/83** maddesi incelenmiştir. İnceleme sayısı uygulama sayısı değildir.

## Kanıt dizini

İncelemeler kendi before→after diff/manifest ve ham test kayıtlarını adlandırır; global çalışma ağacı farkı tek bir göreve mal edilmez. Sonraki fix incelemesi önceki olumlu kapsam kararını koruduğunda tabloda bu birleşik karar esas alınmıştır.

- [CFG]: `src/fusion_cli/config/defaults.yaml`.
- [MODEL]: `src/fusion_cli/core/types.py`.
- [ARM]: `evals/cli.py`.
- [OPT]: `src/fusion_cli/cli/prompt_opt_commands.py`.
- [R1]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-1-review.md`.
- [R2]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-2-review.md`.
- [R3]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-3-fix-2-review.md`.
- [R4]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-4-fix-2-review.md`.
- [R5]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-5-fix-2-review.md`.
- [R6a]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-6a-fix-2-review.md`.
- [R6b]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-6b-fix-2-review.md`.
- [R7]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-7b-fix-1-review.md`.
- [R8]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-8b-fix-1-review.md`.
- [R9]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-9b-fix-1-review.md`.
- [R9a]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-9a-fix-2-review.md`.
- [R10]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-10b11-fix-1-review.md`.
- [R12a]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-12a-fix-1-review.md`.
- [R12b]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-12b-fix-1-review.md`.
- [R13]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-13-fix-1-review.md`.
- [R14]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-14-fix-1-review.md`.
- [IN01]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/integration-01-fix-1-review.md`.
- [IN02]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/IN02-fix-2-review.md`.
- [IN03]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/IN03-report.md`.
- [FG]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/final-frontend-gate/checks.json`.
- [PG]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/final-python-static/checks.json`.
- [IN04]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/IN04-review.md`.
- [PG2]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/final-python-gate-v2/checks.json`.
- [WB]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/final-whole-branch-fix1-review.md`.
- [COMPAT]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/whole-fix1-compat-review.md`.
- [EMPTY]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/empty-read-integration-review.md`.
- [FONT]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/font-license-distribution-review.md`.
- [PG3]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/final-python-gate-v3/checks.json`.
- [PG4]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/final-python-gate-v4/checks.json`.
- [PG5]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/final-python-gate-v5/checks.json`.
- [REM3]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/gate-v3-remotion-review.md`.
- [REM4]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/gate-v4-runtime-remotion-review.md`.
- [REPL4]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/gate-v4-repl-undo-review.md`.
- [INV5]: `.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/final-stage-inventory-v5-report.md`.

[CFG]: ../../../src/fusion_cli/config/defaults.yaml
[MODEL]: ../../../src/fusion_cli/core/types.py
[ARM]: ../../../evals/cli.py
[OPT]: ../../../src/fusion_cli/cli/prompt_opt_commands.py
[R1]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-1-review.md
[R2]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-2-review.md
[R3]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-3-fix-2-review.md
[R4]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-4-fix-2-review.md
[R5]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-5-fix-2-review.md
[R6a]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-6a-fix-2-review.md
[R6b]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-6b-fix-2-review.md
[R7]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-7b-fix-1-review.md
[R8]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-8b-fix-1-review.md
[R9]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-9b-fix-1-review.md
[R9a]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-9a-fix-2-review.md
[R10]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-10b11-fix-1-review.md
[R12a]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-12a-fix-1-review.md
[R12b]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-12b-fix-1-review.md
[R13]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-13-fix-1-review.md
[R14]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/task-14-fix-1-review.md
[IN01]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/integration-01-fix-1-review.md
[IN02]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/IN02-fix-2-review.md
[IN03]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/IN03-report.md
[FG]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/final-frontend-gate/checks.json
[PG]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/final-python-static/checks.json
[IN04]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/IN04-review.md
[PG2]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/final-python-gate-v2/checks.json

Tipli alanlar ayrıca `src/fusion_cli/config/models.py:RuntimeConfig` üzerinden karşılaştırıldı. Model tercihi ve çalışma politikası alanları `src/fusion_cli/engines/agent/execution_policy.py:ExecutionPolicy` içinde doğrulandı.

[WB]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/final-whole-branch-fix1-review.md

[COMPAT]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/whole-fix1-compat-review.md

[EMPTY]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/empty-read-integration-review.md

[FONT]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/font-license-distribution-review.md

[PG3]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/final-python-gate-v3/checks.json

[PG4]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/final-python-gate-v4/checks.json

[PG5]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/final-python-gate-v5/checks.json

[REM3]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/gate-v3-remotion-review.md

[REM4]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/gate-v4-runtime-remotion-review.md

[REPL4]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/gate-v4-repl-undo-review.md

[INV5]: ../../../.superpowers/sdd/2026-10-31-fusion-zeka-tipografi/final-stage-inventory-v5-report.md
