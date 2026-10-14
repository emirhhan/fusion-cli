# FUSION — MASTER PRODUCT & ENGINEERING PLAN

> **Sürüm:** 1.0 — 13 Ekim 2026  
> **Hedef repo:** https://github.com/emirhhan/fusion-cli  
> **Doküman tipi:** Ürün vizyonu + mimari kararlar + kapsamlı geliştirme backlog'u + uygulama fazları + kabul testleri + tasarım direktifi  
> **Hedef:** Claude Code / Codex düzeyinde veya belirli işlerde daha iyi doğrulanmış sonuçlar üreten, profesyonel, local-first, macOS ve Windows'ta tam özellikli, mobil/VS Code/tarayıcı/Telegram üzerinden erişilebilen Fusion.  
> **Başlangıç bütçesi:** Aylık barındırma/GPU/sunucu faturası **0**; zorunlu mağaza, imzalama, alan adı ve sağlayıcı onay ücretleri daha sonra, bilinçli kararla.  
> **Kapsam notu:** Bu belge sohbet boyunca konuştuğumuz **tüm ürün gereksinimlerini, olası hata bulgularını ve çözüm fikirlerini** bir araya getirir. Daha önceki kaynak kodu analizlerinin bir kısmı eksik commit'ler üzerinden statik olarak yapılmıştır. Bu nedenle 'kodda kesin bug' diye sıralanmış bazı maddeler burada **tekrar doğrulanacak bulgu** olarak işaretlenmiştir. Kodu görmeden mevcut uygulamayı bozacak bir değişiklik yapılmayacaktır.

---

## 0. Bu dosyayı uygulayacak Codex / geliştirici için en önemli kurallar

1. **SADECE `emirhhan/fusion-cli` üzerinde çalış.** `Runfusion/Fusion` veya `equinor/fusion-cli` farklı projelerdir. Önceki görsel üretim turunda karışan başka bir Fusion dashboard'unun iş akışları ve komutları bu ürünün mevcut gerçekliği sanılmamalı.
2. Önce repo durumunu incele: `git status`, `git rev-parse HEAD`, branch'ler, commit edilmemiş değişiklikler, `README.md`, `CLAUDE.md`, `RULES.md`, `docs/BACKLOG.md`, ilgili kodlar ve testler. **Kullanıcının commit edilmemiş kodunu silme, overwrite etme, rebase etme, stash etme.** Başlamadan mevcut çalışma ağacını raporla; gerekiyorsa değişiklik yapmadan önce izin al.
3. Aşağıdaki madde başlıkları **ürün gereksinimidir**. Her biri için uygulama öncesi `Var / Kısmen var / Eksik / Hatalı / Belirsiz` matrisi çıkar; kaynak dosya, sembol, test ve mevcut davranışı kaydet. Zaten iyi çalışan sistemi yeniden yazma.
4. **Kod kanıtı, test kanıtı, tasarım önerisi ve henüz doğrulanmamış iddia birbirine karıştırılmayacak.** İlgili commit hash'i olmadan satır numarasına körü körüne güvenme.
5. Her faz küçük PR/commit'lere bölünsün. Önce regresyon testi → düzeltme → CLI/UI testleri → gerçek işletim sistemi testi → dokümantasyon. Fazlar birbirinden bağımsız geri alınabilir olsun.
6. Uygulama, logolar dışında **neon, uzay, hologram, gereksiz gradyan veya çizgi-film robotlarla** doldurulmayacak. Mevcut Fusion arayüzünün güçlü yanları korunacak. Apple'ın sakinlik ve doğal his yaklaşımından esinlen, Apple/Codex arayüzünü kopyalama.
7. Her araç veya otomasyonun yetkileri görünür olmalı. Onayları, macOS/Windows güvenlik mekanizmalarını, OAuth şartlarını veya mağaza kurallarını **asla sessizce aşma**.
8. Kullanıcıya “tamamlandı” denmesi ancak **zorunlu kabul kriterleri gerçekten yürütülüp kanıt üretmişse** mümkün. Atlanan test hiçbir zaman `PASSED` değildir.
9. İnternet altyapı maliyetini başlangıçta 0 tut; ama “her servis, her mağaza, her OAuth sağlayıcısı, her ağ koşulu, her model ücretsiz ve sorunsuz” garantisi verme.
10. Her fazın sonunda **ne değişti / nasıl test edildi / ne eksik / hangi risk kaldı / nasıl geri alınır** raporu üret.

### Kritik terminoloji

- **Mevcut:** Kaynak kodda veya ürün belgelerinde mekanizması bulunan özellik. Uçtan uca başarı garantisi değil.
- **Doğrulanmış:** Sabit commit'te otomatik ve/veya manuel testle gerçekten çalıştığı kanıtlanmış davranış.
- **Koşullu bulgu:** Önceki statik incelemede görülen fakat güncel eksik commit'li çalışma ağacında yeniden kontrol edilmesi gereken şey.
- **Öneri:** Henüz eklenmemiş ürün/mimari davranışı.
- **P0:** Yanlış projeye işlem, izin/güvenlik veya yalancı başarı gibi yüksek riskli konular. **P1:** Temel kullanıcı yeteneği. **P2:** Deneyim, performans ve ölçek iyileştirmesi.

---

## 1. Ürün vizyonu ve ölçülebilir başarı tanımı

Fusion birden fazla LLM'yi aynı arayüzde çağıran bir araçtan fazlası olmalı:

- Claude Code ve Codex benzeri **terminal ve masaüstü coding agent**: dosya okuma/düzenleme, test, terminal, araştırma, Git, MCP, tarayıcı, oyun geliştirme, plan, alt agent.
- Tek güçlü model kullanırken de, Nemotron gibi daha küçük/ücretsiz/yerel modellerle çalışırken de **aynı dış kalite sözleşmesi**.
- Model ne üretti diye değil **gerçek çalışan ürün ne durumda** diye karar veren doğrulama.
- Büyük işlerde planla → uygula → çalıştır → ölç → hatalı bölümü düzelt → yeniden doğrula → kaydet → devam döngüsü.
- Kullanıcıya güven veren **Project Audit / Proje Denetimi**: gerçek zamanlı araç olayları, canlı ekran, test, dosya, plan, onay, model değişimi ve kanıt.
- **Local-first**: kod, projeler, sırlar, çalışma ve mümkün olduğunca denetim kayıtları kullanıcı bilgisayarında.
- Aynı agent'a masaüstü, CLI, VS Code, tarayıcı, mobil PWA ve Telegram üzerinden bağlanma.
- macOS/Windows eşdeğerliği; iOS/Android başlangıçta **uzak istemci** (masaüstü agent'ını telefon içinde çalıştırıyormuş gibi davranma).
- Başlangıçta **0 sürekli sunucu faturası**, ücretli sağlayıcı ve platform masrafını kullanıcı tercihine/gelecekteki büyümeye bırakma.

### Önerilen SLO / kabul hedefleri — ölçülmüş gerçek değil

| Alan | Hedef |
|---|---|
| Güvenli işlemler | Yanlış proje köküne işlem: 0; yetkisiz kritik dış işlem: 0 |
| Doğrulama | Zorunlu test SKIPPED/ERROR iken “başarılı teslimat”: 0 |
| Agent | Aynı test kümesinde Codex/Claude Code ile karşılaştırılabilir bağımsız başarı; mümkünse daha yüksek kabul kriteri geçişi |
| Süre | Eşdeğer görevlerde doğrulanmış teslimata kadar Codex referansından hedef olarak en fazla **%20–30** uzun; başarı/süre dengesi izlenir |
| Model paritesi | Nemotron/Sol farkını **azaltma hedefi**; eşit sonuç garantisi verilmez, her sağlayıcı ayrı ölçülür |
| Uzun görev | 8/24/72 saatlik çok oturumlu görevlerde tutarlı devam; kapanma/çökme/bağlantı kaybı senaryoları |
| UI | Bayat test veya önizleme göstermeme; kanıt ve son güncelleme zamanı açık |
| Masaüstü | İzinli canlı ekran düşük gecikmeli; CPU/RAM tüketimi ölçülmüş; güvenli durdurma |
| Platform | Mac ve Windows'ta aynı yetenek sözleşmesi ve ayrı gerçek cihaz testleri |
| Mobil | Telefon ekranı kapalıyken değil, kullanıcı bilgisayarı açık/erişilebilirken uzaktan görev; bağlantı kesilirse durum doğru |

**Karşılaştırma metodolojisi:** Aynı başlangıç commit'i, aynı proje gereksinimleri, aynı model/bütçe/izin koşulları ile üç ayrı worktree'de Fusion, Codex ve Claude Code benchmark. Her görev en az 3–5 tekrar; maliyet, toplam süre, müdahale, kalite, regresyon, sahte başarı, güvenlik ve teslimat kaydı tutulur. Codex açık kaynak kodu kıyaslamaya uygundur; Claude Code GitHub deposunun herkese açık olması çekirdeğin bütünüyle açık kaynak olduğu anlamına gelmez.

---

## 2. Mevcut ürün envanteri — değiştirmeden önce doğrula

Repo sahibi henüz bütün commit'leri tamamlamadığını söyledi. Aşağıdaki parçaların çoğu geçmiş kod incelemelerinde **zaten var** olarak görülmüştür:

| Alt sistem | Geçmiş bulgu / durum | Yapılacak |
|---|---|---|
| Python agent çekirdeği | Var | ReAct, tool çağrıları, tur bütçesi, hata sınıflandırma ve kullanıcı onayını izle |
| `core/budget.py` | Var | Max çağrı, tekrarlama ve boş ilerleme engeli; uzun görev durmalarını ölç |
| `core/checkpoint.py`, `plan_runner.py`, `plan_checkpoint.py` | Var | Kaydetme/yeniden yükleme/kanıt doğrulamasını test et |
| `recovery.py`, `replan.py` | Var | Timeout, doğrulama, permission ve yeniden planlama testleri |
| `core/changeset.py` | Önceki incelemeye göre bellek içi snapshot | Çökme sonrası transaction bütünlüğünü kontrol et |
| `memory/turn_journal.py` | Var | Yazılamama ve kesinti sonrası devam davranışını doğrula |
| `providers/capabilities.py`, `config/model_select.py` | Var | Model gereksinim çıkarımı ve gerçek tool capability ayrımını düzelt |
| `tools/capabilities.py` | Var | Skill arama ve frontmatter parser doğruluğunu kontrol et |
| `tools/files.py`, `tools/shell.py`, `tools/search.py`, `tools/web.py` | Var | Büyük dosya, sürekli süreç, arama tamamlığı, web kaynak kanıtları |
| `tools/desktop.py` | Geçmişte macOS-only | Ortak platform arayüzü, native capture ve native input |
| `tools/chrome.py`, `chrome-extension/` | Var | Site yetkisi, MV3, native host, paketli yükleme, gerçek browser davranışı |
| `mcp_bridge/oauth.py`, MCP client | Var | CIMD/DCR/PKCE, timeout, kayıtlı client ID ve provider profilleri |
| `app/src/` React UI, Tauri/Rust app | Var | Mevcut görünüm korunarak Project Audit, canlı ekran, izin ve bildirimler |
| `appserver/session.py`, `core/events.py` | Var | Ortak görev API'si ve denetim kaydı için temel |
| ImageCreate, Fusion Kits, Talk/voice | Geçmişte var denildi | Güncel kodda yüzey/araç/çalıştırma zincirini doğrula; yeni ürün yaratılmış gibi varsayma |
| Tests/evals/CI | Var | 24–72 saat, UI/E2E, macOS/Windows paketli uygulama kapsamını genişlet |

**İlk iş:** `docs/architecture/current-inventory.md` ve `docs/audits/<COMMIT_SHA>.md` oluştur; kodu bu dosyalara bağla. Her tespit için komut, hata tekrarlama adımları, ilgili dosya ve test belirt. Önceki konuşmada adı geçen sabit satır numaraları değişmiş olabilir.

### Önceden rapor edilmiş, ancak yeniden doğrulanması gereken kod bulguları

1. `plan_runner` içindeki `run.uncovered` teslimat bilgisinin checkpoint'e yazılıp yeniden yüklendiğini kontrol et. Kayboluyorsa **P0**: kullanıcı isteğinin bir kısmı unutularak tamamlandı denebilir.
2. `cli/repl/loop.py` içinde sabit `conversation_id="repl"` ile checkpoint seçildiği varsayımını doğrula. Farklı işler birbirine karışabiliyorsa **P0**: per-run ID ve explicit resume gerekli.
3. `ChangeSet` yalnız bellekteyse çökme sonrası geri alma journal/transaction eksikliği **P0**.
4. `browser_verify.py` içinde Playwright yoksa `VerificationResult(ok=True)` ve benzeri **SKIPPED=PASS** yollarını araştır. Varsa **P0**.
5. `appserver/session.py` içindeki `MAX_AUTO_CONTINUE_TURNS=3` ve `_restore_interrupted_turn()` davranışını doğrula. Normal sohbeti otomatik uzun görev koordinatörü sanma.
6. TurnJournal yazısı başarısız olduğunda agent'ın devam etmesi durumunu test et; görev kritikse write-fail safe pause.
7. `workflow_mode: "off"` varsayılanını, ne zaman workflow'un açıldığını ve göreve göre otomatik devreye girip girmeyeceğini ölç.
8. Geliştirme sunucularını yalnız `subprocess.run(timeout=...)` ile başlatmaya çalışma; **masaüstündeki ayrı PTY/süreç yöneticisi zaten varsa** tekrar yazma.
9. `read_file` 100 KB civarında kırpıp offset'i kırpılmış veride işliyorsa gerçek aralıklı okuma/sayfalama ekle.
10. `desktop.py` macOS-only, `desktop_click` sürükleme desteklemiyor ve kısıtlı tuş sözlüğü barındırıyorsa platform arayüzünde gider.
11. Chrome `key` sentetik `KeyboardEvent` ile Tab/Backspace varsayılanlarını gerçekleştirmiyorsa native/CDP/uygun browser input yolunu tasarla.
12. Chrome `close` salt-okuma kategorisindeyse **P0** izin sınıflandırmasını düzelt; kapatılacak sekme yetkisini denetle.
13. Chrome yükleme sınırı 10 MiB ise büyük asset ihtiyacını açıkça ele al; limite takılınca sessiz başarısız olmasın.
14. Chrome ekran görüntüsünde `all_urls` gereksinimi varsa daha dar izin/aktif sekme yaklaşımını değerlendir.
15. MCP istemcisi default 10 sn init timeout kullanıyorsa sağlayıcıya göre yapılandırılabilir yap.
16. `TestsPanel.tsx` yalnız `[client]` ile yenileniyorsa bayat durum; `PreviewPanel.tsx` yalnız `[client, selectedPath]` ile yenileniyorsa aynı dosyada bayat önizleme; `FileExplorer key={revision}` local state'i sıfırlıyorsa UI state kaybı.
17. `tools/capabilities.py` sorgu `.split()` ama skill açıklaması regex ile tokenlaştırılıyorsa `pixel-art` uyumsuzluğu; çok satırlı YAML frontmatter `>`/`|` düzgün ayrıştırılmıyorsa düzelt.
18. `ToolSupport.UNKNOWN` için `native_tools=True` üretiliyorsa doğrulanmış native kabiliyetten ayrıştır.
19. `infer_task_requirements` yalnız keyword algılıyorsa oyun/görsel/çok dosya/uzun görev profili geliştir.
20. `visual_verification: false` ise bunu her iş için zorla açma; **oyun/UI profillerinde ölçüt odaklı kullan**.
21. Web araması yalnız HTML/RSS başlık-URL çıkarıyorsa tarih/kaynak/sürüm/kanıt ve kısmi sonuç bildirimini zenginleştir.
22. macOS izinlerinin Python/osascript/screencapture yardımcı süreçlerine bağlandığını test et; native Tauri/OS yaklaşımına geçişi planla.
23. Windows kurucu hedefleri (`app`,`dmg`) ve `runtime_smoke.rs` macOS `.app/Contents/Resources` varsayımlarını kontrol et.
24. `permissions.rs` Windows mikrofon/konuşma izinlerinin desteklenmediğini bildiriyorsa native davranış ekle.
25. Paketli uygulama smoke, canlı ekran, Chrome native host, voice, browser, Project Audit ve UI regresyonları CI'da gerçekten çalışıyor mu denetle.

Yukarıdakilerin herhangi biri yeni commit'lerde düzeltilmişse **tamamlandı** diye işaretle, gereksiz refactor yapma.

---

## 3. Uygulama fazları ve bağımlılıkları

> Zamanlar kesin takvim vaadi değil. Kodun eksik commit'leri ve test kapsamı görüldükten sonra görevlere ayrılacak. Faz 0 tamamlanmadan kapsamlı görsel yeniden yazıma girme.

| Faz | Ad | Öncelik | Ön şart | Çıkış kriteri |
|---|---|---|---|---|
| 0 | Mevcut durum denetimi & güvenli çalışma tabanı | P0 | Yok | Sabit SHA, açık eksik commit listesi, var/kısmi/eksik matrisi |
| 1 | Güvenilir agent & proje görev çekirdeği | P0 | 0 | Run ID, checkpoint, recovery, fail-closed verification |
| 2 | Modeller, skill'ler, araştırma & kalite profilleri | P0/P1 | 1 | Nemotron/Sol eval, model capability gerçeği, kaynak kanıtı |
| 3 | Project Audit altyapısı & UI veri bütünlüğü | P0/P1 | 1 | Gerçek olaylar, güncel UI, kanıtlı teslimat |
| 4 | Yeni Fusion tasarım dili & terminal/Talk/Kits UX | P1 | 0,3 | Mevcut ürünle uyumlu tasarım sisteminin uygulanması |
| 5 | macOS native canlı ekran & izin deneyimi | P0/P1 | 3 | ScreenCaptureKit, stabil input, yetki, mini preview |
| 6 | Windows tam eşdeğerlik & kurucu | P0/P1 | 3,5'in ortak API'si | Graphics Capture, UIA/SendInput, NSIS, smoke |
| 7 | Browser/Chrome profesyonel kurulum | P1 | 1,3 | Mağazadan tek onaylı kurulum, auto pairing, güvenlik |
| 8 | MCP OAuth & sağlayıcı kataloğu | P1 | 1 | CIMD/DCR/registered client, Meta durum tespiti |
| 9 | Görsel/oyun üretimi & zorunlu kabul kapıları | P1 | 2,3,5 | Barista benchmark, sprite + oynanış + görüntü kanıtı |
| 10 | VS Code editör entegrasyonu | P1 | 1,3 | Ortak agent servisinden diff/test/approval |
| 11 | Fusion Task Service & uzaktan güvenlik | P0 | 1,3 | Kimlikli görev API'si, pairing, RBAC, idempotency |
| 12 | Telegram + Kits uzaktan çalıştırma | P1 | 11 | Eşleştirilmiş bot, durum, güvenli onay |
| 13 | iOS/Android PWA & mobil live preview | P1/P2 | 11,12 | Responsive proje/Kit/denetim; seçmeli WebRTC |
| 14 | Dağıtım, doğrulama, imza & güncellemeler | P1/P2 | İlgili ürünler | Release/installer/updater, mağaza başvuruları |
| 15 | 24–72 saat pilotları, benchmark ve yayımlama | P0 | 1–14'ten ilgili olanlar | Objektif parity / risk raporu |

### Faz 0 — Audit, koruma, mimari haritalama

- [ ] Git temiz mi, commit edilmemiş ne var? Kullanıcı dalını koru.
- [ ] `main` ile yerel çalışma ağacındaki farkı raporla; yanlış repo/branch üzerinde çalışmayı engelle.
- [ ] Python/Tauri/React/Chrome/Kits/Talk/voice/OS katmanlarının modül haritasını çıkar.
- [ ] Her mevcut yetenek için komut, test, çalışma yolu ve platform tablosu oluştur.
- [ ] Alpha özelliklerin sınırlarını UI'da doğru işaretle; eskiden düzeltilen bug'ları açık bug gibi gösterme.
- [ ] İlgili testleri baz al: `make check`, `cd app && npm run check`, mevcut pytest/eval/CI; komutlar güncel repoya göre doğrulansın.
- [ ] Kapsam kararı: yeni marka/logo var, fakat mevcut uygulamanın çalışma sistemine saygı korunacak.

### Faz 1 — Agent'ın görevi gerçekten tamamlayabilmesi

**Kalıcı görev durum makinesi:** `QUEUED`, `PLANNING`, `RUNNING`, `VERIFYING`, `PAUSED`, `WAITING_FOR_APPROVAL`, `RECOVERING`, `FAILED`, `COMPLETED`, `CANCELLED`.

- [ ] Her çalışmaya benzersiz `run_id`; `conversation_id` ve `project_id` ayrı; bir görev diğerinin checkpoint'ini yanlışlıkla devralamaz.
- [ ] Plan/acceptance/`uncovered`/file hashes/kanıt/bütçe/onay/son başarılı adım **atomik, şemalı, sürümlü** kaydedilsin.
- [ ] Geri alma için disk üzerinde güvenli journal veya izole Git worktree. Kullanıcının commit edilmemiş değişiklikleri her zaman korunmalı.
- [ ] Çökme halinde “başarısız adımın tekrar yürütülmesi” kör tekrar olmamalı; hangi dış işlemin zaten gerçekleştiği uzlaştırılsın. Dış işlemlerde idempotency key kullan.
- [ ] `SKIPPED`, `ERROR`, `PASSED`, `FAILED` doğrulama durumları kesin ayrılmalı; required gate `SKIPPED/ERROR` ise teslimat bloke.
- [ ] Disk/transaction/journal yazılamıyorsa güvenli duraklatma.
- [ ] Oturum tekrar açıldığında checkpoint görünsün; otomatik devam sadece güvenli ve kullanıcı tarafından etkinleştirilmiş kurallar dahilinde.
- [ ] Bir adımda tekrar limiti dolarsa görevi bütünüyle unutma: yeniden planla, alt göreve ayır, model/araç değiştir veya kullanıcıdan yardım iste.
- [ ] Tüm masaüstü/web/MCP dosya değişiklikleri tek denetim raporuna girebilmeli.
- [ ] Aynı çözümü tekrar tekrar deneyen loop tespitinde neden ve kanıt raporu.
- [ ] `verification_commands: []` durumunda zorunlu oyun/E2E testleri sessizce geçilmiş sayılmasın.
- [ ] İnsan onayı olmayan üretim deploy/silme/ödeme/giriş sistemi işlemleri **asla** otomatik yapılmasın.

**Kabul testleri:** farklı REPL oturumu yanlış planı sürdüremez; eksik gereksinim checkpoint sonrası hâlâ eksik; dosya değişikliğinin ortasında `SIGKILL` sonrası tutarlı devam; Playwright yoksa zorunlu browser gate `SKIPPED`; disk doluyken tamamlandı raporu yok; 10x kesinti ve tekrar eden MCP webhook'unda çift işlem yok.

### Faz 2 — Nemotron ↔ güçlü model farkını küçülten *gerçek* sistemler

- [ ] `TaskRequirements` iki ayrı şey üretsin: **model capability** (tool calling, vision, context, structured output) ve **iş capability** (Godot, pixel-art, web, MCP, desktop, test).
- [ ] Model `UNKNOWN` araç desteği `VERIFIED_NATIVE` gibi raporlanmasın. `VERIFIED_NATIVE`, `VERIFIED_EMULATED`, `DECLARED`, `UNKNOWN`, `UNSUPPORTED` ayrımı.
- [ ] Model yeteneği ilk kurulumda ucuz smoke testle ölçülsün; model/sağlayıcı sürümü değişirse yeniden ölçüm.
- [ ] Skill sorgusu ve indeksinin aynı tokenizer'ı; `pixel-art`/`pixel art`, Türkçe/İngilizce eşanlam, teknoloji etiketleri.
- [ ] Frontmatter için gerçek YAML parser: tek satır, çok satır `>`/`|`, Unicode ve bozuk metadata testleri.
- [ ] İlgili skill keşfedilemediğinde görev başlamadan eksik uzmanlık belirt; doğru skill'i varsayılan yardımcı bağlama ekle.
- [ ] Task-specific planlama: zayıf modelde daha küçük, testlenebilir adım; güçlü modelde gereksiz planning overhead önle.
- [ ] Deterministik kararları LLM'ye bırakma: dosya, palette, lint, test, image dimensions, type-check, Git status, route/test coverage.
- [ ] API timeout/rate limit/circuit breaker/backoff/sağlayıcı fallback mevcut kodu korunup güçlendirilsin.
- [ ] Model fallback görünür olsun: hangi modelden hangi modele, neden, hangi kalite profilinde. **Sessiz kalite eşdeğerliği iddia etme**.
- [ ] Sürüm/proje/görev bazında kalite profili: tool call success, multi-file fix, compile pass, visual repair, code coverage, cost, latency, context failure.
- [ ] Model boyutu/bağlam/çoklu araç kullanımına göre kontrollü concurrency; küçük modellerde fazla paralelliğin kaliteyi düşürmesini ölç.
- [ ] Model desteklemiyorsa tool emulation ile devam edilebilir, ama açık etiket ve uyumluluk testi şart.
- [ ] Nemotron ve Sol aynı final kalite kapısını geçsin; fark kalırsa kullanıcıya dürüstçe bildir. Küçük modelin her durumda güçlü modeli yakalaması garanti değil.
- [ ] `self_review`, `reflexion`, `lessons`, `fusion synthesis` zaten varsa ölçülebilir katkısını A/B ile doğrula; her çağrıyı birkaç modelden geçirmek varsayılan olmasın.
- [ ] Çoklu model sentezinde yanıtlar çelişiyorsa kanıtla seç; kötü sentezin iyi cevabı bozmasına karşı regresyon testleri.
- [ ] Ders belleğinde hatalı/eskimiş bilgi: kaynak, oluşturulma sebebi, doğrulama, sürüm, geri alma/silme yolu.

**ChatGPT planı / özel modeller:**

- [ ] Kullanıcı isteği: API anahtarı oluşturmadan *hesabının resmen izin verdiği* ChatGPT/Codex modelleri Fusion'dan kullanılsın.
- [ ] **Yalnız resmî ve kullanım koşullarına uygun giriş/entegrasyon** (mevcut güncel OpenAI belgeleri ve uygun hesap yetkileri kontrol edilerek); oturum çerezi scraping, özel web endpoint taklidi veya auth bypass yok.
- [ ] Hesaba ait **gerçek model kataloğunu** dinamik listele; `GPT-6.1 Sol` gibi bir model adını her kullanıcıya var veya ücretsiz kabul etme. Kullanıcı hesap/planı bunu desteklemiyorsa net göster.
- [ ] Giriş için resmi OAuth/Codex app-server gibi desteklenen yolların API/araç sınırlarını ayrıştır; ChatGPT aboneliği her görüntü üretimini veya her hosted computer use aracını kapsar varsayma.
- [ ] Güçlü model ile yerel Nemotron'un aynı iş akışında karşılaştırılabilir değerlendirme verisi kaydedilsin.
- [ ] Kullanılan modelin maliyeti, plan kotası ve fallback mekanizması kullanıcıya açık olsun.

**Araştırma / search:**

- [ ] Web search sonuçları `title`, `url`, `source_type`, `retrieved_at`, `published_at?`, `snippet`, `version_context`, `confidence`, `fetch_status`, `partial` alanlarını taşıyabilsin.
- [ ] Önce resmî doküman, sonra kaynak kodu, sonra güncel topluluk içeriği; referans sürümü görünür olsun.
- [ ] JavaScript/SPA için gerektiğinde yetkili browser fallback; login wall veya CAPTCHA gerçek kaynak sanılmasın.
- [ ] Repo araması kapsamı, atlanan dosyalar, timeout ve sonuçların *kısmi* oluşu açıkça bildirilsin.
- [ ] Git/symbol/index araması büyük projede yararlı; `read_file` gerçek byte/satır sayfalama ile tamamlanabilsin.
- [ ] Doğrulanan kaynak/uygulanan kod/test sonucu arasında izlenebilir kanıt zinciri bulunsun.

### Faz 3 — Proje Denetimi (Project Audit) ve UI tutarlılığı

**Yerleşim kararı (onaylanan):** Sağdaki mevcut **Inspector** paneline `Project Audit / Proje Denetimi` adlı sekme eklenecek. Mevcut Files/Changes/Terminal/Preview kaybolmayacak. Yeni kodlama görevi başlarken varsayılan Project Audit; kullanıcı başka sekmeye geçtiğinde zorla geri dönme. Sıradan sohbette son seçim saklansın. Panel kapatıldıysa yeniden otomatik açılmasın.

- [ ] Tekil `ProjectAuditState` türet: `project_id`, `run_id`, `session_id`, `sequence`, `timestamp`, `agent`, `model`, `tool`, `requested_action`, `result`, `evidence`, `verification_status`, `redaction`, `approval_state`.
- [ ] Başlangıçta mevcut `core/events.py` olaylarını kullan (ToolStarted/Executed, ExecutionStepStarted/Verified, FilesChanged, VerificationFailed, ModelFallbackActivated, CheckpointSaved); görünmeyen event'leri tespit edip sadece gerekli olanları ekle.
- [ ] Olaylar tasarımsal kurgu değil gerçek runtime akışından gelsin. `requested` ile `verified` ayrı durumlar.
- [ ] Plan ilerleme sayısı ve **kabul kriterlerinden gerçekten geçenlerin** sayısı ayrı gösterilsin.
- [ ] Aktif model, tool, mevcut hedef pencere, son dosya değişikliği, test, diff, Git branch, geri alma checkpoint'i, fallback ve approval durumu görünür.
- [ ] Son eylemler için `PASSED/FAILED/SKIPPED/ERROR/PENDING`, tarih, delil, komut ve hangi commit'te çalıştığı gösterilsin.
- [ ] Panelin `revision`/dosya olaylarına aboneliği tam; TestsPanel bayat bilgisi, PreviewPanel aynı dosyayı cache'ten gösterme ve FileExplorer state reset sorunları regresyon testleriyle kontrol edilsin.
- [ ] Kullanıcı geçmişteki en son **kanıtlı** sonuca ulaşabilsin; eski kanıt yeni değişiklikle otomatik **stale** olsun.
- [ ] Büyük ekran görüntüsü veya gizli veri denetim kayıtlarında varsayılan saklanmasın; saklama süresi ve dışa aktarma seçenekli.
- [ ] Panelde duraklat/devam/durdur, detaylı log, diff, onay, dosyaya git, terminale geç ve güvenli rollback kontrolleri bulunsun.
- [ ] Mac/Windows aynı görünüm; dar ekran ve split panel resize testleri.

Önerilen görünüm: Üstte **aktif görev & model**, ortada **plan** ve **kalite kapıları**, altta **kanıtlı etkinlik akışı**, gerektiğinde **canlı masaüstü kutusu**. Bütün ekranı grafik/dashboards kalabalığına dönüştürme; aşamalı bilgi açıklaması (progressive disclosure) kullan.

### Faz 4 — Son onaylanan marka / UI / terminal / avatar yaklaşımı

**Kesin alınmış tasarım kararları:**

- **Kabul edilen logolar:** Kullanıcının yüklediği iki görsel. Orbit/halkalı logo **başlangıç animasyonunda**; akıcı dönüşümle ana **F** logosuna morph; uygulamada ana logo F. İki referans `assets/logo_orbit_reference.png` ve `assets/logo_f_reference.png`.
- Fusion kelime işareti/wordmark'ın sevilen **sade modern geometrik tipografi** karakteri korunacak. Görselden font adı veya font lisansı tahmin etmeyin; marka için özgün vektör lettering veya yasal lisanslı font ailesi seçin.
- **Gradyan yalnız ana logo, onboarding hareketi, çok sınırlı marka anlarında.** Neredeyse hiçbir büyük panel/CTA/surface gradyanla boyanmayacak.
- **Light/system theme varsayılan; dark tema ayrıca profesyonel seçenek.** Tekdüze siyah, uzay arkaplanı, camdaki neon parlaklıklar, sahte hologram, parlak masallar yok.
- Mevcut Fusion uygulamasının UI iskeletine sadık kal; yeni tasarım eski ekranların fonksiyonlarını yok etmesin. Referans mockup'lar *gerçek ekran görüntüsü değildir*.
- Apple benzeri net tipografi, doğal macOS yerleşimi, native/yarı-native görsel his, dengeli beyaz alan, ölçülü köşe yarıçapı, sakin gölge, erişilebilir kontrast.
- Marka/palette önerisi başlangıç token'larıdır, commit sonrası gerçek renklerle A/B yapılacak: `--surface: #FAFBFD`, `--panel: #FFFFFF`, `--panel-subtle: #F4F6F9`, `--border: #E2E6ED`, `--text: #1B2230`, `--muted: #697487`, `--accent: #415EF5`, `--accent-hover: #334DD7`, `--success: #18855D`, `--warning: #AD7412`, `--danger: #C64047`. Dark nötrleri ayrıca üret; **logo gradyanı bu semantik renklerin yerine geçmesin**.
- Ölçüler token tabanlı: `4/8/12/16/24/32px` spacing, `8/10/12px` radius, touch hedefi >= 44px (mobil), klavye focus ring ve kontrast.
- Sol sidebar/üst bar/sağ Inspector/terminal/workspace mevcut bilgi mimarisine göre korunmalı. Yanlış repodan üretilen “Kanban ana ekran” mockup'ını mevcut Fusion'ın birebir resmi sanma.

**Terminal/TUI:**

- [ ] Mevcut terminal ANSI, scrollbar, kopyalama, PTY, `zsh`/PowerShell/CMD, süreç sürdürme, exit code, komut geçmişi davranışı aynen korunacak.
- [ ] Kod fontu tek mono aile ile, iyi ligature/ağırlık/line-height. Terminal ana arkaplanı koyu olabilir; uygulama kabuğu light. ANSI çıktısında erişilebilir 16 renk ve truecolor testleri.
- [ ] Büyük ASCII banner varsa modern ve kompakt görünüm opsiyonu; yetenekleri kaldırma.
- [ ] Terminalde süreç açıkken Project Audit canlı kalır. Terminal altına onaylanan **mini canlı masaüstü preview**, küçült/büyüt/gizle; panel seçildiğinde kontrolü ele geçirmez.
- [ ] Dış görüntü oluşturma yerine mevcut PTY/süreç bağlamını kullanan, komutun gerçekten çalıştığını bilen UI.

**Kits ve Talk avatarları — eski AI slop karakterleri reddedildi:**

- [ ] Her Kit için çok sade, 24–64px'de tanınan simgesel avatar: plan (adım/katman), code (bracket), verify (check), research (lens), browser (sekme), Talk (orbit/voice). Ucuz minik çizgi-film robot üretme.
- [ ] Avatar geometri temelinde **ana logo ve orbit hareket dilinden** türetilsin; minimal fill/line çizimleri; hafif semantik renk.
- [ ] Kits Builder/Library: kit ikonunu, araç/izin/model/süreç/kullanım sınırını ayrı göster; oluştur/düzenle/klonla/sil/çalıştır akışı.
- [ ] Talk/Voice: tek odak noktası olan sakin pulse/orbit, konuşma dalgası yalnız gerçek ses durumundan; `Idle`, `Listening`, `Thinking`, `Speaking`, `Muted`, `Disconnected` durumları ve erişilebilir azaltılmış hareket modu.
- [ ] Agent avatars birer kişi gibi sahte fotoğraf olmak zorunda değil; rol/işlev simgesi ve gerektiğinde kullanıcı seçimi.
- [ ] Animation düşük enerji: logo splash kısa ve atlanabilir; `prefers-reduced-motion` ile statik F.
- [ ] Açık izin isteği, hata, boş durum, silme onayı, job tamamlandı, bağlantı kesildi için tutarlı dialog/toast/notification bileşenleri.
- [ ] İngilizce/Türkçe lokalizasyon; uzun metin ve Windows farklı font rasterizasyonu testleri.

### Faz 5 — macOS native canlı desktop capture ve izinler

**Onaylanan ürün davranışı:** Codex benzeri **gerçek zamanlı görüntü akışı**, tekrarlı `screencapture` ile disk üzerinde her adımda PNG biriktiren yaklaşım değil. Kullanıcı Project Audit'te canlı küçük görüntü görür; Terminal altındaki mini ekran seçmeli sürekli görünür. Model ise video akışındaki seçilen kareleri, eylem sonrası kanıt için gerektiğinde analiz eder — her kareyi LLM'ye gönderme.

- [ ] Tauri/Rust içinde macOS `ScreenCaptureKit` tabanlı `SCStream`/pencere veya ekran seçimi; aynı anda yalnız tek capture oturumu çoğu durumda yeterli.
- [ ] `start`, `stop`, `pause`, `resume`, `latest_frame`, `list_sources`, `status` ortak API.
- [ ] Capture GPU/buffer üzerinden UI'a, disk kaydı varsayılan kapalı. Boyut/FPS/adaptive kalite hedefi: ekonomik 8FPS, dengeli ~15FPS, yüksek ~30FPS; gerçekten ölçmeden performans iddiası verme.
- [ ] Model için `frame-at-action`, değişim algısı ve gerekçeli kanıt; aynı stream iki tüketici: live preview ve model.
- [ ] Native mouse/keyboard: click, right/double click, drag/down/move/up, scroll, Unicode/IME, kısayollar, pencereler, çoklu monitör, koordinat dönüşümü, focus.
- [ ] Python `screencapture`, `osascript System Events`, Python `ApplicationServices` yollarını **çalışan native alternatif hazır olduktan sonra** geçişle kaldır/azalt; CLI fallback gerekiyorsa açık ve ayrı.
- [ ] Native macOS Accessibility/Screen Capture/Automation/Notifications izinlerini tek izin yöneticisi; yalnız ihtiyaç anında sor. macOS zorunlu kullanıcı izni, parola/Touch ID, TCC kontrolü **atlanamaz**.
- [ ] İlk açılışta sırf coding agent var diye ekran/mikrofon/Accessibility izni isteme. İlk computer-use anında açıklayıcı Fusion ekranı; macOS kendi izin penceresi.
- [ ] Kullanıcı görüyorsa paylaşım aktif göstergesi ve tek tıkla kapatma; FUSION kendi ekranını yakalayıp ayna tüneli oluşturmamalı.
- [ ] İzin reddi/revocation/uyku/ekran kilidi/ekran değişimi/yeni uygulama/çoklu monitör durumları için tanımlı davranış.
- [ ] macOS imza/notarization, uygulama kimliği, helper process ownership; kullanıcıya “Python 3.x erişim istiyor” gibi gereksiz uygulama ismi yerine mümkün olduğunca Fusion kimliği görünmeli. Sistemin gösterdiği ad TCC sürece bağlıdır; bunu test etmeden kesin garanti verme.
- [ ] Electron/Tauri WebView görüntü aktarımında backpressure, kayıp kare, memory leak, thermal throttle ölçümleri.
- [ ] Video akışı otomatik buluta gönderilmez; sistem gerektiriyorsa kullanıcı onaylı hassas bölge maskelemesi.
- [ ] Yerel/native macOS bildirimler: yalnız görev tamamlandı, onay gerekiyor, bağlantı koptu gibi anlamlı olaylar; her tıklama için notification gönderme.

### Faz 6 — Windows eşdeğerliği

- [ ] Ortak `DesktopBackend`: macOS için ScreenCaptureKit/Accessibility/CoreGraphics; Windows için `Windows.Graphics.Capture` ve `UI Automation` + `SendInput`.
- [ ] Aynı API ve JSON sonuç sözleşmesi; araçlar Windows'ta 'macOS-only' hatası vermez (gerçekte desteklenen işlemler için).
- [ ] DPI aware input, %100/125/150/200 scaling, birden çok monitör, negatif koordinat, alt-tab ve focus kaybı, hızlı hareket, drag-drop, Unicode/Türkçe klavye/IME.
- [ ] UAC/Secure Desktop ve daha yüksek integrity level uygulamaları atlatma yok; kullanıcının müdahalesi gerektiğinde doğru göster.
- [ ] Windows.Graphics.Capture canlı küçük ekran, ekran seçim picker/indicator, frame throttling ve WebView2 gösterimi.
- [ ] Windows için görev süreci/cmd/PowerShell PTY, `npx`/`uvx` MCP, dosya yolu ve quoting testleri.
- [ ] WebView2 Runtime varlık/onarım kontrolü; Windows ARM64 yalnız gerçek testten sonra hedef.
- [ ] Tauri NSIS MSI (önce NSIS) kurucu, mimariye uygun Python runtime/resources, portable/installed uygulama ayrımı, otomatik rollback ve onarım.
- [ ] `runtime_smoke.rs` gibi `.app/Contents/Resources` varsayımları cross-platform resource API ile değişsin.
- [ ] Windows microphone/speech/notification izin durumu gerçek OS üzerinden raporlansın.
- [ ] Windows update, kilitli EXE/DLL, antivirus, SmartScreen ve imza testleri.
- [ ] macOS ve Windows aynı kabul senaryolarını çalıştırır; platformun sistem izni/görsel sınırları şeffafça raporlanır.

### Faz 7 — Chrome / browser entegrasyonu ve kurulum (çok önemli düzeltme)

**Kullanıcı isteği:** Fusion ilk açıldığında Chrome eklentisi ile elle `chrome://extensions` → Developer mode → “Load unpacked” yapmak zorunda kalınmasın. Mac ve Windows'ta birinci sınıf, **tek tıkla** çalışan profesyonel bağlantı.

**Platform gerçekliği:** Normal kullanıcı Chrome profiline üçüncü taraf bir uygulamanın **kullanıcı onayı olmadan sessiz Chrome eklentisi yüklemesi** güvenli/resmî dağıtım politikası değildir ve her Chrome kurulumunda vaat edilemez. Yapılabilir profesyonel çözüm:

- [ ] Chrome Web Store resmi eklenti yayını (mağaza geliştirici kayıt ücreti tek seferlik olabilir; **0 bütçeli alfa** döneminde geçici olarak elle yükleme veya Chrome izinli alternatif kullanılır).
- [ ] Fusion ilk açılışında Chrome mevcutsa **“Fusion Browser'ı Bağla”** tek adımlı onboarding; kullanıcıyı doğru Web Store sayfasına götür; Chrome'un yükleme/izin onayını kullanıcı verir. Eklenti kurulunca native host ile otomatik eşleşir. İlk açılışta sürekli pop-up gösterme; erteleme seçeneği.
- [ ] Tauri kurucusu Chrome Native Messaging host kaydını macOS/Windows'a **otomatik** yerleştirebilir; bunu eklenti kullanıcı onayıyla karıştırma.
- [ ] Chrome mağaza eklenti ID'si `allowed_origins` içinde doğru; update/signature/version matching; kaldırmada host kaydı güvenle temizlenir.
- [ ] Eklenti kullanıcıya port/token kopyalatmasın; yerel pairing kısa ömürlü, açık izinli ve doğrulanmış olsun.
- [ ] Chrome sayfa/alan adı izinleri mümkün olan en dar kapsamda (`activeTab`, site bazlı grant); şifre/2FA/kart alanı koruması devam.
- [ ] `chrome_close` yetkisi read-only olmamalı; kapatılan sekme izinli mi, veri kaybı riski var mı.
- [ ] Sentetik DOM `KeyboardEvent` ve click gerçek kullanıcı etkileşimleriyle aynı değildir; kritik işlemler için izinli, uygun tarayıcı kontrol mekanizması, test edilmiş input sözleşmesi.
- [ ] `open`, navigate, forms, scroll, tabs, back, file upload, download, screenshot, hover; browser kendi sayfalarında kapsam dışı sınırları UI'da dürüstçe göster.
- [ ] Büyük asset upload limiti ve site/video/API erişimi için alternatif güvenli yollar.
- [ ] Screenshot izin kapsamı en dar izin modeliyle araştırılsın; `all_urls` zorunluluğu varsa kullanıcıya açıkça göster.
- [ ] Eklenti state/sürüm değişimi, Chrome kapanması ve masaüstü app kapanmasında otomatik toparlanma.
- [ ] Native host güvenlik sınırları, handshake, eklenti ID kontrolü, origin allowlist ve token rotation.
- [ ] Kurulum doğrulaması: temiz Mac/Windows + Chrome kurulu/kurulu değil + çok profil + update + uninstall + site permission denied.
- [ ] Alternatif: uzantı gerektirmeyen açıkça izinli CDP/browser-managed profile modu; bunun Chrome profil güvenlik sınırlarını ve kullanıcı tercihlerini ayrı değerlendir.

### Faz 8 — MCP OAuth “Connect Account” ve Meta gibi sağlayıcılar

- [ ] Güncel MCP Auth standardına göre `Protected Resource Metadata` ve Authorization Server Metadata keşfi; issuer, scopes, redirect, PKCE/state doğrulaması.
- [ ] **CIMD** (Client ID Metadata Document) destekliyorsa Fusion'ın yayımlanmış HTTPS metadata URL'sini kullan; statik HTTPS barındırma başlangıçta ücretsiz olabilir.
- [ ] **DCR** sağlayıcı destekliyorsa otomatik kayıt ve güvenli kayıt saklama.
- [ ] **Pre-registered client ID** istiyorsa Fusion kurucusu adına uygulama kaydı/approval. Kullanıcıdan her seferinde client ID sorma, ama sağlayıcı app review istiyorsa bunu kodla aşamazsın.
- [ ] Meta/Facebook/Instagram/Ads MCP özelinde hangi OAuth sunucusunun kullanıldığı, redirect URI gereksinimi, Meta App Review/Business Verification/scopes ve gerçek provider politikası araştırılsın; tek bir global CIMD kimliği Meta'da otomatik yetki sağlar diye iddia etme.
- [ ] `localhost:8765` sabit port kullanımı çakışma/redirect policy açısından test edilmeli; loopback için uygun dinamik port veya custom scheme ancak sağlayıcı izin veriyorsa kullanılmalı.
- [ ] Confidential client secret, açık kaynak uygulamaya **gömülmemeli**. Public client + PKCE tercih; yalnız backend secret isteyen sağlayıcıda sıfır backend şartını revize etmek gerekebilir.
- [ ] Scope bazlı yükseltme, refresh token rotation, revocation, çok hesap, provider/tenant isolation, yanlış hesabı seçmeyi engelleme.
- [ ] Yerel OS vault/credential store; token hiçbir log, prompt, Telegram mesajı, repo dosyası, UI tooltip içinde görünmez.
- [ ] UI: `Bağla`, `Bağlı`, `Tekrar yetkilendir`, `İzin eksik`, `Servis client registration gerektiriyor`, `Bağlantıyı kaldır`.
- [ ] Tool list değişimi, yavaş MCP init, kopma/retry, idempotent dış işlem, zorunlu MCP capability fail-closed.
- [ ] GitHub, Google, Notion, Meta vb. için sağlayıcı profilleri sağlayıcının güncel API/koşullarına göre hazırlanacak; desteklenmeyen OAuth yolu otomatik olmuş gibi gösterilmeyecek.

### Faz 9 — Görsel kalite ve oyun üretimi (pixel-art barista kabul örneği)

**Örnek görev:** “Pixel-art barista oyunu: müşteri/sipariş/kahve hazırlama/para/upgrade/kayıt/anlamlı animasyon/tutarlı görsel/UI. Gerçekten oynanabilir şekilde teslim et.”

- [ ] İlk aşamada kullanıcıdan motor (Godot/Unity/web) ve gerekirse asset stil referansı alın; kullanıcı belirtmezse mantıklı açık varsayımı ve seçimi kaydet.
- [ ] Makine okunur **Game Spec**: fonksiyonel acceptance, görsel stil sözleşmesi, ekonomi, kontroller, kaydetme, sahne akışı, platform, performans.
- [ ] Pixel-art kısıtları: tile/sprite çözünürlükleri, ölçekleme, palette, perspektif, sprite oranları, animasyon sheet'leri, alpha/transparency, frame tutarlılığı.
- [ ] ImageCreate görsel ürün yüzeyi varsa, coding agent tarafından çağrılabilen yetkili `asset_generate`, `asset_edit`, `asset_validate` araç sözleşmesi ekle. Desteklenmeyen modelin resim ürettiğini iddia etme; yerel pixel-art deterministik üretim veya yetkili ayrı sağlayıcı kullan.
- [ ] Asset lisansı/kaynağı/kullanım hakkı açık. Başka oyunun görselini kopyalama.
- [ ] Godot headless import/build, açılış testi, log analizi, sahne bağımlılıkları, test edilen input akışları.
- [ ] Playwright/web oyununda sayfa açılma/konsol/overflow; native oyunda screenshot/video/frame analysis.
- [ ] Gerçek render screenshot; görsel test: UI taşması, hizalama, boş sprite, yanlış palet, okunmaz etiket, tile seam, animasyon bozulması.
- [ ] **Estetik kalite** öznel: yalnız model “güzel olmuş” diyerek geçemez; referansla karşılaştırma, ölçülebilir kurallar ve gerekirse kullanıcı değerlendirmesi.
- [ ] Test başarısızsa tüm oyunu baştan yazmak yerine asset/sahne bazında hedefli düzeltme; mevcut çalışan özellikler için regresyon kapısı.
- [ ] Bağımsız final kabul testi; `PASSED`, `FAILED`, `SKIPPED`, `ERROR` ayrımı. “Derleniyor” = “oynanabilir” değil.
- [ ] Kullanıcıya build/oyun dosyası, gerçek görsel kanıt, uygulanan dosyalar, test raporu ve eksik alanların listesi.
- [ ] Aynı görevde Codex/Claude/Fusion karşılaştırması, %20–30 süre hedefi ve kalite artışı objektif ölçülsün.

### Faz 10 — VS Code gerçek eklentisi

- [ ] Bir ayrı LLM agent yazma; mevcut authenticated Task Service'e bağlan.
- [ ] Extension host tarafında workspace URI, aktif dosya/seçim, diagnostics, diff, terminal, Git durumu ve proje bağlamını yetkiyle paylaş.
- [ ] Komut paleti: Ask Fusion, Fix with Fusion, Review diff, Run tests, Project Audit, Open Kits, Resume task.
- [ ] Sağ panel/Chat/Webview yalnız gereken özel UI için; VS Code native diff/diagnostic/terminal API'lerinden yararlan.
- [ ] Local agent yoksa yükleme/bağlantı akışı; izin istemeden kodu dış sağlayıcıya gönderme.
- [ ] VSIX ile ücretsiz alfa test, Visual Studio Marketplace yayımlama, domain/yayıncı doğrulama şartları karşılanınca rozet.
- [ ] Uzantı/Mac/Windows proje durumu birebir senkron, tek `run_id`.

### Faz 11 — Local-first Fusion Task Service & Remote Access

**Mimari:** Desktop/CLI/Chrome/VS Code/PWA/Telegram → **kimlikli görev servisi** → Fusion Agent/Kits/Model/MCP/Desktop → **Project Audit**.

- [ ] `tasks.create`, `tasks.status`, `tasks.events`, `tasks.cancel`, `tasks.pause`, `tasks.resume`, `approvals.respond`, `kits.list`, `kits.run`, `devices.pair`, `devices.revoke` gibi sürümlü RPC sözleşmesi.
- [ ] `gateway`in model proxy'si olma rolünü doğrudan internetten erişilen, kimliksiz bilgisayar kontrolüne dönüştürme.
- [ ] Varsayılan `127.0.0.1`/OS local IPC; internete açık bind varsayılan **yok**.
- [ ] Cihaz eşleştirme tek kullanımlık QR/kod + masaüstünden onay, kısa ömürlü token, cihaz bazlı yetki, kolay erişim iptali.
- [ ] Gerektiğinde local LAN şifreli bağlantı veya kullanıcının yapılandırdığı özel VPN/tünel; kimlik bilgisi olmayan hiçbir uzaktan tool çağrısı yok.
- [ ] Görev, olay ve onaylarda `run_id`, monoton sequence, dedupe, idempotency, HMAC/nonce/signed session; replay'i engelle.
- [ ] İzin ayrımı: read-only/project-write/desktop-control/MCP-write/production-deploy; uzaktan erişim asla yerelden daha yüksek yetkili olmasın.
- [ ] Dış servisler, dosya silme, deploy, ödeme, kimlik doğrulama, üretim ortamı için step-up / ayrı cihaz onayı.
- [ ] Token/log/proje/ekran/video varsayılan buluta gönderilmesin; hassas veri redaction.
- [ ] Bilgisayar kapalı, uyku, kilitli ekran, internet kopması ve ekransız background görevleri ayrı ele al.

### Faz 12 — Telegram uzaktan görev ve Kits

- [ ] **İlk 0 aylık altyapı maliyeti**: her kullanıcı kendi Telegram botunu BotFather ile oluşturur; lokal Fusion `getUpdates` long polling ile **dışarı bağlantı** kurar; açık gelen port yok.
- [ ] Desktop Ayarlar → Uzaktan Erişim → Telegram: token gir, güvenli sakla, tek kullanımlık pairing, yalnız belirli Telegram user/chat ID, DM only varsayılan.
- [ ] Telegram slash komutları: `/projects`, `/tasks`, `/status`, `/kits`, `/kit <slug>`, `/pause`, `/resume`, `/cancel`, `/audit`, `/devices`.
- [ ] Kit çalıştırma yalnız açıkça remote-allowed kit'lerde; kitin normal araç izinleri otomatik genişlemez.
- [ ] Uzaktan kullanıcı bir mesajla proje seçer/görev oluşturur; masaüstü aynı görevi aynı Project Audit üzerinden görür.
- [ ] Onay gerektiren işlemde Telegram bildirimi + güvenli (yerel desktop veya passkey destekli HTTPS kontrol paneli) step-up; bot üzerinden riskli işlemleri tek tıkla kör onaylama yok.
- [ ] Normal Telegram bot konuşması **uçtan uca Secret Chat değil**; bot token/şifre/sır/özel veri sohbete yazdırma. Hassas bilgiler güvenli panelde.
- [ ] Bildirim özeti düşük hacimli; kod/özel repo içeriğini Telegram'a otomatik dökme.
- [ ] Telegram bot mesajı tekrar gelirse aynı aracı iki defa çalıştırma.
- [ ] Bağlantı iptali, parola/token rotasyonu, günlük, cihaz listesi, başarısız giriş hız sınırı.
- [ ] İkinci aşama ortak resmî Fusion botu istenirse merkezi yönlendirme/yetki ve ücretsiz kota riski ayrıca değerlendirilecek; sıfır sunucu garantisi yok.

### Faz 13 — Mobil PWA / iOS / Android

- [ ] Aynı local-first agent'ın mobil **istemcisi**: project list, chat/task, audit, Kits, live preview, approvals, notification settings.
- [ ] iPhone Safari + Android Chrome PWA: responsive, HTTPS gerekli uzak kullanım, Home Screen kurulumu; mobil OS yetenek farkları UI'da doğru.
- [ ] Tam native iOS/Android mağaza sürümleri daha sonra; başlangıçta Apple/Google geliştirici üyelikleri olmadan PWA.
- [ ] Aynı Wi-Fi üzerinde doğrudan yerel bağlantı; uzaktan kullanım için kullanıcı seçimiyle VPN/tünel/pairing. NAT/CGNAT her durumda ücretsiz direkt bağlanma sağlamayabilir.
- [ ] WebRTC canlı ekran istendiğinde kullanıcı onayı; bazı ağlar TURN relay gerektirir (bant maliyeti potansiyel). Relay yoksa görev olayları/snapshots fallback.
- [ ] Telefon kendi başına Mac/Windows masaüstünü çalıştırmaz; bilgisayar uyku/kapalıysa görev yürüyemez. Bu durum açıkça gösterilsin.
- [ ] Mobil Project Audit, duraklat/iptal, onay ve başarı kanıtı; video ve komut ekranı hantal olmamalı.
- [ ] Telegram Mini App ileriki aşama: server-side signed initData validation + HTTPS; ayrı app şart değil.

### Faz 14 — Resmî dağıtım & güvenilir güncelleme

- [ ] Mac: `dmg`, Developer ID signing, notarization, Tauri updater imzası, güvenilir helper identity, migration/uninstall.
- [ ] Windows: NSIS, imzalama mümkünse, runtime/update smoke, SmartScreen uyarılarını giderme; yeni sertifika bile %100 warnings-free garantisi vermez.
- [ ] Browser: Chrome Web Store geliştirici hesabı ve review; otomatik native host, tek tıkla **kullanıcı onaylı** eklenti yükleme.
- [ ] VS Code: Marketplace publisher ve gerekli domain doğrulaması, düzenli yayın geçmişi.
- [ ] iOS: PWA başlangıçta ücretsiz; App Store'a resmi yayın Apple Developer ücretine bağlı.
- [ ] Android: PWA veya doğrudan APK ücretsiz; Play Store hesabı ücretli.
- [ ] Her release: SBOM, checksums, dependency scanning, otomatik güncelleme ve rollback; güvenlik politikası.
- [ ] GitHub Releases/GitHub Actions/ücretsiz statik dokümantasyon; kota ve kullanım şartlarını izleme.
- [ ] Resmî domain zorunluluğu ihtiyaç çıktığında alınabilir; ücretsiz `pages.dev`/`github.io` MVP metadata için bazı koşullarda yeterli, bütün publisher/OAuth doğrulamaları için garanti değil.

### Faz 15 — CI, güvenlik, uzun görev ve kabul benchmark'ları

- [ ] Python unit/static + property tests; Tauri Rust unit/smoke; React RTL/Playwright E2E; Chrome MV3 browser E2E; MCP OAuth mock AS tests.
- [ ] Gerçek macOS + Windows makine matrisinde full package install/update/uninstall, mic, screenshot, controls, terminal, voice, Kits, web/MCP.
- [ ] 8/24/72 saat gerçek görev; en az 10 planlı çökme/yeniden açma; veri tutarlılığı ve yanlış plan testi.
- [ ] Meta OAuth gibi vendor sandbox testleri; kayıt yöntemi/CIMD/DCR/PKCE/refresh/revocation.
- [ ] Web araştırma kaynağı/versiyon/kısmi sonuç, prompt injection, SSRF, credential leakage, workspace escape testleri.
- [ ] Windows çoklu monitör/DPI ve macOS çoklu Spaces/full-screen; canlı frame leak/buffering testleri.
- [ ] Godot barista oyunu; gerçek asset, derleme, playable flow ve gözlemlenebilir görsel kriterler.
- [ ] En az üç model sınıfı: güçlü ChatGPT/Codex entitlement varsa onunla; Nemotron; diğer yerel; aynı kabul seti.
- [ ] Benchmark raporunun kriterleri görev başarı/süre/fiyat/insan müdahalesi/boş tekrar/yanlış onay/olay eksikliği/CPU-RAM.
- [ ] Seçili projenin eski sürümündeki regresyon testleri finalde her zaman geçmeli.

---

## 4. İş akışı sözleşmeleri (örnek, kesin API şeması değil)

### Task & Audit kaydı

```json
{
  "run_id": "run_<uuid>",
  "project_id": "project_<uuid>",
  "session_id": "session_<uuid>",
  "state": "VERIFYING",
  "goal_spec_version": 3,
  "acceptance": [
    {"id":"build", "required":true, "status":"PASSED", "evidence_id":"ev_01"},
    {"id":"visual", "required":true, "status":"PENDING", "evidence_id":null}
  ],
  "events_cursor": 401,
  "last_checkpoint_id": "cp_08",
  "active_model": "provider/model-from-verified-catalog"
}
```

```json
{
  "sequence": 402,
  "run_id": "run_<uuid>",
  "kind": "desktop_action",
  "requested": "Open the game scene",
  "executed": true,
  "verified": false,
  "verification_status": "PENDING",
  "evidence_id": null,
  "user_approval": "NOT_REQUIRED",
  "timestamp": "<ISO-8601>"
}
```

**Kural:** UI'da “işlem gönderildi” sonucunun yeşil **“doğrulandı”** olarak boyanması yasak. Ekran paylaşımı kapatılınca video akışı gerçekten durmalı; sadece UI'dan gizlenmesi yeterli değil.

### Remote izin kapsamları

```text
project.read
project.write
agent.run
agent.pause
agent.cancel
kits.list
kits.run.<kit-id>
desktop.observe
desktop.control
mcp.read.<provider>
mcp.write.<provider>
production.deploy
```

Varsayılan uzak eşleştirme **read-only + izinli agent task**; desktop.control, MCP write ve production.deploy explicit kullanıcı seçimi/step-up.

---

## 5. Tasarım dosyaları ve ne için kullanılacakları

> **En son seçilen tasarım dilini** referans kabul et. Bu görseller **çalışan Fusion'ın birebir screenshot'ı değil**; bazı önceki konseptlerde yanlış Fusion reposunun ekran kurgusu kullanılmış olabilir. Gerçek UI implementasyonundan önce mevcut `app/src/` kodu ve gerçek uygulama screenshot'larıyla karşılaştır.

| Dosya | Amaç | Onay / sınırlama |
|---|---|---|
| `assets/logo_orbit_reference.png` | Açılış/splash orbit mark | **Kullanıcı çok beğendi**. Açılışta akışkan animasyonla F'ye dönüşsün. Küçük referans görselden nihai yüksek çözünürlüklü vektör yeniden çizimi gerekir. |
| `assets/logo_f_reference.png` | Ana app logosu, favicon, Dock/Taskbar | **Kullanıcı çok beğendi.** Mevcut geometrinin özgün SVG üretimi/testi gerekir. |
| `assets/ui_board_concept.png` | Açık tema, sakin üç kolon ve UI yoğunluğu referansı | Görsel kalite/düzen referansı; **Kanban board'u mevcut Fusion'ın kesin gerçek ekranı sanma.** |
| `assets/ui_terminal_project_audit_concept.png` | Terminal + Project Audit + canlı mini ekran yerleşimi | **Konsept**. Terminal komut/metinleri repo gerçek API'siyle düzeltilecek. |
| `assets/ui_agents_talk_concept.png` | Talk, Kits/agent avatar yaklaşımı, voice UX | **Konsept**. Gerçek Talk/Kits modülleri ve mevcut avatarlar incelendikten sonra uygulanacak. |

![Beğenilen logo referansı — orbit](assets/logo_orbit_reference.png)
![Beğenilen ana F logosu](assets/logo_f_reference.png)

![Hafif, profesyonel UI yönü](assets/ui_board_concept.png)

![Terminal + Proje Denetimi](assets/ui_terminal_project_audit_concept.png)

![Kits, ajanlar ve Talk konsepti](assets/ui_agents_talk_concept.png)

### Görsel tasarımda kesinlikle kaçınılacaklar

- Uygulamanın tamamını uzay/navy/gradyan/neon yapma.
- Şekilsiz, plastik 3D yüzlü maskotlar / şirin robotlar ekleme.
- Gerçek veri olmadan sahte “Code Quality A”, “Verified 100%”, “0 errors”, “GPT-4o”, “Claude 3.5” gibi bilgiler üretime sabitleme.
- Uygulamanın var olan işlevlerini sırf mockup güzel diye silme.
- Ekrandaki metinleri/ikonları resme gömüp kodlanmış UI sanma; gerçek React components, semantik HTML, erişilebilir durum ve token sistemi kullan.
- Logo örneklerindeki gradient rengini her butona taşıma. Marka renkleri yalnız yönlendirici küçük vurgu olarak kullanılmalı.

### Tasarım sisteminin gerçek çıktı formatı

- `tokens.css` veya eşdeğer token modülü: semantic colors/typography/spacing/radius/shadows.
- Component gallery/Storybook mevcut tooling'e uygunsa: Button, Input, Tabs, InspectorPanel, AuditRow, StatusPill, Timeline, Modal, Toast, TerminalPane, LivePreview, ApprovalSheet, KitAvatar, VoiceOrb.
- Her bileşen için Light/Dark/Focus/Hover/Disabled/Loading/Error/Empty/ReducedMotion.
- SVG logo vektörü, splash animasyonu (web animasyon veya Lottie yerine mevcut stack'e en iyi uyan erişilebilir çözüm) ve 16/32/128/256/512px icon export; favicon, macOS `.icns`, Windows `.ico`, Chrome, VS Code ve PWA varlıkları.
- UI screenshot goldens: macOS/Windows, 100%/150% DPI, dar/geniş, Türkçe/İngilizce, 2 tema.

---

## 6. 0 ücretli başlangıç stratejisi: gerçek ve dürüst maliyet tablosu

| İhtiyaç | 0 aylık maliyetli başlangıç yolu | Sınır / ileride ücret ihtimali |
|---|---|---|
| Model çıkarımı | Yerel Ollama/vLLM/LM Studio/Nemotron veya kullanıcının kendi izinli model hesabı | Donanım, elektrik, sağlayıcı kotası, ayrı API faturasına tabi olabilir |
| Kaynak + build | Public GitHub repo, GitHub Actions uygun ücretsiz runner kotaları | Limits, saat, storage ve özel repo şartları |
| Desktop kurulum | GitHub Releases `DMG`/Windows installer | Apple notarization, Windows code signing, marka güveni için ücret olabilir |
| Static site / docs / CIMD | GitHub Pages veya Cloudflare Pages free tier | Domain ve bazı OAuth/publisher doğrulamaları ücretli olabilir |
| Chrome Browser | Alfa dönemde geliştirici yükleme; resmî yayına geçince Web Store | Sessiz auto-install yasak/garantisiz; mağaza kayıt ücreti |
| VS Code | `.vsix` ve Marketplace | Publisher/domain doğrulaması şart olabilir |
| iPhone/Android | Responsive PWA | App Store / Play Store resmi yayın üyelik ücretleri |
| Telegram | Kullanıcı bilgisayarında long-polling bot adapter | Tek ortak bot/çok cihaz/24x7 servis büyürse yönlendirme altyapısı |
| Mobil uzaktan canlı ekran | Aynı LAN, kullanıcı VPN'i veya uygun P2P | NAT/CGNAT/TURN relay/bant genişliği masrafı; %100 bedava global live video garantisi yok |
| Veri | Yerel SQLite/dosya/vault | Kullanıcının disk alanı ve yedekleme ihtiyacı |
| Bildirim | Yerel OS bildirimleri, Telegram | iOS/Android push ve sürekli server gereksinimi platforma göre değişebilir |
| OAuth | CIMD/DCR/free static metadata | Meta ve diğer sağlayıcıların uygulama review, business verification, kayıt şartları; confidential client backend masrafı olabilir |

**Yasaklı pazarlama vaadi:** “Hiç para vermeden bütün mağazalarda Verified, hiç izin penceresi olmadan Chrome yüklenmiş, her MCP tek tıkla ve her ağda kesintisiz canlı ekran”. Bunların tümü aynı anda garanti edilemez. **Doğru vaat:** “Sıfır aylık Fusion sunucu faturası hedefi; gerekli platform izinleri, provider kotaları ve resmî kayıt maliyetleri açıkça belirtilir.”

### Ücretli servise ne zaman geçilir?

- Merkezi bot/relay kullanımı ücretsiz kotayı zorlamaya başlarsa.
- App Store/Play Store/Chrome Web Store kullanıcı talebi ve yayıncı güveni açısından gerekli olursa.
- Kurumsal OAuth için sağlayıcı app review veya confidential backend gerektirirse.
- Her ağdan kesintisiz düşük gecikmeli video için TURN relay operasyonu gerekli olursa.
- Yeni harcama ancak ölçülen ürün kullanımı, kullanıcı talebi ve güvenlik/maliyet raporu sonrası onaylanır.

---

## 7. Güvenlik ve gizlilik kontrol listesi

- [ ] OS güvenlik izinleri atlatılmaz; güvenli ekran/UAC/OS Accessibility/Screen Recording kullanıcı kararıdır.
- [ ] CLI shell araçları yalnız çalışma dizini sınırıyla gerçek sandbox kabul edilmez. Onay, iş alanı izolasyonu ve mümkünse OS process sandbox birlikte.
- [ ] Git worktree izolasyonu, outside-root traversal/symlink takip kontrolleri.
- [ ] Tarayıcı prompt injection, MCP tool output injection ve araştırma içeriği talimat olarak kabul edilmez.
- [ ] Gizli değerlerin stdout, terminal transcript, Discord/Telegram, audit, screenshot içinde redaction.
- [ ] Üretim DB, e-posta, dış hesap, silme veya ödeme işlemi için per-tool izin ve müşteri onayı.
- [ ] Browser extension yalnız izinli origin ve tarayıcı tab kimliği; kapatma/yükleme/silme “read” değil.
- [ ] OAuth PKCE/state/issuer exact match, redirect allowlist, refresh rotation, local secret store.
- [ ] Telegram bot token ve pairing device id korumalı; DM allowlist, rate limit, E2EE olmadığını açıkla.
- [ ] Uzaktan API kullanıcı dışında internetten görünmez; telemetry varsayılan opt-in.
- [ ] Screenshot/video tutma süresi kısa, kullanıcı tarafından silinebilir, maskeleme seçeneği.
- [ ] Otomatik güncellemeler imzalı, rollback ve attack supply chain taraması.
- [ ] Privacy Policy, Terms, Security Policy, responsible disclosure ve uygulama kaldırma verisi ayrı dokümante.

---

## 8. Test paketleri — tamamlandı demek için

**A. İşlevsel temel**

- `fusion` CLI açılır, varsayılan model sağlar veya açık hata gösterir; dosya yazma, test, Git, recovery çalışır.
- Aynı görev için session ve checkpoint tutarlılığı; farklı projelerin izolasyonu.
- Yerel Nemotron ve hesabın gerçekten izin verdiği başka güçlü model, aynı tool contract ve acceptance durumlarını doğru raporlar.

**B. Project Audit/UI**

- İlgili dosya değiştiği anda önizleme ve test durumunun güncellenmesi; refresh gerekmiyor.
- Terminal açıkken alt mini live preview; sağ Project Audit'te geçmiş/kanıt; panel değişince gizli otomatik sekme sıçraması yok.
- Ekran paylaşımı durdurulduğunda OS capture oturumu kapanmış.
- `PASSED/FAILED/SKIPPED/ERROR` yanlış renk veya yanlış statüye dönüşmüyor.

**C. Masaüstü**

- macOS ilk kullanım izinleri Fusion kimliğiyle yönetilir; kullanıcı reddi sonrası fallback anlaşılır.
- Windows x64 kurulum ve capture/click/drag/keyboard ile aynı görev.
- Çoklu monitör+DPI+uyku/kilit+yanlış odak senaryoları.
- ScreenCaptureKit/GraphicsCapture performansı 15fps dengeli modda gerçek ölçümle doğrulanır.

**D. Browser / MCP / VS Code**

- Resmî Web Store'dan yükleme kullanıcı onayıyla çalışır, native host otomatik ve güvenli eşleşir.
- Site dışı tab'a tıklanamaz/kapandıramaz; formlar/Tab/Backspace gerçek sayfalarda test.
- CIMD, DCR ve statik client ID mock sunucularda; Meta kayıt kabulü sağlayıcıya göre gerçek test.
- VS Code oturumu CLI/desktop ile aynı `run_id` ve değişiklik kayıtlarını görür.

**E. Mobile / Telegram**

- İzinli Telegram hesabı görev verir, yetkisiz gönderici reddedilir; Kits scope korunur; tekrar eden mesaj ikinci kez işlem yaptırmaz.
- Telefon PWA offline/uyanma/yeniden bağlanma/oturum yenileme, onay ve audit.
- Remote desktop WebRTC başarısız olursa doğru fallback; relay yokluğu “canlı video” varmış gibi sunulmaz.

**F. Oyun benchmark**

- Barista oyunu gerçekten açılır, kullanıcı yönlendirmeleri çalışır, sipariş/para/upgrade/save döngüsü test edilir.
- Sprite ölçüleri/palet/animasyon/yerleşim testleri; gerçek ekran görüntüsü delili.
- Test başarısız ise döngü düzeltir; aynı hatayı sonsuza kadar tekrarlamaz.
- Bağımsız test setini agent değiştirip kendine kolay hale getiremez.

---

## 9. Codex uygulama protokolü: faz başına teslim formatı

Her faz için Codex şu raporu yazacak:

```markdown
# PHASE N — <başlık>

## Başlangıç kanıtı
- Repo commit: <SHA>
- Çalışma ağacı: <temiz/kirli; dokunulmayan dosyalar>
- Mevcut özellik: <var/kısmen/eksik>
- Dosyalar / semboller: <somut liste>

## Plan / değişiklikler
- Gereksinim ID'leri: ...
- Seçilen mimari ve neden alternatiften iyi: ...
- Değişen dosyalar: ...
- Migration / feature flag / rollback: ...

## Testler ve gerçek sonuçlar
- Unit / integration / UI / E2E / OS testleri: ...
- Kanıt, log, ekran, benchmark: ...
- Başarısız / atlanan testler: ...

## Güvenlik, performans ve maliyet
- İzinler, veri saklama, secret handling: ...
- CPU/RAM/gecikme/sağlayıcı kotası etkisi: ...
- Ücretsiz başlangıç ile uyum: ...

## Kalan riskler
- ...

## Faz çıkış kararı
- PASS / BLOCKED / PARTIAL
```

**İlk Codex görevi (kopyala-yapıştır):**

> `FUSION_MASTER_PLAN.md` dosyasını oku. Başlamadan önce yalnız `https://github.com/emirhhan/fusion-cli` çalışma ağacının mevcut durumunu denetle, `git rev-parse HEAD` ile commit hash'i belirle ve commit edilmemiş kullanıcı değişikliklerini koru. Her gereksinimi mevcut koda göre `var/kısmen var/eksik/hatalı/belirsiz` olarak işaretleyen kaynak dosyalı envanter ve faz bağımlılıkları çıkar. Hiçbir şeyi sıfırdan yeniden yazma ve henüz tasarım uygulamasına geçme. Özellikle önceki konuşmada doğrulanmamış kod bulgularını gerçek regresyon testleriyle ele al. Var olan yapı ile çelişen veya provider/policy sebebiyle yapılamayan gereksinimleri açıkça raporla. Önce Faz 0 raporunu sun; onaydan sonra küçük, testli, geri alınabilir Faz 1 değişiklikleri yap.

---

## 10. İleride açık kalmaması gereken konuşma başlıkları — kapsam kontrolü

Bu kontrol listesi geçmiş konuşmada özel olarak ifade edilen bütün hedeflerin ana planda yer aldığını denetlemek içindir:

- [ ] Claude Code ve Codex benzeri doğal terminalden kod/game/web uygulama geliştirme.
- [ ] 24–72 saat iş yapma; sorunları çözerek, kesintiden toparlanarak, yanlış planı sürdürmeden tamamlayabilme.
- [ ] Checkpoint, ChangeSet/journal, resumed plan, `uncovered`, TurnBudget, recovery, no-progress, context compaction, verification, lessons, tool fallback.
- [ ] Daha az güçlü Nemotron ile güçlü modeller arasındaki farkı görev/skill/test mimarisiyle azaltma; eşitlik vaadi yok.
- [ ] Kullanıcının ChatGPT aboneliğiyle API anahtarı olmaksızın, **resmen yetkili** model(ler)e uygun entegrasyon; Sol gibi model isimlerini hesaba göre doğrulama.
- [ ] Multi-model fusion/sentez, model performans ölçümü ve fallback.
- [ ] Web/Godot araştırmasında doğru güncel sürüm/kaynak/kanıt; kod tabanı arama tamamlığı.
- [ ] Pixel-art barista oyunu, görsel/asset stil kontrolü, gerçekten oynanabilir teslimat, Codex'ten hedef %20–30 uzun ve daha iyi kabul başarısı.
- [ ] Masaüstü native GUI kullanımı, browser, MCP, ses/voice, Kits, codebase/Git/test, live preview.
- [ ] Sağ Project Audit varsayılan yeni görev sekmesi; Terminal altında mini canlı ekran; ilerleme ile doğrulanmış başarı ayrımı.
- [ ] macOS ScreenCaptureKit canlı video, model kare örnekleme, Python helper izin gürültüsünü azaltma, bildirimler.
- [ ] macOS zorunlu izinleri gizlice kaldırmama; ilk açılış onboarding yalnız özellik kullanıldığında.
- [ ] Windows gerçek eşdeğerlik: Graphics Capture, UI Automation/SendInput, DPI, PTY, voice, NSIS, smoke, update.
- [ ] Chrome için manuel extension yükleme deneyimini kaldırma hedefi: mağaza üzerinden kullanıcı onaylı bir tık, native host auto-setup; sessiz zorla yükleme yok.
- [ ] Tarayıcı izinleri, native pairing, sentetik klavye/click, sekme kapatma, file upload, screenshot sınırları.
- [ ] MCP OAuth CIMD/DCR/registered client ID, Meta/provider app review, secure vault, client secret sınırı.
- [ ] VS Code Marketplace eklentisi ve aynı agent görevi.
- [ ] iOS/Android ücretsiz PWA başlangıcı; bilgisayar tarafı agent, opsiyonel WebRTC.
- [ ] Telegram özel kullanıcı botu, şifreli ağ bağlantısı, güvenli eşleştirme, `/kits`, remote desktop task, onay, revoke.
- [ ] Merkezi/yerel Task Service, kalıcı task events, kit run ve per-device izinler.
- [ ] 0 aylık sunucu/hosting hedefi, platform ücretleri ve model kotaları için dürüst maliyet planı.
- [ ] Profesyonel resmî yayın: imzalama, noter onayı, Web Store/Marketplace, domain, security docs.
- [ ] Beğenilen F logo + orbit animasyon, sevilen Fusion wordmark; fazla gradyan ve AI-slop karakterlerin reddi.
- [ ] Mevcut Fusion UI/TUI/Talk/Kits ekranlarını koruyup kaynak kodla doğrulayarak modernleştirme; son light theme mockup'ları yalnız referans.
- [ ] Şirket çapında geçişten önce gerçek benchmark ve güvenlik; kullanıcı/firma geleceği riske atılmadan kademeli yaygınlaştırma.

---

## 11. Önemli kaynak bağlantıları

- Hedef Fusion: https://github.com/emirhhan/fusion-cli
- Hedef Fusion README: https://github.com/emirhhan/fusion-cli/blob/main/README.md
- Hedef Fusion backlog: https://github.com/emirhhan/fusion-cli/blob/main/docs/BACKLOG.md
- Hedef Fusion CLAUDE talimatları: https://github.com/emirhhan/fusion-cli/blob/main/CLAUDE.md
- Hedef Fusion RULES: https://github.com/emirhhan/fusion-cli/blob/main/RULES.md
- OpenAI Codex açık kaynak: https://github.com/openai/codex
- Claude Code kamuya açık repo (tüm çekirdek kaynak kodu anlamına gelmez): https://github.com/anthropics/claude-code
- MCP Authorization: https://modelcontextprotocol.io/specification/
- Apple ScreenCaptureKit: https://developer.apple.com/documentation/screencapturekit
- Microsoft Windows Graphics Capture: https://learn.microsoft.com/windows/uwp/audio-video-camera/screen-capture
- Chrome Web Store yayınlama belgeleri: https://developer.chrome.com/docs/webstore/publish
- VS Code extension docs: https://code.visualstudio.com/api
- Telegram Bot API: https://core.telegram.org/bots/api
- GitHub Pages: https://pages.github.com/

**Son karar:** Bu dosya direkt “bütün sistemi bugün değiştir” emri değildir; **eksik commit'leri ve mevcut uygulamanın gerçek davranışını koruyarak yapılacak, sınanabilir, fazlanmış tek kaynak planıdır.** Önce kod doğrulaması; sonra küçük ve geri alınabilir geliştirmeler; en son marka, dağıtım ve büyüme.
