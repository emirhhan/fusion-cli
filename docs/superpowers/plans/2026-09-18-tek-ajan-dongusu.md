# Faz 2 — Tek Ajan Döngüsü: Uygulama Planı

> **Ajanlar için:** Bu plan görev görev uygulanır. Önerilen beceri `superpowers:subagent-driven-development`; alternatifi `superpowers:executing-plans`. Adımlar `- [ ]` ile işaretlenir.

**Onaylanan kararlar (18 Eylül):** §6'daki beş açık kararda önerilen seçenekler uygulanır (gözlem kilidi `workspace_read` ile; görünür geri alma; harness testi zorla çalıştırmaz, rapor dürüstçe söyler; `self_review` yalnız değişiklik turunda; `classify.py` yalnız `/profil otomatik` için kalır). Kullanıcı aksini söylerse görev yeniden açılır.

**Kaynak:** 17 Eylül denetimi, `docs/superpowers/plans/2026-09-17-claude-paritesi.md` "Faz 2". Kod 18 Eylül 2026'da okundu. Dal `fusion-runtime-hardening-20260827-022831`, HEAD `34b925e`. Çalışma ağacında başka bir ajanın commit edilmemiş değişiklikleri var: `loop.py`, `verification.py`, `step_verification.py`, `verify_discovery.py`, `tools/registry.py`, `tools/safety.py`, `tools/command_policy.py` ve diğerleri. Bu plan o dosyaların son hâlini varsayar. Referanslar satır numarasıyla değil, fonksiyon adıyla verilir.

**Amaç:** Fusion ilk mesajdan son mesaja kadar Claude Code gibi davranmalı:
- Tek konuşma geçmişi olmalı.
- Ne zaman araç kullanacağına, ne zaman plan yapacağına (`todo_write`) model karar vermeli.
- Düzenleme tam metin eşleşmesiyle yapılmalı ve sonuç modele diff olarak dönmeli.
- Başarı beyanı gerçek komut çıktısına ve araç kaydına dayanmalı.
- Kullanıcı bir aracı reddederse tur durmalı ve kullanıcıya sorulmalı.
- Gözlem turunda yazma tamamen kapalı olmalı.

---

## 1. Bugünkü akış: bir kullanıcı mesajının izlediği yol

### 1.1 Giriş

- `appserver/session.py` (`tur.calistir` işleyicisi). Kip `_workspace_mode`'dan gelir: `chat_mode = _workspace_mode != "kod"`. Ardından `cli/session.py::run_agent_task` çağrılır.
- `cli/repl/loop.py::_drive_agent` ve `cli/repl/tui_loop.py` de aynı motoru çağırır.
- `cli/session.py::run_agent_task`: `AgentDeps` burada kurulur (`build_policy`, `build_verifier`, `JsonCheckpointStore`). Sonra `_run_agent_with_mcp` → `engines/agent/loop.py::run_agent` çağrılır.
- Tur bitince `NoFileChanges`/`FilesChanged` olayları `ToolContext.changes`'ten üretilir (bu doğru). Çağıran taraf `state.history = outcome.messages` yapar.

### 1.2 `loop.py::run_agent` içindeki sıra

1. `_new_budget`: tur bütçesi.
2. `playbook_stage.py::maybe_run_playbook`: opt-in, varsayılan kapalı.
3. `engine_tools.py::build_agent_registry`.
4. **`classify.py::classify_task_details(_scoped_task(task, history))`**
   - `_scoped_task`, geçmişteki ilk kullanıcı mesajını bu turun metniyle birleştirir.
   - **B2 kök nedeni:** "Tamam yaz" mesajı, oturumun ilk mesajının türünü (ör. FEATURE) miras alır ve karmaşık görev sayılır.
5. `providers/capabilities.py::infer_task_requirements`.
6. `effects/runner.py::maybe_run_effect_workflow`: deterministik git push akışı.
7. Bağlam enjeksiyonu (**A5/B5**). Hepsi sınıflandırmaya bağlıdır:
   - `skill_recall.should_auto_context(classification)`
   - `learning_steps.recall_lessons(scope=recall_scope(kind))`
   - `_recall_skill` → `skill_recall.auto_skill` + `auto_expertise_block` (`CapabilityActivated` yayınlar; WEBSITE türünde 21 KB'lık `web_reference.md` eklenir)
   - `repo_context.py::repo_map_block(root, kind)` (`loops.wants_plan(kind)` ile)
   - Bunlar `_initial_messages` ile birleşir.
8. `execution_policy.py::policy_for(config, spec, kind, task)`:
   - `kind` → `complex_task`; web'de bütçe kademesi 8/5, 90/75 ya da 150/130 olur.
   - `effects/detect.py::required_effect_for` bu turun metnine regex uygular.
   - `_is_genuine_simple_chat` → `offer_tools`.
   - Sohbet kipinde `chat_mode.py::chat_execution` çağrılır.
9. Mutasyon yeteneği kapısı (`MutationUnavailable`).
10. **`execution_route.py::choose_execution_route`**:
    - `workflow_mode: auto` iken `complex_task` + `loops.wants_plan(kind)` → `WORKFLOW` → `plan_runner.py::run_execution_plan(task, deps, run_agent)`. **Geçmiş verilmez.**
    - `FAST_PROMOTABLE` → önce `_drive` çalışır, sonra `_promotion_context` + `promotion.py::should_promote` → yine `run_execution_plan`. Yarım kalan iş plan motorunda **ikinci kez** yapılır; "basit soru 13 dakika" vakasının kaynağı budur.
11. **`_drive`** (ReAct döngüsü):
    - `apply_steering` → `_call_model`.
    - Araç çağrısı yoksa:
      - kanıt kapısı (`_tool_evidence_satisfied`, `reflexion.tool_evidence_required_note`),
      - ardından `_auto_continue_note`: `reflexion.integrity_note`, `_asked_instead_of_acting`, `_never_acted`, `reflexion.looks_unfinished`, `_stopped_without_acting`.
    - Araç çağrısı varsa `_run_tools`:
      - sözleşme doğrulaması, tekrar kapısı, `_targeted_edit_required`, `tools/preview.py::file_diff`,
      - `_execute` → `ApprovalPolicy.decide`,
      - **DENIED** sonucunda model `DENIED_MESSAGE` alır: "Onay GEREKTİRMEYEN bir yol dene". **B3 kök nedeni:** model aynı silmeyi başka yoldan yeniden onaya getirir.
    - Her araç turundan sonra: `reflexion.note`, `_stuck_editing`, `_looks_like_wrong_workspace`, `_record_changes` (`reflexion.change_log_note`), `_needs_push_to_act` (`enough_exploring_note`, yani "okumayı bırak, yaz" dürtmesi; **B4/A13** baskısı).
12. Doğrulama kapısı: `_verify` → `deps.verifier.verify()`, yalnız değiştirici tur varsa. Düşerse `_fix_findings` → `_run_verification_correction_attempt` (`run_agent(internal=True, require_local_mutation=True)`). Hakkı `MAX_VERIFY_ROUNDS`.
13. Öz denetim:
    - API modellerinde `config.runtime.self_review` açıkken **her** depth-0 turda (merhaba dahil) çalışır.
    - Web modellerinde `_web_self_review_needed` karar verir (regex içerir).
    - Akış: `_self_review` → `review.review_turn` → düzeltici `run_agent(internal=True)`. Düzeltme metni `_CORRECTION_TASK` görevi yeniden anlatan sahte bir kullanıcı mesajı olarak geçmişe girer.
14. Kapanış: `_mark_verification_notes`, `_mark_unverified`, `_announce_answer`, `learning_steps.learn` / `reinforce_recalled` (`scope_of(kind)`), `_maybe_compress`.

### 1.3 Plan motoru (`plan_runner.py`)

- `run_execution_plan` → `plan_generation.py::generate_plan`. Bu da `run_agent` ile çalışır; **geçmişsizdir** ve `PromotionContext` alır.
- Ardından temel doğrulama (`deps.verifier.verify()`) → `_PlanRun.run`.
- `_PlanRun.run_step` → `_PlanRun.execute`:
  - `_step_context` her adımda `todos`, `touched`, `fully_read`, `read_revisions` ve `changes` alanlarını sıfırlar.
  - `plan_context.py::step_deps` + `plan_context.py::step_prompt`. Adım istemi "Sonuçta yaptığını ve gözlediğin kanıtı açıkça yaz" der. **D4 kaynağı:** her cevap aynı rapor şablonunda çıkar.
  - **`self.agent(prompt, deps, depth=1, internal=True)` `history` olmadan çağrılır. A4 kök nedeni budur:** her adım geçmişi olmayan yeni bir ajandır. `run_candidates` ve `quality_gate` de aynı durumda.
- `_PlanRun.verify` → `step_verification.py::verify_step`.
- Adım düşerse `StepRollback(...).discard()` değişiklikleri **sessizce geri alır** (**A9**). Sonra `recovery.py::choose_recovery` / `replan_failed_step` (yeniden `generate_plan`) / `pause` gelir. Kullanıcı yalnız "duraklatıldı" görür.
- Final: `step_verification.py::verify_plan_acceptance` → `repair_final` → `quality_gate` (`review.review_turn` + düzeltme) → `finish`.
- `finish` metni **`self.outcomes[-1].final_text`**, yani son adımın kendi raporudur. O adım dosya değiştirmediyse cevap "hiçbir dosya değiştirmedim" der; oysa turda 5 dosya değişmiştir (**A4/A12**).
- `_PlanRun.outcome().messages` tüm adımların mesajlarının düz birleşimidir: her adım kendi sistem mesajını ve adım istemini taşır, **önceki sohbet hiç yoktur**. Çağıran bunu `state.history`'ye yazdığı için gizli kelime sonraki turlarda da **kalıcı olarak** kaybolur.

### 1.4 Araçlar (`tools/files.py`, `tools/builtin.py`)

- API yolunda `ExecutionPolicy.edit_format` varsayılanı `EditFormat.LINE_RANGE`'dir ve `replace_range` "TERCİH EDİLEN" araç olarak tanıtılır. Aralık tamamen silinip yerine `new` yazılır.
- **A2 kök nedeni:** `urun.adet -= adet` satırı `new` içinde tekrar edilmediği için sessizce kayboldu.
- Tüm düzenleme araçları modele yalnız "düzenlendi: yol (1 değişiklik)" döner. Diff yalnız UI olayına (`ToolExecuted.diff`) gider, model silinen satırı hiç görmez.
- Ek bulgu: `multi_edit` yapı kapısından (`_yapi_engeli`) geçmiyor. Godot `.tscn` biçimi `multi_edit` ile bozulabilir.

---

## 2. Hedef akış

```
kullanıcı mesajı
  → run_agent
      budget; bağlam = sistem istemi + proje talimatları + (kod kipinde) depo haritası
      [ders/beceri METNİ YOK; model find_skill / read_skill / recall_lessons ile ister]
      yürütme politikası: görev türüne bakmaz; tek web bütçe kademesi
      gözlem kilidi: sohbet kipi | plan kipi | bu turun etkisi "workspace_read"
                     → değiştirici araç şeması yok, dispatcher engeller
      plan motoru YALNIZ: workflow_mode=always  VEYA  kullanıcı /plan-yurut seçti
      _drive (tek ReAct döngüsü, TEK geçmiş):
          model → araç → sonuç (düzenlemede diff) → model …
          araç reddedildi → tur ORADA biter, model çağrılmaz, kullanıcıya sorulur
          dürtmeler: yalnız taşıma bütünlüğü, boş yanıt, bekleyen todo,
                     açık dış etki kanıtı (push/commit/shell/dosya)
      değiştirici tur → doğrulama kapısı (projenin kendi komutları)
      öz denetim yalnız değişiklik yapılmış turda
      TUR RAPORU (deterministik, araç kaydından):
          değişen dosyalar = ChangeSet
          çalıştırılan doğrulama komutları + çıkış kodları = tool_uses
          kapı sonucu
          değişiklik yoksa rapor YOK (sohbet ve merhaba sade kalır)
```

Plan motoru opsiyonel yol olarak kalır ama:
- adımlar tek konuşma geçmişini paylaşır;
- geri alma görünür olur;
- final cevabı aynı tur raporunu kullanır.

### Tasarım kararları

| Karar | Gerekçe |
|---|---|
| **Plan motoru silinmez; varsayılan yoldan çıkarılır.** `workflow_mode: auto` kaldırılır. Eski `auto` değeri `ExecutionMode._missing_` ile `off`'a eşlenir, tıpkı bugünkü boolean eşlemesi gibi. Motor yalnız `always` ayarıyla ya da `/plan-yurut` makrosuyla çalışır. | Adım kanıtı, checkpoint/devam ve Godot final kabulü (`verify_plan_acceptance` + alan adaptörleri) gerçekten değerli ve uzun Godot işleri için ölçülmüş. Varsayılan yol olması ise B2'yi üretiyor. Claude Code'da da çok adımlı iş için ayrı motor yok; model `todo_write` kullanıyor. Motoru "model çağırır" aracı yapmak bu fazda kapsamı büyütür ve BACKLOG'a yazılır. |
| **`classify.py` karar yolundan çıkarılır, modül silinmez.** Tek tüketicisi opt-in `/profil otomatik` (`auto_profile.py`) kalır. | Tur yönlendirme, bütçe, bağlam enjeksiyonu ve öz denetim artık görev türüne bakmaz. `auto_profile` kullanıcının açıkça açtığı bir model seçim özelliğidir. Bu fazda ona dokunmak kapsam genişletmedir; BACKLOG'a yazılır. |
| **`loops.py`, `promotion.py` ve `skill_recall.py` silinir.** | Karar yolundan çıkınca ölü kod olurlar (RULES "Ölü Kod"). |
| **`effects/detect.py::required_effect_for` kalır, yalnız BU turun metnine uygulanır.** Yönlendirme yapmaz; yalnız kanıt kapısını ve gözlem kilidini besler. | "Pushladım" yalanını yakalayan tek deterministik kapı budur (A1). "Tamam yaz" hiçbir desene uymaz: `yaz` fiili nesne ya da dosya adı olmadan eşleşmez. Kod bunu açıkça belgeliyor. |
| **Gözlem kilidi = sohbet kipi, plan kipi ya da `required_effect == "workspace_read"`.** | B4 "salt okuma turunda yazma kapalı" istiyor. Kilit yalnız **kısıtlar**, hiçbir işi başka yola yönlendirmez. Yanlış pozitifte model "yazma kapalı" der ve kullanıcı açıkça ister. Bu karar kullanıcı onayına sunulur (bkz. §6). |
| **Web bütçesinde tek kademe:** bugünkü "karmaşık" değerler kullanılır (90 çağrı / 75 araç turu / 5400 sn / 300 sn boşta). | Sabit uydurulmuyor; Godot koşusunda ölçülmüş değerler bunlar (`policy_for` yorumu). Kaçak turu ilerleme kapısı ve boşta kalma süresi durdurur. "Merhaba" bütçe tüketmez, çünkü model tek çağrıda cevaplar. |
| **`_is_genuine_simple_chat` yalnız `offer_tools` için kalır.** | Yönlendirme değil, taşıma optimizasyonu: selamlaşmada web istemine onlarca araç şeması eklenmez. |
| **`replace_range` tamamen kaldırılır.** Düzenleme sözleşmesi tüm sağlayıcılarda `edit_file` / `multi_edit` (benzersiz tam metin) + `write_file` olur. | A2. Web yolu zaten `SEARCH_REPLACE` (aider ölçümü). Tek sözleşme, emülasyon örneklerini ve reflexion metinlerini de sadeleştirir. |
| **Diff tavanı mevcut `MAX_PREVIEW_LINES` sabitidir.** | Yeni sabit uydurulmaz; onay önizlemesiyle aynı değer kullanılır. |
| **Plan adımında geri alma kalır ama görünür olur.** Kullanıcıya duraklama metninde, modele geçmişte not olarak bildirilir. | Geri almayı tamamen kaldırmak `test_rollback_unblocks_retry` ve Godot kurtarma akışını kırar. Görünürlük A9'u çözer. Alternatif (hiç geri almamak) §6'da sorulur. |

---

## Genel kısıtlar

- `CLAUDE.md` ve `RULES.md` bağlayıcıdır. Deponun `.env` dosyası okunmaz.
- Yeni dal açılmaz, push yapılmaz. `git add` her zaman dosya adıyla yapılır.
- İzlenmeyen `:memory:.ses`, `FUSION_MASTER_PROJE_DOKUMANI.md`, `dagitim/`, `index.html` dosyalarına dokunulmaz.
- Kalite kapısı her commit öncesi çalışır: `.venv/bin/ruff check . && .venv/bin/mypy && .venv/bin/pytest -q`.
- Commit mesajı: Türkçe conventional; faz numarası ve co-author satırı yok.
- Kırılan test gevşetilmez. Silinen her test için commit gövdesinde tek satır gerekçe yazılır ("X kaldırıldı çünkü …").
- Godot/alan adaptörü davranışı korunur. `verify_plan_acceptance`, `domain_adapters/*`, `core/structured_files.py` kapıları gevşetilmez.

## Görev bağımlılıkları ve paralellik

```
G0 ─┬─ G1 (araçlar)      ┐
    ├─ G2 (onay reddi)   ├─ dalga A: paralel, dosya kümeleri ayrık
    └─ G3 (plan geçmişi) ┘
          └─ G4 (yönlendirme)  ← G1, G2, G3 bitince
               └─ G5 (gözlem kilidi + dürtmeler)
                    └─ G6 (tur raporu)
                         └─ G7 (gerçek koşu doğrulaması)
```

`loop.py` darboğazdır. Dalga A'da ona yalnız G2 dokunur, o da yalnız `_run_tools` / `_execute` / `_drive` başındaki kısa kanca noktalarına. G4, G5 ve G6 `loop.py`'yi sırayla değiştirir.

---

### Görev 0: Başlangıç durumu (salt okuma)

**Dosyalar:** yok.

- [ ] Paralel ajanın değişikliklerinin commit edildiğini doğrula:
  - `git status --short` yalnız izlenmeyen 4 kullanıcı dosyasını göstermeli.
  - `loop.py`, `verification.py`, `step_verification.py`, `verify_discovery.py`, `tools/registry.py`, `tools/safety.py` **değişmiş olarak görünmemeli**.
  - Görünüyorsa DUR ve kullanıcıya sor.
- [ ] Kalite kapısını çalıştır; test sayısını kaydet (hedef: 3.900+). Kırmızıysa DUR.

---

### Görev 1: Tam metin eşleşmeli düzenleme ve modele diff dönüşü (A2)

**Dosyalar (sahiplik):**
- `src/fusion_cli/tools/files.py`
- `src/fusion_cli/tools/builtin.py`
- `src/fusion_cli/tools/preview.py`
- `src/fusion_cli/core/tools.py` (`_FAMILIES` içindeki `replace_range` girdisi ve `read_revisions` açıklaması)
- `src/fusion_cli/core/tool_emulation.py` (örnek ve talimat metinleri)
- `src/fusion_cli/core/structured_files.py` (yalnız yönlendirme mesajı)
- `src/fusion_cli/appserver/approval_preview.py`
- `src/fusion_cli/engines/agent/prompts/system.md` (yalnız "Kod değişiklikleri" bölümü)

**Bu görevin dokunmadığı yerler:** `loop.py` ve `reflexion.py` içindeki `replace_range` metinleri (G5), `plan_runner.py` (G3), `EditFormat` (G4).

**Önce yazılacak başarısız testler:** `tests/test_exact_edit_contract.py`
- `test_edit_sonucu_silinen_satiri_modele_diff_olarak_gosterir`: `urun.adet -= adet` satırını `new` içinde bırakmayan bir `edit_file` başarılı olur. `ToolResult.output` içinde `-    urun.adet -= adet` satırı bulunmalı. A2'nin birebir yeniden üretimidir.
- `test_edit_file_benzersiz_olmayan_old_reddedilir_ve_dosya_degismez`: davranış zaten var, sözleşme olarak kilitlenir.
- `test_multi_edit_yapi_denetiminden_gecer`: `.tscn` başlığını silen bir `multi_edit` "Yapı geçersiz" döner ve dosya değişmez. Bugün bu test **düşer** (ek bulgu).
- `test_write_file_var_olan_dosyada_diff_dondurur`: var olan dosyanın üzerine yazılınca çıktı unified diff içerir; yeni dosyada satır sayısı döner.
- `test_duzenleme_diffi_onizleme_tavaniyla_sinirlanir`: `MAX_PREVIEW_LINES`'ı aşan diff "… (+N satır)" ile kesilir.
- `test_replace_range_kayit_defterinde_yok`: `build_registry().get("replace_range") is None`; takma adlarda da yok.
- `test_emulasyon_talimatlari_replace_range_onermez`: `render_tool_instructions` çıktısında `replace_range` geçmez.

**Uygulama adımları:**
- [ ] `files.py`: `replace_range` ve `_replace_range_text` silinir.
- [ ] Ortak yardımcı `_change_summary(before, after, display)` eklenir. `preview.unified_diff` kullanır ve `MAX_PREVIEW_LINES` ile sınırlar. `preview.py` zaten `files.py`'yi import ediyor; döngüyü önlemek için `unified_diff` ve kırpma `files.py` tarafında ya da yeni saf bir `tools/diffing.py` içinde tutulur. `preview.py` oradan import eder.
- [ ] `edit_file`, `multi_edit` ve `write_file` (var olan dosya) başarı çıktısına bu diff eklenir. Biçim: `düzenlendi: yol (N değişiklik)\n` + diff.
- [ ] `multi_edit` sonucu yazılmadan önce `_yapi_engeli`'nden geçer.
- [ ] `edit_file` araç açıklaması "TERCİH EDİLEN kısmi düzenleme" olarak yeniden yazılır ("GERİYE UYUMLU fallback" ifadesi çıkar). Kural açıkça söylenir: `old` birebir ve benzersiz olmalı; ekleme için çevre satır `old`'a alınır. `EMPTY_OLD_MESSAGE` `replace_range`'i önermeyecek biçimde güncellenir. `write_file` açıklaması `replace_range` yerine `edit_file`'ı önerir.
- [ ] `preview.py`: `_preview_replace_range` ve `FILE_DIFF_TOOLS` içindeki girdi silinir. Aynı iş `approval_preview.py`'de yapılır.
- [ ] `core/tools.py`: `replace_range` aile girdisi silinir. `read_revisions` yalnız `replace_range` içinse alan ve `read_file` içindeki yazımı da silinir. Önce `grep read_revisions` ile tüketicileri doğrula; `plan_runner._step_context` onu sıfırlıyor, o satır G3'te temizlenir. **Alan kalırsa G3 için not düş.**
- [ ] `tool_emulation.py`: `replace_range` örneği `edit_file` örneğiyle değiştirilir; kural satırları güncellenir.
- [ ] `structured_files.py`: yönlendirme metni "`edit_file` ile yalnız ilgili satırları" olur.
- [ ] `system.md` "Kod değişiklikleri": "satır aralığı…" maddesi yerine "düzenleme sonucunda dönen diff'i oku; silinmesini istemediğin bir `-` satırı görürsen hemen geri ekle" gelir.

**Kaldırılacak / değişecek testler:**
- **Silinir:** `tests/test_replace_range.py` (8), `tests/test_replace_range_add_recipe.py` (3). Gerekçe: araç kaldırıldı; ekleme reçetesinin karşılığı `edit_file` benzersiz çevre satırıdır ve yeni testte kilitlenir.
- **Güncellenir** (yalnız `replace_range`'e değinen iddialar): `test_tools_files.py`, `test_approval_preview.py`, `test_emulated_edit_contract.py`, `test_tool_emulation_diet.py`, `test_tool_contract_example.py`, `test_missing_file_suggestion.py`, `test_structured_files.py`, `test_turn_budget.py`, `test_rollback_unblocks_retry.py`.
- `loop.py` mesajlarını sınayan `test_full_rewrite_guard.py`, `test_edit_format*.py` ve `test_agent_loop.py` iddialarına **bu görevde dokunulmaz**; G4 ve G5'te güncellenir. Bu testler araç kaydına bakıyorsa ve kırılıyorsa bunları G1'e al ve raporla.

**Risk:**
- Web modelleri ezberden `replace_range` çağırabilir. Bu durumda "bilinmeyen araç" sözleşme hatası, kullanılabilir araç listesiyle döner; onarım hakkı zaten var.
- Büyük diff bağlamı şişirebilir: tavan uygulanıyor.
- `preview` ile `files` arasında import döngüsü riski var.

**Commit:** `feat(araclar): düzenlemeyi tam metin eşleşmesine indir ve sonucu diff olarak modele döndür`

---

### Görev 2: Onay reddi turu durdurur ve kullanıcıya sorar (B3)

**Dosyalar (sahiplik):**
- `src/fusion_cli/engines/agent/approval.py` (`ApprovalAnswer.UNAVAILABLE`, `_ask_and_remember`)
- `src/fusion_cli/cli/prompter.py` (`ConsolePrompter.confirm`: TTY yoksa `UNAVAILABLE`)
- `src/fusion_cli/core/budget.py` (`BudgetStop.USER_DENIED`)
- Yeni: `src/fusion_cli/engines/agent/denial.py` (metin sabitleri + saf yardımcı; `loop.py` şişmesin diye)
- `src/fusion_cli/engines/agent/loop.py`: **yalnız** `DENIED_MESSAGE` / `_DECISION_MESSAGES`, `_run_tools`, `_execute`, `_drive`'ın döngü başı
- `src/fusion_cli/engines/effects/tool_runner.py` (DENIED dalı)

**Önce yazılacak başarısız testler:** `tests/test_user_denial_stops_turn.py`. `fakes.ScriptedProvider`, `AlwaysReject` ve `tool_call` kullanılır.
- `test_kullanici_reddedince_tur_ikinci_model_cagrisi_yapmadan_biter`: model `run_shell("rm -rf build")` ister, kullanıcı reddeder. Beklenen:
  - `outcome.model_calls_made == 1`,
  - prompter yalnız **bir** kez çağrılmış,
  - `budget.stop is BudgetStop.USER_DENIED`,
  - `final_text` `denial.DENIAL_STOP_ANSWER` biçiminde (araç adı + "nasıl devam edeyim?"),
  - `outcome.ok is True` (red bir hata değildir).
- `test_ayni_yanittaki_kalan_cagrilar_calismaz_ama_eslesen_arac_sonucu_alir`: iki çağrılı batch'te ilki reddedilir. İkinci çalışmaz ve kendi `tool_call_id`'siyle "atlandı" araç mesajı alır; API sağlayıcıları çağrı/sonuç eşleşmesi ister.
- `test_red_sonrasi_dogrulama_kapisi_ve_oz_denetim_calismaz`: sahte verifier ve review çağrılmaz.
- `test_ic_ice_tur_red_sonrasi_hemen_doner`: `budget.stop == USER_DENIED` iken `_drive` model çağırmadan döner. Plan motoru ve düzeltici turlar bunu miras alır.
- `test_etkilesimsiz_oturumda_onay_alinamamasi_red_sayilmaz`: TTY olmayan `ConsolePrompter` → `Decision.BLOCKED`. Model "onay alınamadı" metnini görür ve tur sürer.
- `test_reddedilen_git_akisi_durur`: `effects/tool_runner` DENIED'da akışı durdurur. Mevcut davranışı koru ve kilitle.

**Uygulama adımları:**
- [ ] `ApprovalAnswer.UNAVAILABLE` eklenir. `_ask_and_remember` bunu `Decision.BLOCKED`'a çevirir; `DENIED` artık yalnız "insan hayır dedi" demektir.
- [ ] `ConsolePrompter.confirm`, TTY olmayan ortamda boş cevaba `False` yerine `ApprovalAnswer.UNAVAILABLE` döner.
- [ ] `denial.py`:
  - `DENIAL_STOP_ANSWER` (kullanıcıya),
  - `DENIED_TOOL_RESULT` (modele: "kullanıcı reddetti; tur durdu"),
  - `SKIPPED_TOOL_RESULT`,
  - `APPROVAL_UNAVAILABLE_MESSAGE` (bugünkü `DENIED_MESSAGE`'in "etkileşimsiz" yarısı + UYDURMA UYARISI).
  - Ölçüm gerekçeli docstring'ler buraya taşınır.
- [ ] `_run_tools`: `ToolOutcome.DENIED` sonrası `budget.halt(BudgetStop.USER_DENIED)` çağrılır. Batch'in kalan çağrıları için `SKIPPED_TOOL_RESULT` araç mesajı yazılır ve döngüden çıkılır.
- [ ] `_drive`: döngü başında `budget.stop is USER_DENIED` ise model çağrılmadan `_outcome(DENIAL_STOP_ANSWER…, ok=True)` döner. `TurnBudgetExhausted` **yayınlanmaz**, çünkü bu bir bütçe olayı değildir. `run_agent`'taki doğrulama ve öz denetim kapıları `budget.stop` kontrolüyle zaten atlanır; öz denetim için `budget.stop is None` koşulu eklenir.
- [ ] Onay isteyen UI'da `UNAVAILABLE` yolu yok (`appserver/bridges.py` zaten `DENY` döner); dokunulmaz.

**Kaldırılacak / değişecek testler:**
- `test_agent_loop.py` ve `test_agent_approval.py` içinde "red sonrası model başka yol dener" iddiası **değişir**. Gerekçe: B3'te istenen davranış bunun tam tersi.
- `DENIED_MESSAGE` metnini doğrulayan testler `denial.*` sabitlerine taşınır.
- `test_renderer.py` içindeki `ToolOutcome.DENIED` gösterimi değişmez.

**Risk:**
- Oturum izni (`ApprovalMemory`) etkilenmez.
- Otomatik kipte sorulmadan çalışan komutlar zaten reddedilemez.
- Plan motorunda adımın reddi → adım düşer → G3'ün genel `budget.stop` kontrolü duraklatır. G3 birleşene kadar plan yolunda duraklama metni dağınık olabilir; G4'ten önce ikisi de biter.

**Commit:** `fix(onay): reddedilen araçta turu durdur ve kullanıcıya sor`

---

### Görev 3: Plan adımları tek konuşma geçmişini paylaşır; geri alma görünür olur (A4, A9, D4)

**Dosyalar (sahiplik):**
- `src/fusion_cli/engines/agent/plan_runner.py`
- `src/fusion_cli/engines/agent/plan_context.py`
- `src/fusion_cli/engines/agent/plan_generation.py` (yalnız `history` parametresi; `promotion` G4'te silinir)
- `src/fusion_cli/core/rollback.py` (gerekirse geri alınan yolları döndürme)

**Arayüz değişikliği:** `run_execution_plan(task, deps, run_agent, *, conversation: list[Message] | None = None, …)`.
- `conversation`, sistem mesajıyla başlayan ve bu turun kullanıcı mesajıyla biten kök konuşmadır.
- `None` ise bugünkü davranış korunur; çağrı yeri G4'te bağlanır.

**Önce yazılacak başarısız testler:** `tests/test_plan_shared_history.py`. Sahte `RunAgent` aldığı `history`'yi kaydeder.
- `test_plan_adimi_onceki_sohbeti_gorur`: `conversation` "gizli kelime: MAVİ-KEDİ" içeren bir kullanıcı mesajı taşır. **Her** adımın aldığı `history` bu mesajı içerir. Gizli kelime vakasının birebir yeniden üretimidir.
- `test_ikinci_adim_birinci_adimin_mesajlarini_gorur`: 1. adımın asistan ve araç mesajları 2. adımın geçmişinde bulunur.
- `test_plan_sonucu_gecmisi_kok_konusmayla_baslar_ve_tek_sistem_mesaji_tasir`: `outcome.messages[:len(conversation)] == conversation`; `role == "system"` olan başlangıç mesajı bir tanedir.
- `test_plan_uretimi_sohbet_gecmisini_gorur`: `generate_plan` içindeki `run_agent` çağrısı `history=conversation` alır.
- `test_dusen_adimin_geri_alinan_dosyalari_duraklama_metninde_ve_gecmiste_bildirilir` (A9): düşen adım `a.py` ve `b.py` yazmıştır ve geri alma çalışır. Pause metni "Geri alınan değişiklikler: a.py, b.py" içerir. Geçmişe "[Fusion] Şu değişiklikler geri alındı: …" notu eklenir. Geri alınan yollar `fully_read`'den düşer.
- `test_butce_durdurmasinda_plan_kurtarma_yapmadan_duraklar`: adım sonrası `deps.budget.stop` doluysa `replan_failed_step` ve `choose_recovery` çağrılmaz; pause metni durma nedenini taşır. G2'nin USER_DENIED'ı bu yoldan geçer.
- `test_adim_istemi_rapor_sablonu_istemez` (D4): `step_prompt` çıktısında "gözlediğin kanıtı" talimatı yok; "adım bitince tek cümleyle ne yaptığını söyle" var.

**Uygulama adımları:**
- [ ] `_PlanRun`'a `messages: list[Message]` alanı eklenir; `conversation` ile başlar.
- [ ] `execute`, `run_candidates` (aday için kopya) ve `quality_gate` → `self.agent(prompt, deps, history=self.messages, internal=True, …)`. `internal=True`, `loop._initial_messages(inherit_system=True)` sayesinde sistem önekini sabit tutar. Web sohbeti adım başına sıfırlanmaz; hız kazancı var, G7'de ölçülür.
- [ ] Adım başarılıysa `self.messages = outcome.messages`. Başarısızsa da konuşma korunur (model ne denediğini bilmeli), geri alma notu eklenir.
- [ ] Adım istemi geçmişe `[Plan adımı s1] …` önekli kullanıcı mesajı olarak girer. `step_prompt` içinden "ANA GÖREV" tekrarı çıkarılır (görev zaten geçmişte); "gözlediğin kanıtı açıkça yaz" talimatı silinir.
- [ ] `_step_context`: `fully_read` artık kopyalanır, sıfırlanmaz (okuma bilgisi geçmişte duruyor). `touched`, `changes`, `todos` ve `browser` adım başına ayrı kalır; adım kanıtı ve geri alma buna dayanıyor. `read_revisions` G1'de kalktıysa satırı silinir.
- [ ] Geri alma: `StepRollback.discard()` geri alınan yolları döndürüyor (`forget_rolled_back`'e geçiyor). Bunlar `_pause_text`'e ve geçmiş notuna aktarılır.
- [ ] `run_step` / `execute` sonrası: `deps.budget.stop is not None` ise kurtarma yapılmaz, doğrudan `pause` çağrılır.
- [ ] `outcome()`: `messages = [*self.messages, Message("assistant", text)]`. Son adımın asistan metni metinle aynıysa tekrar eklenmez.
- [ ] `finish` metni şimdilik son adımın metnidir. Geçmiş artık paylaşıldığı için bu metin tüm işi bilen modelden gelir; deterministik rapor G6'da eklenir.
- [ ] `plan_generation.generate_plan(..., history=...)` parametresi eklenir.
- [ ] `local_repair` izin kümesindeki `"replace_range"` girdisi silinir.

**Kaldırılacak / değişecek testler:**
- `test_plan_runner.py`, `test_plan_resume.py`, `test_plan_repair.py`, `test_rollback_wiring.py`, `test_rollback_unblocks_retry.py`, `test_attempts_wiring.py`: `messages` birleşimini ya da `step_prompt` metnini birebir doğrulayan iddialar yeni sözleşmeye göre **güncellenir**.
- Adım bağımsızlığını (her adımın taze `fully_read` alması) iddia eden test varsa **silinir**. Gerekçe: tek konuşma modelinde okuma bilgisi paylaşılır.

**Risk:**
- **Bağlam büyür.** Uzun Godot planında geçmiş şişer. `_maybe_compress` her `run_agent` sonunda çalışıyor, ama adımlar `internal` ve depth=1. Sıkıştırmanın plan yolunda tetiklendiğini testle doğrula (`test_plan_gecmisi_esikte_ozetlenir`).
- Ardışık iki `user` rolü (görev + adım istemi) bazı API'lerde birleştirilir. Harness notu gerekirse `assistant`/`user` sırası korunarak eklenir; `fakes` ile iki rol dizisi test edilir.
- Web öneki: adımlar arasında araç kümesi değişince `providers/web_browser.py::_deliver_turn` önek karşılaştırması sohbeti sıfırlayabilir. G7'de ölç; sıfırlanıyorsa BACKLOG'a yaz, bu fazda çözme.

**Commit:** `fix(plan): adımlar tek konuşma geçmişini paylaşsın, geri alma kullanıcıya bildirilsin`

---

### Görev 4: Yönlendirme modele bırakılır; kelime sınıflandırıcısı ve varsayılan plan motoru kalkar (B2, A5/B5)

**Bağımlılık:** G1, G2, G3 commit edilmiş olmalı.

**Dosyalar (sahiplik):**
- `src/fusion_cli/engines/agent/loop.py`: `run_agent` giriş bölümü, `_scoped_task`, `_promotion_context`, `_recall_skill`, `_permitted` / `_EDIT_TOOLS_HIDDEN`, `run_execution_plan` çağrı yerleri
- `src/fusion_cli/engines/agent/execution_route.py` (sadeleşir)
- `src/fusion_cli/engines/agent/execution_policy.py` (`kind` parametresi, `_EXTENDED_MARKERS`, kademeler, `edit_format`)
- `src/fusion_cli/core/model_capability.py` (`EditFormat.LINE_RANGE` silinir)
- `src/fusion_cli/core/execution_mode.py` (`AUTO` kalkar; `_missing_("auto") → OFF`)
- `src/fusion_cli/config/defaults.yaml`, `config/models.py` (`workflow_mode: off`)
- `src/fusion_cli/engines/agent/repo_context.py` (`kind` parametresi kalkar)
- `src/fusion_cli/engines/agent/learning_steps.py` (`scope`)
- `src/fusion_cli/engines/agent/engine_tools.py` (`recall_lessons` aracı)
- `src/fusion_cli/engines/agent/plan_generation.py` (`promotion` parametresi silinir)
- `src/fusion_cli/cli/repl/macros.py` (`Mode.WORKFLOW` + `plan-yurut` makrosu)
- `src/fusion_cli/cli/session.py`, `cli/repl/loop.py`, `cli/repl/tui_loop.py`, `appserver/session.py`: yalnız `workflow` bayrağının geçirilmesi
- **Silinir:** `engines/agent/loops.py`, `engines/agent/promotion.py`, `engines/agent/skill_recall.py`

**Önce yazılacak başarısız testler:** `tests/test_single_loop_routing.py`
- `test_kisa_onay_mesaji_plan_motoruna_girmez` (B2): geçmişin ilk kullanıcı mesajı "CSV export özelliği ekle ve testlerini yaz", yeni mesaj "Tamam yaz". `run_execution_plan` monkeypatch ile patlatılır ve çağrılmaz; `ExecutionRouteSelected.route == "fast"`.
- `test_karmasik_gorev_varsayilan_olarak_tek_dongude_kalir`: "hatayı düzelt, refactor et ve testleri güncelle" plan motoruna girmez.
- `test_workflow_mode_always_plan_motorunu_calistirir`: `run_execution_plan` çağrılır ve `conversation` kök mesajları taşır (G3 bağlantısı).
- `test_kullanici_plan_yurut_secince_plan_motoru_calisir`: `run_agent(..., workflow=True)` → plan.
- `test_eski_auto_ayari_off_olarak_yuklenir`: `workflow_mode: auto` içeren yapılandırma hatasız yüklenir ve `ExecutionMode.OFF` verir.
- `test_yurutme_politikasi_gorev_turune_bakmaz`: web modelinde "merhaba dünyayı açıkla" ile "tüm projeyi kapsamlı refactor et" için `max_model_calls` ve `max_tool_rounds` eşittir.
- `test_beceri_metni_kendiliginden_baglama_girmez` (A5/B5): kurulu `godot` becerisi varken "godot sahnesini düzelt" görevinde sistem mesajı beceri metnini içermez ve `CapabilityActivated` yayınlanmaz.
- `test_dersler_kendiliginden_hatirlanmaz_ama_aracla_istenebilir`: sahte `LessonMemory.recall` tur başında çağrılmaz; `recall_lessons` aracı çağrılınca döner.
- `test_duzenleme_semasi_tum_saglayicilarda_ayni`: API ve web politikalarında şemada `edit_file`, `multi_edit`, `write_file` var, `replace_range` yok.
- `test_depo_haritasi_gorev_turunden_bagimsiz_ve_sohbette_yok`: kod kipinde depth-0'da harita var; sohbet kipinde yok.

**Uygulama adımları:**
- [ ] `run_agent`: `classify_task_details`, `_scoped_task`, `auto_context`, `_recall_skill` ve `skill_recall` importu silinir. `learning_steps.recall_lessons` tur başında çağrılmaz; `learn(..., scope=None)` kapsamsız kaydeder. Önce `LessonMemory` sözleşmesinin `None` kabul ettiğini doğrula; kabul etmiyorsa sabit bir genel kapsam kullan.
- [ ] `run_agent` imzasına `workflow: bool = False` eklenir. Rota:
  - `workflow` ya da `workflow_mode is ALWAYS` → `run_execution_plan(task, deps, run_agent, conversation=messages, self_review=…)`,
  - aksi hâlde `_drive`.
  - `FAST_PROMOTABLE` ve yükseltme bloğu silinir. `ExecutionPromoted` olayı artık yayınlanmıyorsa olay sınıfı ve renderer eşlemesi de silinir (ölü kod).
- [ ] `execution_route.py`: `choose_execution_route(mode, *, requested: bool) -> ExecutionRouteDecision`, iki değerli (`FAST`, `WORKFLOW`).
- [ ] `execution_policy.py`:
  - `policy_for(config, spec, task)` olur; `kind` ve `_COMPLEX_KINDS` kalkar.
  - `complex_task = required_effect in _MUTATING_EFFECTS`.
  - Web için tek kademe (90/75/5400/300) uygulanır; `_EXTENDED_MARKERS` silinir.
  - `edit_format` alanı ve `EditFormat.LINE_RANGE` silinir. Tek sözleşme kaldığı için `_EDIT_TOOLS_HIDDEN` yalnız `WHOLE_FILE` için gerekiyorsa kalır; kullanan yoksa enum ve harita tamamen silinir. Önce `grep EditFormat` ile kontrol et.
  - `is_complex_kind` silinir. `loop.py`'deki kullanımları (`blocking` hesabı, `_web_self_review_needed`) `execution.complex_task` ile değişir.
- [ ] `repo_map_block(root)`: kod kipinde depth-0'da her turda eklenir. Metin sabit olduğu için önek de sabit kalır.
- [ ] `engine_tools.py`: `recall_lessons(query)` salt okunur aracı eklenir. `LessonMemory` yoksa araç sunulmaz; `find_skill` deseniyle aynı kurulur. `loop.ALWAYS_ALLOWED` kümesine eklenir.
- [ ] `web_reference.md`: `CapabilityRegistry` yerleşik kaynak destekliyorsa `find_skill` ile bulunabilir yerleşik beceri olarak kaydedilir. Desteklemiyorsa dosya ve kaydı `docs/BACKLOG.md`'ye taşınır ("web referansını yerleşik beceri yap"). Sessizce silinmez.
- [ ] `macros.py`: `Mode.WORKFLOW`, `plan-yurut` makrosu ve `mode_workflow(mode) -> bool`. REPL, TUI ve appserver turları bayrağı `run_agent_task(..., workflow=…)` ile geçirir.
- [ ] `loops.py`, `promotion.py`, `skill_recall.py` silinir. `classify.py` yalnız `auto_profile.py` için kalır; BACKLOG'a "auto_profile'ı kelime sınıflandırıcısından çıkar" yazılır.

**Kaldırılacak / değişecek testler (gerekçeli):**
- **Silinir:**
  - `test_loop_primitives.py` (5), `test_loops_wiring.py` (4): modül silindi.
  - `test_execution_promotion.py`: yükseltme kaldırıldı; işi ikinci kez yaptırıyordu (B2).
  - `test_skill_recall.py` (23), `test_recall_policy_v2.py` (8), `test_referans_butcesi.py`: otomatik enjeksiyon kaldırıldı (A5/B5).
- **Yeniden yazılır:**
  - `test_execution_route.py` (7): iki değerli rota.
  - `test_web_execution_policy.py` (20): tek kademe. `_is_genuine_simple_chat` → `offer_tools` iddiaları korunur.
  - `test_runtime_budget_v2.py`, `test_plan_step_budget.py`, `test_repo_map_wiring.py`, `test_edit_format.py`, `test_edit_format_dispatch.py`.
  - `test_config.py` (`workflow_mode`).
- **`kind`'e bağlı iddialar ayıklanır:** `test_agent_loop.py`, `test_diagnosis_wiring.py`, `test_output_contract.py`, `test_tool_directive_scope_visibility.py`, `test_web_mutation_gate.py`, `test_web_response_integrity.py`, `test_evals.py`.
- **Dokunulmaz:** `test_classifier_v2.py`, `test_classify_verify.py` (modül duruyor). Bu dosyaların doğrulama kısmı `classify`'dan bağımsızsa zaten korunur.

**Risk:**
- **En büyük davranış değişikliği bu.** Web modeli karmaşık bir işte plan yapmadan dağılabilir. Önlemler:
  - `system.md`'de `todo_write` yönergesi (G5),
  - bekleyen todo varken otomatik devam (G5'te korunur),
  - ilerleme kapısı.
- Godot uzun koşuları varsayılan olarak planı kaybeder. Kullanıcı `workflow_mode: always` ya da `/plan-yurut` kullanır; bu, sürüm notuna yazılır.
- Web'de "merhaba" bütçesi 8'den 90'a çıkar. Kaçak tur riskini `max_idle_rounds` ve `idle_timeout_s` sınırlar. G7'de "merhaba" süresi ölçülür.

**Commit:** `refactor(agent): yönlendirmeyi modele bırak, kelime sınıflandırıcısını ve varsayılan plan motorunu karar yolundan çıkar`

---

### Görev 5: Gözlem turunda yazma kapalı; kapsamı büyüten dürtmeler kalkar (B4, A13)

**Bağımlılık:** G4.

**Dosyalar (sahiplik):**
- `src/fusion_cli/engines/agent/chat_mode.py` → `observe_execution(execution, reason)` olarak genelleştirilir. `chat_execution` bunun ince sarmalayıcısı olur ya da çağrı yerleri güncellenip silinir.
- `src/fusion_cli/engines/agent/loop.py`: `_drive`, `_auto_continue_note`, `_needs_push_to_act`, `_stopped_without_acting`, `_never_acted`, `_asked_instead_of_acting`, `_targeted_edit_required` mesajları, `_tool_contract_failure` / `_suggested_tool_schema` metinleri
- `src/fusion_cli/engines/agent/reflexion.py`
- `src/fusion_cli/engines/agent/prompts/system.md` ("İlerleme" ve "Çalışma ilkeleri" bölümleri: `todo_write` yönergesi)

**Önce yazılacak başarısız testler:** `tests/test_observe_turn.py`
- `test_salt_okuma_isteginde_degistirici_arac_semasi_sunulmaz`: "src/app.py dosyasını oku ve ne yaptığını anlat" isteğinde `CompletionRequest.tools` içinde `write_file`, `edit_file`, `multi_edit`, `run_shell`, `scaffold_web` yok.
- `test_gozlem_turunda_yazma_cagrisi_engellenir_ve_diske_dosya_dusmez` (B4): web emülasyonuyla gelen `write_file("kopya.py", …)` sonucu `BLOCKED` olur; `tmp_path` içeriği değişmez.
- `test_okuma_turlarinda_kesif_durtmesi_yapilmaz`: beş okuma turundan sonra mesajlarda `enough_exploring_note` metni yok.
- `test_arac_cagirmadan_cevaplanan_kod_sorusu_zorlanmaz`: kod kipinde "bu fonksiyon ne işe yarar" tek model çağrısıyla biter (bugün `_never_acted` / `_stopped_without_acting` ek çağrı açabiliyor).
- `test_bekleyen_todo_varken_devam_notu_verilir`: korunacak davranış.
- `test_kesik_yanitta_butunluk_notu_korunur`: korunacak davranış.
- `test_acik_dis_etkide_kanit_kapisi_korunur`: "commit at" isteğinde araçsız "commitledim" cevabı `unverified_action_message` ile `ok=False` döner.
- `test_dogrulama_duzeltmesinde_mutasyon_zorunlulugu_korunur`: `require_local_mutation` dalı korunur.

**Uygulama adımları:**
- [ ] `observe_execution`: `allow_mutation=False`, `observe_only=True`, `complex_task=False`, `requires_tool_evidence` yalnız okuma etkisi için.
- [ ] `run_agent`'ta kilit uygulanır: `chat_mode` ya da `plan_mode` ya da `execution.required_effect == "workspace_read"`. Model yine de değiştirici araç çağırırsa `_execute` zaten `MUTATION_BLOCKED_MESSAGE` döner; gözlem gerekçesi metinde yazılır ("bu tur salt okuma; değişiklik istiyorsan açıkça söyle").
- [ ] `_needs_push_to_act`, `_stopped_without_acting`, `_asked_instead_of_acting` ve `_never_acted`'ın `require_local_mutation` dışındaki dalı silinir. İlgili sabitler (`MAX_READ_ONLY_ROUNDS`, `MAX_EXPLORE_PUSHES`), `_State` alanları ve `reflexion` notları (`enough_exploring_note`, `never_acted_note`, `asked_instead_of_acting_note`, `looks_unfinished`, `has_concrete_deliverable`) da silinir.
- [ ] `_auto_continue_note` yalnız şunlara bakar: `integrity_note`, `require_local_mutation` ve bekleyen todo. `heuristic_auto_continue` alanı artık anlamsızsa `ExecutionPolicy`'den silinir.
- [ ] `loop.py` ve `reflexion.py` içindeki `replace_range` önerileri `edit_file` olarak güncellenir: `_targeted_edit_required`, `_suggested_tool_schema`, `_verification_correction_task`, `reflexion.verification_action_required_note`.
- [ ] `system.md`: "Çok adımlı işte `todo_write` ile kısa bir liste tut ve ilerledikçe güncelle; basit işte kullanma" ve "İstenmeyen dosya, kopya ya da kanıt dosyası oluşturma" satırları.

**Kaldırılacak / değişecek testler (gerekçeli):**
- **Silinir:**
  - `test_hic_arac_cagirmayan_tur.py`: `_never_acted` kaldırıldı; model araçsız cevap verebilmeli.
  - `test_gorev_hatirlatmasi.py` içindeki dürtme iddiaları.
  - `test_agent_loop.py` içindeki `_needs_push_to_act`, `_stopped_without_acting`, `_asked_instead_of_acting` ve `looks_unfinished` testleri. Gerekçe: bu kapılar modeli yazmaya itiyor, B4 ve A13'ü üretiyordu.
- **Korunur:** `test_verification_action_gate.py`. Gerekiyorsa yalnız metni güncellenir.
- **Güncellenir:** `test_full_rewrite_guard.py`, `test_agent_chat_mode.py`.

**Risk:**
- Ölçülmüş web vakası: model "şimdi yapacağım" deyip durabilir.
  - Önlem: bekleyen todo devamı ve açık etki kanıt kapısı korunuyor.
  - G7'de CSV senaryosunda ölçülür. Tekrar ederse yalnız "araç çağrısı ilan edip üretmedi" teşhisi (`classify_response` taşıma bütünlüğü) genişletilir, türe dayalı dürtme geri getirilmez.
- `workspace_read` yanlış pozitifi → §6'da karar.

**Commit:** `fix(agent): gözlem turunda yazmayı kapat, modeli yazmaya iten dürtmeleri kaldır`

---

### Görev 6: Başarı beyanı gerçek çıktıya bağlanır; tur raporu araç kaydından üretilir (A1, A12, D4)

**Bağımlılık:** G5 ve G3.

**Dosyalar (sahiplik):**
- Yeni: `src/fusion_cli/engines/agent/turn_report.py` (saf; ağır bağımlılık yok)
- `src/fusion_cli/engines/agent/loop.py`: `run_agent` kapanışı, `_mark_unverified`, `_mark_verification_notes`, `_self_review` koşulu, `_CORRECTION_TASK` / `_correction_task` / `_already_done_block`, `_verification_correction_task`, `_web_self_review_needed`
- `src/fusion_cli/engines/agent/plan_runner.py` (yalnız `finish` ve `pause` metni)
- Tüketir: `verify_discovery.py::is_behavioral_command`. Bu dosya diğer ajanın alanı; **değiştirilmez**, yalnız import edilir.

**Arayüzler:**
- `CommandRun(command: str, exit_code: int | None, after_last_mutation: bool)` (frozen)
- `TurnReport(changed_paths: tuple[str, ...], command_runs: tuple[CommandRun, ...], gate: VerificationResult | None)` (frozen)
- Metotlar:
  - `is_verified -> bool | None`: `None` = değişiklik yok, soru yok.
  - `render() -> str`: Türkçe, kısa.
- `build_turn_report(changed_paths, tool_uses, gate) -> TurnReport`. Çıkış kodu `run_shell` çıktısındaki `(çıkış kodu N)` önekinden tek yardımcı ile okunur (RULES "hata tespiti tek yardımcı").

**Önce yazılacak başarısız testler:** `tests/test_turn_report.py`
- `test_degisiklik_yoksa_rapor_eklenmez` (D4): "Sadece 'merhaba' yaz" ve okuma turu final metne hiçbir şey eklemez.
- `test_degisen_dosyalar_modelin_beyanindan_degil_degisiklik_kaydindan_gelir` (A12): model "hiçbir dosya değiştirmedim" der ama iki dosya yazılmıştır. Rapor iki yolu listeler.
- `test_son_degisiklikten_sonra_test_calismadiysa_dogrulanmadi_yazar` (A1).
- `test_son_degisiklikten_sonra_basarisiz_test_turu_basarisiz_yapar`: `run_shell("pytest -q")` çıkış kodu 1 döner. Rapor "başarısız (çıkış 1)" der; `outcome.ok is False`.
- `test_degisiklikten_once_calisan_test_kanit_sayilmaz`: test geçti, sonra dosya değişti → "doğrulanmadı".
- `test_kapi_sonucu_rapora_girer_ve_uyari_tek_yerden_uretilir`: `_mark_unverified` metni rapora taşınır; iki ayrı uyarı bloğu çıkmaz.
- `test_plan_sonucu_ayni_raporu_kullanir`: `_PlanRun.finish` çıktısı kök `ChangeSet` ile rapor içerir; son adımın "değiştirmedim" cümlesi raporla çelişse bile listede dosyalar görünür.
- `test_oz_denetim_yalniz_degisiklik_yapilan_turda_calisir`: API modelinde "merhaba" için `review_turn` çağrılmaz (B2 gecikmesi).
- `test_duzeltme_turu_gorevi_sahte_kullanici_mesajiyla_tekrarlamaz`: düzeltme notu `[Fusion doğrulama]` önekli kısa not olur; "Kullanıcının görevi şuydu" geçmişe girmez.

**Uygulama adımları:**
- [ ] `turn_report.py` saf olarak yazılır. Komut sınıflandırması için `is_behavioral_command` + `_is_test_command` eşdeğeri kullanılır. `_is_test_command` özelse ve dışa açık değilse, G0'daki commit sonrası dışa açılması için kullanıcıya/diğer ajana sorulur; kendiliğinden değiştirilmez.
- [ ] `run_agent` kapanışı: `_mark_verification_notes` + `_mark_unverified` yerine `build_turn_report(...)` kullanılır. Sohbet ve gözlem turunda rapor yoktur. Son davranışsal komut başarısızsa ya da kapı düştüyse `outcome.ok = False`.
- [ ] Öz denetim koşulu `outcome.mutating_tool_calls_made > 0 and budget.stop is None` olur. `_web_self_review_needed` (regex içeriyor) silinir.
- [ ] Düzeltme görevleri görevi yeniden anlatmaz (geçmiş zaten paylaşılıyor). `_already_done_block` gereksizleşirse silinir.
- [ ] `plan_runner.finish` ve `pause` aynı raporu kullanır. Kök `deps.tool_context.changes.paths` ile adımlardaki `tool_uses` birleşimi girdidir.

**Kaldırılacak / değişecek testler:**
- `UNVERIFIED_WARNING` ve `VERIFICATION_NOTES` metin testleri `turn_report` testlerine **taşınır**.
- `test_agent_loop.py` öz denetim testleri "her turda denetim" iddiasını bırakır.
- `_web_self_review_needed` testleri **silinir**. Gerekçe: regex karar kaldırıldı, koşul yapısal oldu.

**Risk:**
- Test komutu olmayan projelerde her değiştirici tur "doğrulanmadı" satırı taşır. Bu dürüst bir davranış ve istenen şey.
- Kapıya otomatik test komutu eklemek bu görevin dışında (§6).

**Commit:** `feat(agent): başarı beyanını gerçek komut çıktısına ve değişiklik kaydına bağla`

---

### Görev 7: Gerçek koşu doğrulaması ve belgeler

**Dosyalar:** `docs/BACKLOG.md`, `docs/NASIL_KULLANILIR.md` (`/plan-yurut`, `workflow_mode` notu), `docs/superpowers/plans/2026-09-17-claude-paritesi.md` (Faz 2 durumu).

- [ ] Kalite kapısı yeşil; test sayısı G0 ile karşılaştırılır. Silinen her dosya commit gövdelerinde gerekçelidir.
- [ ] Aşağıdaki senaryolar hem bir API modeliyle (yerleşik araç çağrısı) hem `gemini_web` ile (emülasyon), `fusion serve` uygulamasında ve REPL'de koşturulur. Sonuçlar bu plan dosyasının sonuna tablo olarak eklenir: süre, model çağrısı, sonuç.
- [ ] BACKLOG'a eklenecekler:
  - plan motorunu modelin çağırabildiği araç yapmak,
  - `auto_profile`'ı sınıflandırıcıdan çıkarmak,
  - web öneki / adım araç kümesi ölçümü,
  - web referansı (G4'te taşınamadıysa).

**Commit:** `docs: tek ajan döngüsünü ve plan yürütme kipini belgele`

---

## 4. Commit mesajı önerileri (özet)

| Görev | Mesaj |
|---|---|
| G1 | `feat(araclar): düzenlemeyi tam metin eşleşmesine indir ve sonucu diff olarak modele döndür` |
| G2 | `fix(onay): reddedilen araçta turu durdur ve kullanıcıya sor` |
| G3 | `fix(plan): adımlar tek konuşma geçmişini paylaşsın, geri alma kullanıcıya bildirilsin` |
| G4 | `refactor(agent): yönlendirmeyi modele bırak, kelime sınıflandırıcısını ve varsayılan plan motorunu karar yolundan çıkar` |
| G5 | `fix(agent): gözlem turunda yazmayı kapat, modeli yazmaya iten dürtmeleri kaldır` |
| G6 | `feat(agent): başarı beyanını gerçek komut çıktısına ve değişiklik kaydına bağla` |
| G7 | `docs: tek ajan döngüsünü ve plan yürütme kipini belgele` |

---

## 5. Gerçek koşu doğrulama senaryoları

Her senaryo kod kipinde koşar; "Sadece merhaba yaz" ve gizli kelime senaryoları ek olarak sohbet kipinde de koşar. Gözlem kaynağı:
- `fusion trace`,
- UI olayları (`ExecutionRouteSelected`, `ToolExecuted`, `TurnOutcome`),
- `git status`.

| # | Senaryo | Adımlar | Beklenen (geçme ölçütü) | Bulgu |
|---|---|---|---|---|
| 1 | "Sadece 'merhaba' yaz" | Yeni oturum, tek mesaj | Cevap yalnız `merhaba`. Model çağrısı 1, araç çağrısı 0. Rapor ya da uyarı eki yok. Web'de araç şeması gönderilmedi. Süre: API < 5 sn; web tek çağrı süresi mertebesinde. | D4, B2 |
| 2 | "Tamam yaz" | Önce "CSV export özelliği ekle" (tamamlanır), ardından "Tamam yaz" | İkinci tur plan motoruna girmez (`route=fast`). Kabuk komutu çalışmaz, dosya değişmez. Cevap kısa bir onay; süre 34 sn'nin çok altında. | B2 |
| 3 | Gizli kelime | "Gizli kelime MAVİ-KEDİ, sakla." → "Bu projeye X fonksiyonunu ekle" (çok dosyalı; bir kez `/plan-yurut` ile, bir kez varsayılan yolla) → "Gizli kelime neydi?" | Her iki yolda da cevap `MAVİ-KEDİ`. Plan yolunda `outcome.messages` ilk kullanıcı mesajını taşır. | A4 |
| 4 | CSV export görevi | Test paketi olan küçük bir Python projesinde "ürünleri CSV'ye aktaran bir export ekle, testini yaz" | Düzenlemeler `edit_file`/`write_file` ile yapılır ve her araç sonucunda diff görünür. Var olan satır kaybolmaz (`git diff` elle incelenir: `urun.adet -= adet` benzeri satırlar yerinde). Tur raporu değişen dosyaları ChangeSet'ten listeler. Son değişiklikten sonra `pytest` gerçekten çalışmış ve çıkış kodu raporda yazıyor. Testler kırıksa `ok=False` ve cevapta "başarısız". "Tüm testler geçti" cümlesi yalnız çıkış 0 varsa kabul edilir. | A1, A2, A12 |
| 5 | Silme reddi | "build klasörünü sil" → onay ekranında Reddet | Onay ekranı **bir kez** çıkar. Tur ikinci model çağrısı yapmadan biter; cevap "reddettin, durdum, nasıl devam edeyim?". Klasör yerinde. Aynı turda başka bir silme yolu önerilmez. `/plan-yurut` ile aynı deneme plan duraklamasıyla biter; plan yeniden planlama yapmaz. | B3 |
| 6 | Salt okuma sorusu | 2.600 satırlık bir dosyası olan projede "bu dosyadaki sipariş akışını incele ve anlat" | Değiştirici araç şeması sunulmaz. `git status` temiz; kopya ya da kanıt dosyası yok. Cevap kısa ve rapor şablonsuz. | B4, D4 |
| 7 | Plan yolunda geri alma (ek) | `/plan-yurut` ile adımı kasıtlı düşürecek bir görev (olmayan bir komutu doğrulama koşulu yapan) | Duraklama metninde "Geri alınan değişiklikler: …" listesi var. Sonraki turda model geri alınan düzenlemeleri biliyor. | A9 |
| 8 | Godot kapısı (gerileme) | Mevcut Godot örnek projesinde sahneye düğüm ekleme, bir kez varsayılan yolla, bir kez `/plan-yurut` ile | `.tscn` biçim kapısı (`edit_file`/`multi_edit` dahil) çalışır; alan kapıları ve final kabul değişmemiştir. | Godot koruması |

**Kabul:** 1–6 iki sağlayıcı yolunda da geçer. 7–8 en az API yolunda geçer. Herhangi biri düşerse ilgili görev yeniden açılır ve faz kapanmaz.

---

## 6. Onaya sunulan açık kararlar

Kod yazılmadan önce kullanıcıya sorulacaklar:

1. **Gözlem kilidinin tetikleyicisi.** Salt okuma turunu tanımak için `effects/detect.py::required_effect_for == "workspace_read"` kullanılıyor; bu da regex tabanlı. Alternatif: kilidi yalnız sohbet ve plan kipinde tutmak, kod kipinde B4'ü dürtme kapılarının kaldırılmasına (G5) bırakmak.
2. **Plan adımında geri alma.** Önerilen: görünür geri alma. Alternatif: Claude Code gibi hiç geri almamak; kullanıcı `/undo` kullanır.
3. **Test komutunun doğrulama kapısına eklenmesi.** `discover_auto_commands` testleri bilerek dışarıda bırakıyor. Önerilen: bu fazda harness testi çalıştırmaz, rapor dürüstçe "çalıştırılmadı" der. Alternatif: değiştirici turda projenin test komutu da kapıda koşar. Bu seçenek maliyetlidir ve diğer ajanın `verify_discovery.py` alanına girer.
4. **`self_review` varsayılanı.** Önerilen: açık kalır ama yalnız değişiklik yapılan turda çalışır. Alternatif: varsayılanı `false` yapmak.
5. **`classify.py`'nin akıbeti.** Önerilen: yalnız opt-in `/profil otomatik` için kalır, BACKLOG'a yazılır. Alternatif: `auto_profile` ile birlikte bu fazda silinir.

---

### Critical Files for Implementation
- /Users/motogate/Desktop/01-Projeler/fusion-cli/src/fusion_cli/engines/agent/loop.py
- /Users/motogate/Desktop/01-Projeler/fusion-cli/src/fusion_cli/engines/agent/plan_runner.py
- /Users/motogate/Desktop/01-Projeler/fusion-cli/src/fusion_cli/tools/files.py
- /Users/motogate/Desktop/01-Projeler/fusion-cli/src/fusion_cli/engines/agent/execution_policy.py
- /Users/motogate/Desktop/01-Projeler/fusion-cli/src/fusion_cli/engines/agent/approval.py