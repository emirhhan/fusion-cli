# Zayıf modeli güçlü ajana çeviren harness: araştırma ve yol haritası

Tarih: 6 Eylül 2026. Amaç: Fusion'ın, ücretsiz/web sağlayıcılarla çalışırken Codex ve Claude Code sınıfı bir çalışma deneyimi vermesi. Soru "model yeterince zeki mi" değil; **"harness, elindeki modelden ne kadarını işe çevirebiliyor"**.

## Araştırmanın ana bulgusu

Literatür bu soruya net cevap veriyor: **scaffold farkı, model farkını kapatabiliyor — ve kazanç en çok zayıf modelde ortaya çıkıyor.**

- Confucius Code Agent, aynı backbone altında OpenHands'i geçiyor ve daha güçlü bir modelle çalışan mini-SWE-agent varyantını da aşıyor; kazanç "runtime LLM'in agentic yeteneği zayıfken en büyük" olarak raporlanıyor ([2512.10398](https://arxiv.org/pdf/2512.10398)).
- Agentless, ajan bile kullanmadan, üç aşamalı sabit bir boru hattıyla (yerelleştir → onar → doğrula) SWE-bench Lite'ta açık kaynak birinciliği aldı ve maliyeti düşürdü ([2407.01489](https://arxiv.org/html/2407.01489)).
- Ters yönde uyarı: mini-SWE-agent (~100 satır, yalnız bash) Opus 4.5 ile %76,8, OpenHands+CodeAct %77,6. Yani **güçlü modelde ağır scaffold kazandırmıyor, hatta kısıtlıyor** ([mini-swe-agent](https://github.com/swe-agent/mini-swe-agent), [2606.20683](https://arxiv.org/pdf/2606.20683)).

Bu ikisi çelişmiyor, tasarım kuralını veriyor:

> **Zayıf modele iskele kur, ama iskele modelin yolunu kapatmasın.**

Dün canlı koşuda tam bunu yaşadık: adım kapsamı `read_file`'ı kapattı ve görev imkânsızlaştı. Bu, "kısıt fazlası" tarafının somut örneği.

## Bulgular ve Fusion'daki karşılığı

### 1. Agent-Computer Interface (ACI) — arayüz, modelin yeteneğini belirler

SWE-agent'ın ana tezi: model sabitken **eylemleri, dokümantasyonu ve geri bildirimi** modelin sınırlarına göre tasarlamak sonucu belirgin biçimde değiştiriyor. Somut kararlar: düzenleme sonrası otomatik linter (sözdizimi hatası diske ulaşmasın), özel dosya görüntüleyici (turda 100 satır en iyi sonucu veriyor), arama sonuçlarını kısa listeleme (fazla bağlam modeli şaşırtıyor) ([ACI](https://swe-agent.com/latest/background/aci/), [2405.15793](https://arxiv.org/abs/2405.15793)).

Fusion'da: yapı denetimi (`structured_files`) bu felsefeye uygun; `read_file` 800 satır sınırı var. Eksik: dile göre lint/parse kapısı yalnız birkaç biçimde, arama çıktısı ACI ölçütlerine göre ayarlanmamış.

### 2. Düzenleme biçimi (edit format) — zayıf modelde en ucuz kazanç

Aider'ın ölçümü: aynı model, farklı düzenleme biçimiyle %20 → %61. Search/replace blokları satır numarası/uzunluk tutturmayı gerektirmediği için zayıf modelde daha sağlam; udiff'te tek karakterlik işaretleri kodla karıştıran küçük modeller için işaretleri açık etiketlere çevirmek (ADD/DEL/CON) belirgin fark yaratıyor ([aider unified diffs](https://aider.chat/docs/unified-diffs.html), [edit leaderboard](https://aider.chat/docs/leaderboards/edit.html)).

Fusion'da: `write_file` / `replace_range` / `edit_file` var, **modele göre biçim seçimi yok**. Aider tek başına 13 varyant taşıyor ([2604.03515](https://arxiv.org/html/2604.03515v1)).

### 3. Araç şeması modele uyarlanmalı, model şemaya değil

Kısıtlı çözümleme (constrained decoding) küçük modellerde araç seçimini %49,5 → %78,1 çıkarıyor; ancak katı şema küçük modelde "kısıt vergisi" de doğuruyor ([2606.25605](https://arxiv.org/pdf/2606.25605), [2510.07248](https://arxiv.org/pdf/2510.07248)).

Fusion'da: web sağlayıcı yolunda araç çağrısı **metinden ayrıştırılıyor** — burada şema sadeleştirme ve tolere edici ayrıştırma doğrudan başarı oranıdır.

### 4. Bağlam mühendisliği — compaction ve artifact

Context rot ölçülmüş bir olgu: bağlam uzadıkça, ilgili bilgi hâlâ oradayken bile doğruluk %13,9–85 düşüyor. Çözüm compaction (özetleyerek küçültme), artifact'a taşıma ve alt-ajan izolasyonu. OpenHands condenser'ı olayları özet olayla değiştiriyor ve oturumun bağlam penceresini sınırsız aşmasını sağlıyor ([2606.29718](https://arxiv.org/pdf/2606.29718), [OpenHands condenser](https://docs.openhands.dev/sdk/guides/context-condenser), [Anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)).

Taksonomi çalışması yedi ayrı sıkıştırma stratejisi sayıyor ve "compaction mimarisi zorunludur, opsiyonel değil" diyor ([2604.03515](https://arxiv.org/html/2604.03515v1)).

Fusion'da: checkpoint var, **condenser yok**; büyük araç çıktısı 20.000 karakterde kırpılıyor ama artifact'a taşınıp handle verilmiyor.

### 5. Yerelleştirme — repo haritası

Aider tree-sitter ile sembol grafiği çıkarıp PageRank benzeri sıralamayla bütçeye sığan haritayı veriyor; büyük depoda ucuz kalmasının ana sebebi bu ([repomap](https://aider.chat/2023/10/22/repomap.html)). Taksonomi de yapı farkında (AST) erişimin salt anahtar kelime aramasından üstün olduğunu söylüyor.

Fusion'da: grep/glob var, **sembol grafiği ve sıralama yok**.

### 6. Üretme–test–onarma döngüsü ve runtime tanı

- Agentless: onarım aşamasında birden çok aday yama, ardından **LLM'in ürettiği reprodüksiyon testi + regresyon testleri + çoğunluk oyu** ile seçim.
- ReProAgent: reprodüksiyon testi üretimini iyileştirince SWE-agent'ın çözdüğü konu 143 → 153.
- SWE-Doctor: testleri **debugger altında** çalıştırıp "şüpheli konum, çalışma zamanı belirtisi, hata yayılım yolu, gözlenen değerler" içeren yapılandırılmış tanı üretiyor ve yamayı bununla yönlendiriyor; SWE-bench Verified %75,7 ([2607.00990](https://arxiv.org/html/2607.00990), [2607.09123](https://arxiv.org/html/2607.09123)).

Fusion'da: kanıt sistemi (bu hafta eklendi) bu döngünün altyapısı; **testi önce üretme ve runtime tanı yok**. Dün Godot koşusunda `SCRIPT ERROR: Parse Error` çıktısı elimizdeydi ve kimse onu "sahnedeki düğüm tipi ile script API'si uyuşmuyor" tanısına çevirmedi.

### 7. Test-time scaling — paralel deneme ve seçim

K bağımsız rollout üretip skorlayarak yeniden sıralamak açık kaynakta standart hale geldi. Yürütme tabanlı doğrulayıcı ajanlar Best@K'de +%10–15; rubrik tabanlı süreç ödül modelleri kötü dalları **rollout sırasında** budayarak sonradan sıralamadan daha iyi sonuç veriyor ([2602.04254](https://arxiv.org/html/2602.04254v1), [2604.14820](https://arxiv.org/html/2604.14820v1), [2512.21919](https://arxiv.org/pdf/2512.21919)).

Fusion'da: hakem/çok model motoru zaten var (`fusion run`), ama **agent turunda paralel deneme + kanıtla seçim yok**. Ücretsiz sağlayıcılarla çalışan bir üründe bu, en doğal avantaj.

### 8. Ensemble ve yönlendirme

Çoklu ucuz model + oylama/münazara, tek güçlü modele karşı ölçülebilir kazanç veriyor (kodlamada çoğunluk oyu ile seçim kesinliği %66,7 → %85,7 raporlanmış). Pratikte yaygın desen: trafiğin %60–80'i ucuz/yerel modelde, en zor %20 güçlü modele yükseltiliyor ([2504.17087](https://arxiv.org/pdf/2504.17087), [2510.12697](https://arxiv.org/abs/2510.12697)).

Fusion'da: `doctor` çıktısına göre OpenRouter, NVIDIA NIM ve Gemini Web birlikte yapılandırılmış; **zorluk temelli yükseltme yok**.

### 9. Kendi kendini geliştiren araçlar (mega fikir)

Live-SWE-agent: yalnız bash ile başlıyor, koşu sırasında kendine Python araçları yazıyor; adım sonlarında "araç üretmek/iyileştirmek işi hızlandırır mı" diye yansıma yapıyor. SWE-bench Verified %77,4, SWE-Bench Pro %45,8 — çevrimdışı eğitim maliyeti sıfır ([2511.13646](https://arxiv.org/html/2511.13646)).

Fusion'da yok. Fusion'ın MCP + shell + dosya araçları bu primitifi kurmak için yeterli.

### 10. Harness blueprint'i — üretim disiplini

2026 blueprint'i somut varsayılanlar veriyor: araç çıktısı yapılandırılmış zarf (status + özet + artifact referansı), dört kademeli bağlam tahliyesi, checkpoint'in yan etkiden önce ve sonra alınması, tekrar oynatmanın deterministik olması, iptalin birinci sınıf primitif olması, tur başına 50–100 adım, adım başına 2–3 deneme, pencerenin %20–25'inin rezerve edilmesi ([blueprint](https://gist.github.com/amazingvince/52158d00fb8b3ba1b8476bc62bb562e3)).

Fusion bunların bir kısmını zaten yapıyor (checkpoint, bütçe zarfları, onay katmanları). Eksikler: artifact deposu, tahliye kademeleri, araç çıktısı zarfı.

## Yol haritası

Sıra, "ölçülen kayıp / uygulama maliyeti" oranına göre. Her madde aynı sabit sete karşı ölçülür; ölçüm yoksa madde bitmiş sayılmaz.

### Dalga 1 — ucuz ve doğrudan (her biri 1-3 gün)

| # | İş | Neden | Ölçülecek |
|---|---|---|---|
| 1 | **Modele göre düzenleme biçimi**: search/replace, tam dosya ve etiketli udiff varyantları; sağlayıcıya göre seçim | Aider'da aynı modelde %20 → %61 | başarısız/bloke araç çağrısı oranı, düzenleme başarısı |
| 2 | **Araç şeması sadeleştirme + tolere edici ayrıştırma** (web yolunda metinden çağrı) | küçük modelde araç seçimi %49,5 → %78,1 | araç çağrısı ayrıştırma başarısı |
| 3 | **Araç çıktısı zarfı + artifact deposu**: büyük çıktı dosyaya, modele özet + handle | context rot; blueprint Tier 1 | tur başına token, uzun görevde başarı |
| 4 | **Edit sonrası dil kapısı**: yazılan her dosya için sözdizimi/lint denetimi | SWE-agent ACI: bozuk kod diske ulaşmasın | bozuk dosya sayısı, kurtarma turu sayısı |
| 5 | **Arama/görüntüleme ACI ayarı**: 100 satırlık pencere, kısa eşleşme listesi | ACI ölçümleri | adım sayısı, gereksiz okuma |

### Dalga 2 — döngü değişikliği (her biri 1-2 hafta)

| # | İş | Neden | Ölçülecek |
|---|---|---|---|
| 6 | **Reprodüksiyon testi önce**: hatayı gösteren testi üret, kırmızıyı gör, sonra düzelt | ReProAgent ile 143 → 153 | ilk denemede başarı, yanlış başarı |
| 7 | **Runtime tanı kaydı**: testi/komutu izleyerek yapılandırılmış tanı üret (konum, belirti, yayılım, değerler) | SWE-Doctor %75,7 | oku-anla-düzelt sınıfı görevlerde başarı |
| 8 | **Paralel deneme + kanıtla seçim**: N aday, reprodüksiyon + regresyon + çoğunluk oyu | Agentless seçim aşaması; TTS +%10–15 | Best@K, tek koşu varyansı |
| 9 | **Bağlam condenser'ı**: eşikte özetle, olay kaydını koru | context rot %13,9–85; OpenHands | uzun görevde tamamlanma |
| 10 | **Zorluk temelli yönlendirme**: ucuz model varsayılan, takılınca yükselt | %60–80 ucuz / %20 güçlü deseni | maliyet başına başarı |

### Dalga 3 — mimari sıçrama

| # | İş | Neden |
|---|---|---|
| 11 | **Repo haritası**: tree-sitter sembol grafiği + PageRank sıralaması, bütçeli harita | büyük depoda yerelleştirme; Aider'ın ucuzluk sırrı |
| 12 | **Döngü primitifleri kütüphanesi**: ReAct, üret-test-onar, planla-yürüt, çok denemeli tekrar, ağaç arama — birleştirilebilir parçalar | taksonominin ana bulgusu: mimariler bu beşin bileşimi |
| 13 | **Süreç ödülü / rubrik doğrulayıcı**: kötü dalı rollout sırasında buda | SWE-TRACE: sonradan sıralamadan iyi |
| 14 | **Koşu içi araç üretimi (self-evolution)**: ajan kendine görev-özel araç yazsın | Live-SWE-agent %77,4, eğitim maliyeti sıfır |
| 15 | **Alan adaptörleri**: Godot/web/veri için "neyin kanıt sayıldığını" tanımlayan eklenti katmanı | ortak motor + alana özel kanıt |

## Uygulama kuralları

1. **Kısıt, yolu kapatmaz.** Dün ölçtük: kapsam zorlaması `read_file`'ı kapatınca görev imkânsızlaştı. Her yeni kapı için "model bu kapıya takılırsa hangi yol açık kalıyor?" sorusu cevaplanmadan birleştirilmez.
2. **Ağır scaffold güçlü modelde ceza olabilir.** mini-SWE-agent kanıtı: yapı, modelin önüne geçmemeli. Yeni katmanlar kapatılabilir olmalı.
3. **Her değişiklik aynı sete karşı ölçülür.** Tek koşu gürültülüdür; `--repeat 3-5` ve önce/sonra karşılaştırması.
4. **Elle düzeltilen çıktı başarı sayılmaz.** İnsan müdahalesi sayısı birinci sınıf metriktir.

## Kaynaklar

- [Confucius Code Agent](https://arxiv.org/pdf/2512.10398) · [Inside the Scaffold (taksonomi)](https://arxiv.org/html/2604.03515v1) · [Harness design survey](https://arxiv.org/pdf/2606.20683)
- [SWE-agent ACI](https://swe-agent.com/latest/background/aci/) · [SWE-agent makalesi](https://arxiv.org/abs/2405.15793) · [mini-swe-agent](https://github.com/swe-agent/mini-swe-agent)
- [Agentless](https://arxiv.org/html/2407.01489) · [ReProAgent](https://arxiv.org/html/2607.09123) · [SWE-Doctor](https://arxiv.org/html/2607.00990)
- [Agentic Verifier](https://arxiv.org/html/2602.04254v1) · [SWE-TRACE](https://arxiv.org/html/2604.14820v1) · [SWE-RM](https://arxiv.org/pdf/2512.21919)
- [Aider unified diffs](https://aider.chat/docs/unified-diffs.html) · [Aider repo map](https://aider.chat/2023/10/22/repomap.html) · [Aider edit leaderboard](https://aider.chat/docs/leaderboards/edit.html)
- [Context rot](https://arxiv.org/pdf/2606.29718) · [OpenHands condenser](https://docs.openhands.dev/sdk/guides/context-condenser) · [Anthropic context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Constraint tax](https://arxiv.org/pdf/2606.25605) · [Adapt tool schemas](https://arxiv.org/pdf/2510.07248) · [Live-SWE-agent](https://arxiv.org/html/2511.13646)
- [Modern Agent Harness Blueprint 2026](https://gist.github.com/amazingvince/52158d00fb8b3ba1b8476bc62bb562e3) · [awesome-harness-engineering](https://github.com/ai-boost/awesome-harness-engineering)

## Nasıl yapılır — madde madde uygulama notları

### Dalga 1

1. **Modele göre düzenleme biçimi** — `core/model_capability.py` içindeki `ToolSupport` yanına bir `EditFormat` alanı eklenir ve `tools/files.py`'daki `write_file` / `replace_range` / `edit_file` üçlüsü tek bir "düzenleme adaptörü" arkasına alınır; sağlayıcı zayıfsa aider'ın ölçtüğü gibi search/replace blokları (`edit_file`'ın `old`/`new` çifti) varsayılan olur, güçlü modelde `replace_range` satır aralığı açılır ve biçim seçimi `core/tool_emulation.py`'nin ürettiği talimata da yansıtılır.
2. **Araç şeması sadeleştirme ve tolere edici ayrıştırma** — `core/tool_emulation.py`'de şemalar modele göre budanır (derin `properties` ağacı yerine düz alanlar, örnek çağrı sayısı artırılır) ve `parse` tarafına `tools/files.py:_tolerate_line_numbers` benzeri toleranslar eklenir: eksik `$ref`, tırnaksız anahtar ve fazladan açıklama satırı hata değil onarılabilir sapma sayılır, her onarım telemetriye "ayrıştırma kurtarması" olarak yazılır.
3. **Araç çıktısı zarfı ve artifact deposu** — `core/tools.py:ToolResult`'a `artifact_path` alanı eklenir; `MAX_OUTPUT_CHARS` sınırını aşan çıktı `.fusion/artifacts/<oturum>/<adım>-<araç>.txt` dosyasına yazılıp modele "özet + satır sayısı + dosya yolu" döner, model gerektiğinde `read_file` ile o dosyayı okur (blueprint'in Tier 1 tahliyesi).
4. **Edit sonrası dil kapısı** — `core/structured_files.py:validate_structured` mevcut biçim tablosuna dil eklenir: `.py` için `compile()`, `.gd` için `godot --headless --check-only`, `.ts/.js` için `node --check`/`tsc --noEmit`, `.json/.yaml` için ayrıştırıcı; SWE-agent'ın linter dersi gereği bozuk içerik `tools/files.py:208`'deki gibi diske hiç ulaşmaz ve hata metni modele döner.
5. **Arama ve görüntüleme ACI ayarı** — `core/constants.py:MAX_READ_LINES` 800'den SWE-agent'ın ölçtüğü 100 satırlık pencereye indirilir (mevcut `_devam_notu` zaten devamı öğretiyor) ve `tools/search.py` eşleşmeleri dosya başına tek satır olarak listeler; amaç turda gösterilen bağlamı azaltıp adım sayısını düşürmektir.

### Dalga 2

6. **Önce reprodüksiyon testi** — `engines/agent/plan_parser.py`'nin ürettiği plan şemasına "hatayı gösteren test" adımı zorunlu kılınır ve `core/execution_plan.py:VerificationCheck` üzerinden bu testin ÖNCE kırmızı, düzeltmeden sonra yeşil olduğu iki ayrı kanıt olarak kaydedilir; Agentless'ın seçim aşamasındaki gibi test yoksa yama "doğrulanmamış" kalır.
7. **Runtime tanı kaydı** — `engines/agent/verification.py:CommandVerifier` çıktısı ham metin yerine yapılandırılmış tanıya çevrilir (`SCRIPT ERROR ... at: res://player.gd:12` → dosya, satır, belirti, ilgili sembol) ve bu kayıt `core/evidence.py:CriterionEvidence` içine konup `recovery.py:choose_recovery`'ye girdi olur; SWE-Doctor'ın yaptığı gibi kurtarma turu "hata metnini oku" değil "tanıyı düzelt" görevi alır.
8. **Paralel deneme ve kanıtla seçim** — `engines/agent/plan_runner.py:_PlanRun.run_step` tek alt tur yerine N alt turu ayrı çalışma kopyalarında (git worktree ya da `changeset` snapshot) koşturur, her adayı `step_verification.verify_step` ile puanlar ve reprodüksiyon testi + regresyon + çoğunluk oyuyla birini seçer; bütçe `engines/workflow/model.py:BudgetEnvelope`'a yeni bir `ATTEMPTS` zarfı olarak eklenir.
9. **Bağlam condenser'ı** — `engines/agent/loop.py`'nin mesaj listesine OpenHands'in condenser'ı gibi bir eşik konur: pencerenin %70'ine gelince eski araç sonuçları özet mesajla değiştirilir, orijinali artifact'ta kalır ve `core/checkpoint.py`'ye "condensation" olayı olarak yazılır ki devam eden oturum neyin özetlendiğini bilsin.
10. **Zorluk temelli yönlendirme** — `core/routing_strategy.py`'ye "escalate" stratejisi eklenir: adım ilk denemede ucuz modelle koşar, `recovery.py:classify_failure` aynı adımda ikinci kez düşerse yedek zincirin bir üst modeli devreye girer ve bu karar `core/health.py` kayıtlarıyla beslenir; hedef maliyet başına başarıyı ölçmek, model sabitlemek değil.

### Dalga 3

11. **Repo haritası** — yeni `core/repo_map.py` tree-sitter ile sembol tanımlarını çıkarır, dosyalar arası referans grafiğine PageRank uygular ve bütçeye sığan haritayı `engines/agent/loop.py`'nin sistem bağlamına ekler; aider'ın `--map-tokens` yaklaşımı gibi harita boyutu yapılandırılabilir olur ve grep yerine ilk yerelleştirme adımı bu haritadan başlar.
12. **Döngü primitifleri kütüphanesi** — `engines/agent/plan_runner.py` içine gömülü akış, `ReAct`, `üret-test-onar`, `planla-yürüt`, `çok-denemeli-tekrar` ve `ağaç-arama` primitiflerine ayrılıp `engines/agent/loops/` altına taşınır; görev türü (`classify.py`) hangi primitif bileşimini kullanacağını seçer, böylece basit görev mini-swe-agent kadar sade bir yolda kalır.
13. **Süreç ödülü / rubrik doğrulayıcı** — `step_verification.py`'ye adım bitmeden çalışan hafif bir rubrik puanlayıcı eklenir (kanıt var mı, ilerleme oldu mu, aynı hata tekrar mı ediyor) ve eşiğin altındaki dal `plan_runner` tarafından erken kapatılır; SWE-TRACE'in bulgusu, kötü dalı sonradan elemek yerine koşarken budamanın daha etkili olduğudur.
14. **Koşu içi araç üretimi** — Live-SWE-agent'ın deseniyle `engine_tools.py`'ye `make_tool` primitifi eklenir: agent `.fusion/tools/<ad>.py` altına küçük bir betik yazar, `ToolRegistry` onu tur içinde kayıt eder ve üretilen araç `ToolFamily.EXTERNAL` olarak onay/kapsam kurallarına tabi kalır; adım sonlarında "bu işi hızlandıracak bir araç yazmalı mıyım" yansıması sorulur.
15. **Alan adaptörleri** — `engines/agent/verify_discovery.py`'deki keşif tablosu, alan başına "neyin kanıt sayıldığını" tanımlayan bir adaptör arayüzüne dönüştürülür (Godot: sahne açılır + N kare hatasız + düğüm/script tipi tutarlı, web: sayfa yüklenir + kritik akış tıklanır, veri: şema doğrular); motor değişmez, yalnız adaptör alanın kanıt sözleşmesini verir.
