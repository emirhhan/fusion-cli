# Parite iş kolları — detaylı madde tanımları

Hedef: Fusion'ın ücretsiz/web sağlayıcılarla Codex ve Claude Code sınıfı bir çalışma deneyimi vermesi. Kaynak araştırma: [harness araştırması](../reports/2026-09-06-harness-arastirmasi.md). Bu belge **madde tanımlarıdır**; faz planı (sıra, onay, commit disiplini) bundan sonra yazılır.

Her madde şu alanları taşır: **Ne · Kanıt · Dokunulan yer · Nasıl · Kabul ölçütü · Ölçüm · Risk · Boyut.**

Boyut: **S** = 1-3 gün · **M** = 1-2 hafta · **L** = 2-4 hafta.

Bugünkü taban ölçüm: starter seti **%87,5 (21/24)**, ortalama 9,0 model çağrısı, 45,5 sn; Godot 3 koşuda 0 tam otonom teslim.

---

## A. Araç ve arayüz katmanı (Dalga 1)

### 1. Modele göre düzenleme biçimi — S

**Ne.** Tek bir düzenleme sözleşmesi yerine, sağlayıcının gücüne göre seçilen düzenleme biçimleri.

**Kanıt.** Aider'da aynı model, farklı biçimle %20 → %61. Search/replace blokları satır numarası ve uzunluk tutturmayı gerektirmediği için zayıf modelde daha sağlam.

**Dokunulan yer.** `tools/files.py` (`write_file`, `replace_range`, `edit_file`, `multi_edit`, `parse_edits`), `core/model_capability.py`, `core/tool_emulation.py:render_tool_instructions`.

**Nasıl.**
- `ModelCapability`'ye `edit_format` alanı eklenir: `search_replace` | `line_range` | `whole_file`.
- Üç araç tek bir "düzenleme adaptörü" arkasına alınır; modele yalnız seçilen biçimin aracı ve örneği sunulur (üçü birden sunulunca model karıştırıyor — bu ölçülmeli).
- Zayıf modelde varsayılan `search_replace`; eşleşme bulunamazsa mevcut `_neden_eslesmedi` metni korunur ve `_tolerate_line_numbers` benzeri tolerans genişletilir.
- Biçim seçimi telemetriye yazılır ki başarı oranı biçime göre ayrıştırılabilsin.

**Kabul ölçütü.** Aynı sette düzenleme kaynaklı başarısızlık (`failed` sonuçlu dosya aracı çağrısı) en az yarıya iner; toplam başarı gerilemez.

**Ölçüm.** starter seti + yeni "çok dosyalı refactor" seti, `--repeat 3`. Metrik: araç çağrısı başarı oranı, düzenleme başına deneme sayısı.

**Risk.** Biçim başına ayrı kod yolu bakımı artırır; adaptör tek noktada tutulmazsa üç kopya doğar.

---

### 2. Araç şeması sadeleştirme ve tolere edici ayrıştırma — S

**Ne.** Web sağlayıcı yolunda metinden araç çağrısı üretimini ve okunmasını zayıf modele göre uyarlamak.

**Kanıt.** Küçük modellerde kısıtlı çözümleme araç seçimini %49,5 → %78,1 çıkarıyor; katı şema ise "kısıt vergisi" doğuruyor. Fusion'da native function-calling yok, sözleşme metin.

**Dokunulan yer.** `core/tool_emulation.py` (blok biçimi, `render_tool_example`, `_instruction_schema`, ayrıştırıcı), `engines/agent/loop.py` şema sunumu.

**Nasıl.**
- Şema modele göre budanır: iç içe `properties` düzleştirilir, opsiyonel alanlar talimattan çıkarılır, her araç için bir tam örnek çağrı verilir.
- Ayrıştırıcıya onarılabilir sapmalar tanıtılır: eksik `$ref`, tırnaksız anahtar, blok öncesi açıklama metni, kod bloğu içine alınmış çağrı.
- Her onarım "ayrıştırma kurtarması" olarak sayaçlanır; sessiz düzeltme yapılmaz.
- Zayıf modelde aynı anda sunulan araç sayısı sınırlanır (görev türüne göre 6-10), gerisi `find_skill` gibi keşif üzerinden açılır.

**Kabul ölçütü.** Boş yanıt ve ayrıştırılamayan blok oranı ölçülebilir biçimde düşer; tur başına harcanan model çağrısı azalır.

**Ölçüm.** starter + Godot seti; metrik: ayrıştırma hatası sayısı, boş yanıt sayısı, tur başına çağrı.

**Risk.** Fazla tolerans, modelin yanlış biçimi öğrenmesine yol açar; tolerans daima uyarı ile birlikte.

---

### 3. Araç çıktısı zarfı ve artifact deposu — S

**Ne.** Büyük araç çıktısının modele değil diske gitmesi; modele özet + referans dönmesi.

**Kanıt.** Context rot: bağlam uzadıkça doğruluk %13,9-85 düşüyor. Blueprint'in Tier 1 kuralı: büyük çıktı hemen artifact'a, modele handle.

**Dokunulan yer.** `core/tools.py:ToolResult`, `core/constants.py:MAX_OUTPUT_CHARS`, `tools/files.py`, `tools/search.py`, `mcp_bridge/content.py`, `engines/agent/loop.py`.

**Nasıl.**
- `ToolResult`'a `artifact_path` ve `truncated_lines` eklenir.
- Eşiği aşan çıktı `.fusion/artifacts/<oturum>/<adım>-<araç>-<sıra>.txt` dosyasına yazılır; modele "ilk N satır + toplam satır + yol" döner.
- Kanıt zincirine bağlanır: `CriterionEvidence.output` yerine artifact yolu tutulur, checkpoint maskeleme kuralı (`checkpoint_evidence.py`) korunur.
- Artifact'lar oturum sonunda temizlenmez; `resume` sırasında okunabilir kalır.

**Kabul ölçütü.** 30+ adımlık bir görevde toplam bağlam büyümesi doğrusal olmaktan çıkar; hiçbir kanıt kaybolmaz.

**Ölçüm.** Uzun görev seti (yeni, madde 17); metrik: tur başına token, tamamlanma oranı.

**Risk.** Modelin artifact'ı hiç okumaması. Özet metninde "gerekirse şu dosyayı oku" yönergesi ve ölçüm şart.

---

### 4. Edit sonrası dil kapısı — S

**Ne.** Yazılan her dosyanın diline göre sözdizimi/parse denetimi; bozuk içerik diske ulaşmaz.

**Kanıt.** SWE-agent ACI: düzenleme sonrası linter, sözdizimi hatalarını üretim anında engelliyor. Fusion'da bu yalnız birkaç yapılandırılmış biçimde var.

**Dokunulan yer.** `core/structured_files.py` (`validate_structured`, `_DENETLEYICILER`), `tools/files.py:_yapi_engeli`.

**Nasıl.**
- Denetleyici tablosu genişletilir: `.py` → `compile()`, `.json/.yaml/.toml` → ayrıştırıcı (kısmen var), `.gd` → `godot --headless --check-only`, `.js/.ts` → `node --check` / `tsc --noEmit`, `.rs` → `cargo check` (yalnız hızlıysa).
- Dış araç gerektiren denetimler yalnız araç kuruluysa çalışır; yoksa denetim atlanır (mevcut "araç yoksa engelleme" kuralı).
- Hata metni modele aynen döner ve "kaçıncı satır" bilgisi korunur.

**Kabul ölçütü.** Bozuk sözdizimiyle diske yazılan dosya sayısı sıfır; kurtarma turu sayısı düşer.

**Ölçüm.** Godot ve çok dosyalı setler; metrik: bozuk dosya sayısı, adım başına kurtarma.

**Risk.** Yavaş denetim turu uzatır; her denetim için süre bütçesi ve zaman aşımı gerekir.

---

### 5. Arama ve görüntüleme ACI ayarı — S

**Ne.** Modelin bir turda gördüğü kod miktarını ölçülmüş değerlere çekmek.

**Kanıt.** SWE-agent: turda 100 satır göstermek en iyi sonucu veriyor; arama sonuçlarında dosya başına tek satır, fazla bağlamdan daha iyi.

**Dokunulan yer.** `core/constants.py` (`MAX_READ_LINES`, `MAX_SEARCH_HITS`, `MAX_MATCH_LINE_CHARS`), `tools/files.py:read_file` + `_devam_notu`, `tools/search.py`.

**Nasıl.**
- `MAX_READ_LINES` 800 → 100-200 aralığında A/B ile ölçülür; devam notu zaten mevcut, sözleşme korunur.
- Arama çıktısı dosya başına tek satıra indirilir, eşleşme sayısı özet olarak verilir.
- Değerler sabit tabloya değil yapılandırmaya bağlanır ki ölçümle değiştirilebilsin.

**Kabul ölçütü.** Aynı görevlerde adım sayısı ve token düşer, başarı gerilemez.

**Ölçüm.** starter seti `--repeat 3`, iki değerle karşılaştırma.

**Risk.** Çok küçük pencere, büyük dosyada modeli sonsuz sayfalamaya sokar; devam notu ve özet şart.

---

## B. Yürütme döngüsü (Dalga 2)

### 6. Önce reprodüksiyon testi — M

**Ne.** Hata düzeltme görevlerinde önce hatayı gösteren testi üretmek, kırmızıyı görmek, sonra düzeltmek.

**Kanıt.** ReProAgent entegrasyonu SWE-agent'ın çözdüğü konuyu 143 → 153 çıkardı. Agentless seçim aşamasında reprodüksiyon testi + regresyon + çoğunluk oyu kullanıyor.

**Dokunulan yer.** `engines/agent/plan_parser.py` (plan şeması), `core/execution_plan.py:VerificationCheck`, `engines/agent/step_verification.py`, `engines/agent/prompts/execution_plan.md`.

**Nasıl.**
- Görev türü "hata düzeltme" ise plan şeması "hatayı gösteren test" adımını zorunlu kılar.
- İki ayrı kanıt kaydedilir: düzeltmeden ÖNCE testin başarısız olduğu, SONRA geçtiği. Yalnız ikinci kanıt "düzeltildi" demek için yeterli sayılmaz.
- Test üretilemiyorsa adım `unverified` kalır ve final bunu uyarı olarak taşır (mevcut `UNPROVEN_BEHAVIOR_WARNING` yolu).

**Kabul ölçütü.** Hata düzeltme görevlerinde "düzeltildi" iddiası daima iki kanıtla gelir; yanlış başarı sayısı sıfır.

**Ölçüm.** `traceback-okuyup-duzelt`, `test-ciktisini-okuyup-duzelt` ve yeni hata setleri; metrik: doğrulanmış düzeltme oranı.

**Risk.** Kötü test, yanlış yöne sürükler (SWE-Doctor'ın uyarısı: fail-to-fail testler yanıltıyor). Test kalitesi ayrıca denetlenmeli.

---

### 7. Runtime tanı kaydı — M

**Ne.** Ham hata çıktısını yapılandırılmış tanıya çevirmek: konum, belirti, yayılım yolu, gözlenen değerler.

**Kanıt.** SWE-Doctor bu tanıyla SWE-bench Verified %75,7. Bizim Godot koşusunda `SCRIPT ERROR ... at: res://player.gd:12` elimizdeydi ve kimse bunu "düğüm tipi ↔ script API uyuşmazlığı" tanısına çeviremedi.

**Dokunulan yer.** `engines/agent/verification.py` (`CommandVerifier`, `_tail`, `_ZERO_EXIT_FAILURE_MARKERS`), `core/evidence.py`, `engines/agent/recovery.py`.

**Nasıl.**
- Çıktı ayrıştırıcıları eklenir: Python traceback, pytest özeti, Godot `SCRIPT ERROR`, `tsc`/`node` hatası, `cargo` hatası.
- Her biri `Diagnosis(dosya, satır, belirti, sembol, ham_alıntı)` üretir; `CriterionEvidence`'a bağlanır.
- `choose_recovery` bu tanıyı alır ve kurtarma istemi "hata metnini oku" yerine "şu dosyada şu satırdaki şu belirtiyi düzelt" olur.
- Tanı üretilemezse ham çıktı korunur; uydurma yapılmaz.

**Kabul ölçütü.** Kurtarma turu, hatanın gösterdiği dosyaya ilk denemede dokunur; oku-anla-düzelt sınıfında başarı artar.

**Ölçüm.** Godot seti + hata setleri; metrik: kurtarma turu başarısı, adım başına deneme.

**Risk.** Ayrıştırıcı listesi dilden dile büyür; her biri test edilmeli, yoksa yanlış tanı doğru koda müdahale ettirir.

---

### 8. Paralel deneme ve kanıtla seçim — L

**Ne.** Bir adımı N kez bağımsız denemek ve kazananı kanıtla seçmek.

**Kanıt.** Yürütme tabanlı doğrulayıcılarla Best@K'de +%10-15; Agentless'ta seçim aşaması reprodüksiyon + regresyon + oy.

**Dokunulan yer.** `engines/agent/plan_runner.py:_PlanRun.run_step`, `engines/workflow/model.py:BudgetEnvelope`, `core/changeset.py`, yeni `engines/agent/attempts.py`.

**Nasıl.**
- Adım, izole çalışma kopyalarında N kez koşar (git deposu varsa worktree, yoksa dizin kopyası).
- Her aday `verify_step` ile puanlanır; eşitlikte reprodüksiyon testi ve regresyon sonucu, sonra çoğunluk oyu belirler.
- Kazanan kopya ana ağaca uygulanır; diğerleri artifact olarak saklanır (teşhis için).
- Yeni `ATTEMPTS` bütçe zarfı eklenir; N görev zorluğuna göre 1'e düşebilir.

**Kabul ölçütü.** Aynı sette Best@N, N=1'e göre ölçülebilir kazanç verir ve maliyet artışı raporlanır.

**Ölçüm.** starter + Godot, `--repeat 3`; metrik: başarı, maliyet başına başarı, süre.

**Risk.** Ücretsiz sağlayıcıda kota ve eşzamanlılık sınırı; oturum çakışması. Sağlayıcı başına eşzamanlılık tavanı gerekir.

---

### 9. Bağlam condenser'ı — M

**Ne.** Bağlam eşiğe gelince eski olayları özetle değiştirmek, orijinali artifact'ta tutmak.

**Kanıt.** OpenHands condenser'ı oturumun pencereyi sınırsız aşmasını sağlıyor; Anthropic compaction'ı 5-20k / 50-100k token aralıklarında öneriyor.

**Dokunulan yer.** `engines/agent/loop.py` mesaj listesi, `core/compression.py`, `core/checkpoint.py`, `history/`.

**Nasıl.**
- Pencerenin %70'inde tetiklenir: eski araç sonuçları ve ara adımlar tek bir özet mesaja indirilir.
- Özet, hedef + ulaşılan durum + açık işler + kritik kararlar başlıklarını taşır (blueprint Tier 3).
- Condensation olayı checkpoint'e yazılır; `resume` neyin özetlendiğini bilir.
- Özetleme için ucuz model kullanılabilir (madde 10 ile birlikte).

**Kabul ölçütü.** 50+ adımlık görev bağlam taşmadan tamamlanır; özetten sonra doğruluk düşmez.

**Ölçüm.** Uzun görev seti; metrik: tamamlanma, özet sonrası hata oranı.

**Risk.** Özet kritik ayrıntıyı düşürür. Kanıt ve artifact referansları özetin dışında, yapılandırılmış alanda tutulmalı.

---

### 10. Zorluk temelli yönlendirme — M

**Ne.** Ucuz modeli varsayılan yapmak, takıldığı yerde güçlü modele yükseltmek.

**Kanıt.** Sektörde yaygın desen: trafiğin %60-80'i ucuz modelde, en zor %20 güçlüye yükseltiliyor.

**Dokunulan yer.** `core/routing_strategy.py`, `core/health.py`, `engines/agent/recovery.py`, `engines/agent/promotion.py`.

**Nasıl.**
- Yeni `ESCALATE` stratejisi: adım ilk denemede ucuz modelle koşar.
- `classify_failure` aynı adımda ikinci kez düşerse yedek zincirin bir üst modeli devreye girer; karar `HealthRegistry`'ye yazılır.
- Yükseltme kararı kanıta bağlanır (hangi hata sınıfı yükseltmeyi tetikledi), böylece eşik ölçümle ayarlanır.

**Kabul ölçütü.** Maliyet başına başarı artar; toplam başarı en az sabit kalır.

**Ölçüm.** starter seti iki profil ile; metrik: başarı, çağrı sayısı, süre.

**Risk.** Yükseltme kriteri gevşerse her görev pahalı modele kaçar; sıkı olursa hiç tetiklenmez. Eşik ölçümle sabitlenmeli.

---

## C. Mimari sıçrama (Dalga 3)

### 11. Repo haritası — L

**Ne.** Sembol grafiği + sıralama ile bütçeye sığan depo haritası.

**Kanıt.** Aider'ın büyük depoda ucuz kalmasının ana sebebi; taksonomi AST tabanlı erişimin anahtar kelime aramasından üstün olduğunu söylüyor.

**Dokunulan yer.** Yeni `core/repo_map.py`, `engines/agent/loop.py` sistem bağlamı, `tools/search.py`.

**Nasıl.**
- tree-sitter ile tanımlar çıkarılır (fonksiyon, sınıf, dışa açık semboller).
- Dosyalar arası referans grafiği kurulur, PageRank benzeri sıralama uygulanır.
- Bütçeye sığan harita sistem bağlamına eklenir; boyut yapılandırılabilir (`--map-tokens` muadili).
- Yerelleştirme adımı önce haritaya, sonra grep'e başvurur.

**Kabul ölçütü.** Büyük depoda ilk doğru dosyaya varma adımı azalır; token düşer.

**Ölçüm.** Gerçek bir depo üzerinde yerelleştirme seti; metrik: ilk doğru dosya adımı, token.

**Risk.** tree-sitter bağımlılığı ve dil gramerleri paket boyutunu büyütür; paketli runtime'a etkisi ölçülmeli.

---

### 12. Döngü primitifleri kütüphanesi — L

**Ne.** Tek gömülü akış yerine birleştirilebilir döngü primitifleri.

**Kanıt.** Taksonomi: bütün mimariler beş primitifin (ReAct, üret-test-onar, planla-yürüt, çok-denemeli-tekrar, ağaç arama) bileşimi. mini-swe-agent: basit görevde sade yol daha iyi.

**Dokunulan yer.** `engines/agent/plan_runner.py`, yeni `engines/agent/loops/`, `engines/agent/classify.py`.

**Nasıl.**
- Mevcut `_PlanRun` akışı primitiflere ayrılır; her primitif aynı kanıt ve bütçe sözleşmesini kullanır.
- Görev türü hangi bileşimin çalışacağını seçer: basit görev tek ReAct turu, hata düzeltme üret-test-onar, büyük iş planla-yürüt.
- Her primitif kapatılabilir; "iskele modelin önüne geçmesin" kuralı yapılandırmaya bağlanır.

**Kabul ölçütü.** Basit görevlerde adım ve token düşer; karmaşık görevlerde başarı korunur.

**Ölçüm.** Görev türüne göre ayrıştırılmış starter sonucu.

**Risk.** Büyük refactor; kanıt/checkpoint sözleşmesi bozulursa bu haftanın kazanımları kaybolur. Testler önce yazılmalı.

---

### 13. Süreç ödülü / rubrik doğrulayıcı — M

**Ne.** Adım bitmeden ilerlemeyi puanlayıp kötü dalı erken kapatmak.

**Kanıt.** SWE-TRACE: rollout sırasında budama, sonradan yeniden sıralamadan iyi.

**Dokunulan yer.** `engines/agent/step_verification.py`, `engines/agent/loop.py` tur içi kontrol, `engines/agent/recovery.py`.

**Nasıl.**
- Hafif rubrik: kanıt üretildi mi, dosya/durum değişti mi, aynı hata tekrar mı ediyor, araç çağrısı başarı oranı düşüyor mu.
- Eşiğin altında kalan tur erken kapatılır ve kurtarmaya devredilir; mevcut "3 turdur ilerleme yok" sezgisinin ölçülebilir hâli.
- Puan kanıt olarak kaydedilir, sonradan eşik ayarlanabilir.

**Kabul ölçütü.** Boşa harcanan tur sayısı düşer; başarı sabit kalır veya artar.

**Ölçüm.** starter + Godot; metrik: başarısız görevde harcanan çağrı.

**Risk.** Erken kapatma, yavaş ama doğru ilerleyen turu keser; eşik ölçümle konur.

---

### 14. Koşu içi araç üretimi — L

**Ne.** Ajanın koşu sırasında kendine görev-özel araç yazması.

**Kanıt.** Live-SWE-agent: yalnız bash ile başlayıp kendine araç yazarak SWE-bench Verified %77,4, SWE-Bench Pro %45,8; çevrimdışı eğitim maliyeti sıfır.

**Dokunulan yer.** `engines/agent/engine_tools.py`, `tools/registry.py`, `engines/agent/approval.py`, `core/tools.py:ToolFamily`.

**Nasıl.**
- `make_tool` primitifi: agent `.fusion/tools/<ad>.py` altına küçük bir betik ve şeması yazar.
- `ToolRegistry` bunu tur içinde kaydeder; aile `EXTERNAL`, onay ve kapsam kuralları aynen geçerli.
- Adım sonlarında "bu işi hızlandıracak bir araç yazmalı mıyım" yansıması sorulur (Live-SWE-agent'ın deseni).
- Üretilen araçlar oturum sonunda saklanır ve tekrar kullanılabilir; kalıcı hale gelmesi kullanıcı onayına bağlıdır.

**Kabul ölçütü.** En az bir gerçek görevde üretilen araç tekrar kullanılır ve adım sayısını düşürür.

**Ölçüm.** Godot + veri işleme setleri; metrik: adım sayısı, tekrar kullanım.

**Risk.** Güvenlik: model kendi aracını yazıp çalıştırıyor. Sandbox, onay ve kapsam kuralları gevşetilmemeli.

---

### 15. Alan adaptörleri — M

**Ne.** Alan başına "neyin kanıt sayıldığını" tanımlayan eklenti katmanı.

**Kanıt.** Ortak motor + alana özel kanıt ayrımı; bugün Godot'ta kanıt sözleşmesi kodun içine gömülü.

**Dokunulan yer.** `engines/agent/verify_discovery.py`, `engines/agent/verification.py`, yeni `engines/agent/domains/`.

**Nasıl.**
- Adaptör arayüzü: keşif (bu proje bu alana mı ait), kapı komutları, kanıt kuralları, tanı ayrıştırıcıları.
- Godot adaptörü: proje açılır + N kare hatasız + sahne düğüm tipi ile script API'si tutarlı.
- Web adaptörü: sayfa yüklenir + kritik akış tıklanır + konsol hatası yok.
- Veri/MCP adaptörü: yapılandırılmış sonuç şemayı doğrular.

**Kabul ölçütü.** Yeni bir alan eklemek motoru değiştirmeden mümkün olur; Godot kabulü adaptörden gelir.

**Ölçüm.** Godot ve web setleri; metrik: yanlış başarı sayısı.

**Risk.** Adaptörler motor kurallarını ezmeye başlarsa tek sözleşme bozulur; adaptör yalnız kanıt tanımlar, akış tanımlamaz.

---

## D. Eksik iş kolları — paritenin görünmeyen yarısı

### 16. Gözlemlenebilirlik: adım telemetrisi ve koşu izleyici — M

**Ne.** Her adımın ne yaptığını, neden düştüğünü ve neyi harcadığını makine tarafından okunabilir biçimde kaydetmek.

**Kanıt.** Bugün 5 başarısızlığın sebebini transkript okuyup elle buldum; bu ölçeklenmez.

**Dokunulan yer.** `observability/json_sink.py`, `core/events.py`, `evals/transcript.py`, yeni `fusion trace` komutu.

**Nasıl.**
- Olay şeması sabitlenir: adım, araç, sonuç, kanıt durumu, bütçe, model, süre, ayrıştırma kurtarması.
- Koşu sonunda tek dosyalık iz; `fusion trace <koşu>` ile özet tablo ve başarısızlık nedeni sınıflandırması.
- Hata taksonomisi: araç engeli, ayrıştırma, model boş yanıt, doğrulama, bütçe, sağlayıcı hatası.

**Kabul ölçütü.** Bir koşunun neden düştüğü, transkript okumadan tek komutla söylenebilir.

**Ölçüm.** Kendi kullanımımız: teşhis süresi.

**Risk.** Sır sızıntısı; mevcut `redaction` tüm yollarda uygulanmalı.

---

### 17. Değerlendirme setinin genişletilmesi — M

**Ne.** 24 görevlik tek seti, alan ve zorluk bazlı setler ailesine çevirmek.

**Kanıt.** Godot koşuları birbirinden belirgin ayrıştı; tek koşu gürültülü. Ölçüm zayıfsa kalan her madde tahmin olur.

**Dokunulan yer.** `evals/suite/`, `evals/tasks.py`, `evals/metrics.py`, `tests/test_eval_criteria_sound.py`.

**Nasıl.**
- Yeni setler: çok dosyalı refactor, hata düzeltme (traceback/test), MCP yapılandırılmış sonuç, tarayıcı akışı, Godot, uzun görev (50+ adım).
- Her yeni ölçüt için referans çözüm (`test_eval_criteria_sound.py` deseni) zorunlu.
- `--repeat 3-5` varsayılan; rapor varyansı da yazsın.
- İnsan müdahalesi sayısı birinci sınıf metrik olur.

**Kabul ölçütü.** Her madde kendi setine karşı önce/sonra ölçülebilir.

**Ölçüm.** Setin kendisi; metrik: kapsanan alan sayısı, varyans.

**Risk.** Set büyüdükçe koşu süresi artar; hızlı alt küme ve tam set ayrımı gerekir.

---

### 18. Web taşıma güvenilirliği — L

**Ne.** Tarayıcı tabanlı sağlayıcıda oturum, kesinti, kota ve tekrar sorunlarının sistematik çözümü.

**Kanıt.** Ağustos'tan beri ayrı bir hata kaynağı; bugünkü koşularda da "boş yanıt" ve onay/oturum kaynaklı kayıplar görüldü.

**Dokunulan yer.** `providers/web_browser.py`, `providers/web_session.py`, `providers/web_transport.py`, `core/health.py`.

**Nasıl.**
- Yanıt bütünlüğü denetimi: yarım blok, kesilmiş kod, boş yanıt ayrı sınıflar olarak tanınır ve farklı kurtarma alır.
- İdempotency: aynı adımın tekrarında yan etkinin iki kez üretilmemesi için araç çağrısı kimliği taşınır.
- Kota ve hız sınırı geri çekilmesi (backoff), sağlayıcı sağlığına yazılır.
- Oturum yenileme ve konuşma sürekliliği testleri sabit senaryolarla otomatikleşir.

**Kabul ölçütü.** Aynı sette sağlayıcı kaynaklı başarısızlık sınıfı ölçülebilir biçimde azalır.

**Ölçüm.** starter seti + uzun görev; metrik: sağlayıcı hatası sayısı, boş yanıt.

**Risk.** Tarayıcı arayüzü değişir; testler kırılgan olur. Sözleşme testleri sabit fikstürlerle yazılmalı.

---

### 19. İzole ve paralel çalışma altyapısı — L

**Ne.** Madde 8'in ve alt-ajanların ihtiyaç duyduğu izolasyon, eşzamanlılık ve iptal.

**Kanıt.** Blueprint: iptal birinci sınıf primitif; yan etkiden önce ve sonra checkpoint; deterministik tekrar oynatma.

**Dokunulan yer.** `core/concurrency.py`, `core/changeset.py`, `engines/agent/loop.py`, yeni worktree yöneticisi.

**Nasıl.**
- Git deposunda worktree, dışında dizin kopyası ile izole çalışma alanı.
- Eşzamanlılık tavanı sağlayıcı ve araç bazında; iptal her seviyede yayılır.
- Yan etkili araç çağrıları kimliklenir; tekrar oynatmada iki kez çalışmaz.

**Kabul ölçütü.** N paralel deneme veri kaybı ve çakışma olmadan çalışır; iptal 1 saniyede etkili olur.

**Ölçüm.** Yük testi + paralel deneme seti.

**Risk.** Disk ve bellek maliyeti; büyük depoda kopya pahalı.

---

### 20. Çok dosyalı tutarlılık — L

**Ne.** Model tek dosyayı doğru yazarken bütünü bozmasını yakalayan çapraz dosya denetimi.

**Kanıt.** Godot koşusu: `player.gd` `CharacterBody2D` API'si kullanıyor, sahnede düğüm `Area2D`. `cok-dosyali-modul-kur` görevi hâlâ başarısız.

**Dokunulan yer.** Yeni `core/project_model.py`, `core/structured_files.py`, madde 11'in sembol grafiği.

**Nasıl.**
- Proje modeli: semboller, içe/dışa aktarımlar, sahne-script bağları, şema-veri bağları.
- Değişiklik sonrası çapraz denetim: çağrılan sembol var mı, tip uyuşuyor mu, sahne düğüm tipi script'in beklediği taban mı.
- İhlal, kanıt olarak raporlanır ve kurtarma turuna tanı olarak girer.

**Kabul ölçütü.** Godot tipi uyuşmazlığı, motor çalışmadan önce yakalanır.

**Ölçüm.** Godot + çok dosyalı setler; metrik: yakalanan tutarsızlık, yanlış başarı.

**Risk.** Dil başına ayrı model gerekir; kapsam hızla büyür. Önce iki dil (Python, GDScript) ile sınırlanmalı.

---

### 21. Sağlayıcı yetenek keşfi — M

**Ne.** Her modelin gerçekte neyi desteklediğini elle yapılandırmak yerine ölçerek belirlemek.

**Kanıt.** Görsel taşıma, bağlam uzunluğu ve araç çağrısı desteği sağlayıcıya göre değişiyor; bugün bir kısmı elle yazılı.

**Dokunulan yer.** `core/model_capability.py`, `runtime_health.py`, `core/health.py`.

**Nasıl.**
- Küçük sondaj testleri: görsel gönderilebiliyor mu, uzun bağlam korunuyor mu, araç bloğu doğru üretiliyor mu.
- Sonuçlar önbelleğe alınır ve `ModelCapability`'yi besler; madde 1 ve 2 bu bilgiyi kullanır.
- Sondajlar `fusion doctor` altında görünür.

**Kabul ölçütü.** Yeni bir sağlayıcı eklendiğinde elle yetenek yazmadan doğru biçim seçilir.

**Ölçüm.** İki sağlayıcıda sondaj doğruluğu.

**Risk.** Sondaj maliyeti; oturum başına bir kez ve önbellekli olmalı.

---

### 22. Kullanıcı deneyimi paritesi — L

**Ne.** Araya girme, yönlendirme, diff inceleme, devam ve iptal akışları.

**Kanıt.** Codex/Claude Code paritesi yalnız başarı oranı değil; kullanıcı bu akışlarla çalışıyor.

**Dokunulan yer.** `cli/repl/`, `appserver/`, `app/` (Tauri arayüzü), `engines/agent/loop.py` iptal yolu.

**Nasıl.**
- Koşu sırasında mesajla yönlendirme (steering) ve güvenli duraklatma.
- Değişikliklerin diff olarak sunulması, adım adım kabul/ret.
- Duraklatılan işin listelenmesi ve tek komutla devam (`checkpoint` altyapısı hazır).

**Kabul ölçütü.** Uzun bir görev, kullanıcı araya girip yön verdikten sonra kaldığı yerden doğru şekilde sürer.

**Ölçüm.** Senaryo testleri (masaüstü + CLI).

**Risk.** Arayüz ve motor sözleşmesi ayrışırsa iki taraf farklı davranır; protokol testleri şart.

---

### 23. Uzun koşuda güvenlik, kota ve maliyet — M

**Ne.** Saatlerce otonom çalışan bir ajan için izin, sır, kota ve geri alma disiplini.

**Kanıt.** Bu hafta checkpoint'e ham araç çıktısı yazıldığını ve `.env` sızma yolu olduğunu ölçtük; madde 14 model tarafından yazılan kod çalıştırıyor.

**Dokunulan yer.** `engines/agent/approval.py`, `tools/command_policy.py`, `core/redaction.py`, `config/permissions.py`.

**Nasıl.**
- Uzun koşu için risk kademeleri: okuma serbest, yumuşak yazma loglu, sert yazma onaylı, yıkıcı daima onaylı.
- Kota ve maliyet tavanı; aşımda güvenli duraklatma.
- Geri alma: her adımın öncesi/sonrası artifact ve git noktası.

**Kabul ölçütü.** Otonom bir saatlik koşuda hiçbir sır loglara/checkpoint'e düşmez; yıkıcı işlem onaysız çalışmaz.

**Ölçüm.** Sızıntı taraması + izin senaryo testleri.

**Risk.** Aşırı sıkı politika otonomiyi öldürür; kademe ölçümle ayarlanır.

---

### 24. Determinizm ve tekrar oynatma — M

**Ne.** Bir koşuyu aynı girdilerle yeniden üretebilmek ve adım adım incelemek.

**Kanıt.** Blueprint: deterministik replay, tipli durum + olay geçmişi. Ajan hatalarının ayıklanması bunsuz tahmin işi.

**Dokunulan yer.** `evals/transcript.py`, `core/checkpoint.py`, `observability/`, yeni replay komutu.

**Nasıl.**
- Model yanıtları ve araç sonuçları kayıtlı fikstüre yazılır; replay modunda ağ yerine kayıt kullanılır.
- Bir başarısızlık, tek komutla yeniden üretilebilir hâle gelir ve regresyon testine dönüştürülebilir.
- Rastgelelik (örnekleme, sıralama) tohumlanır.

**Kabul ölçütü.** Canlı koşudaki bir başarısızlık, ağsız olarak birebir tekrar üretilebilir.

**Ölçüm.** Seçilmiş üç başarısızlık üzerinde tekrar üretim.

**Risk.** Fikstür boyutu; artifact deposuyla (madde 3) ortak çözülmeli.

---

## Bağımlılık haritası

- **16, 17, 24** diğer her şeyin önkoşulu: ölçüm ve teşhis olmadan kalan maddelerin etkisi bilinemez.
- **3** madde 9'un, **11** madde 20'nin, **19** madde 8 ve 14'ün önkoşulu.
- **1, 2, 4, 5** birbirinden bağımsız; paralel yürütülebilir.
- **12** en yıkıcı refactor; 1-10 arası kararlar oturmadan başlanmamalı.

## Sıra önerisi

1. **16 + 17** (gözlemlenebilirlik ve set) — sonraki her maddenin kanıtı buradan gelir.
2. **1 + 2** (düzenleme biçimi ve şema) — literatürdeki en büyük tek sıçrama, ölçüm hazır olduğunda.
3. **4 + 5 + 3** (dil kapısı, ACI ayarı, artifact).
4. **7 + 6** (runtime tanı ve reprodüksiyon testi) — oku-anla-düzelt sınıfı buradan düzelir.
5. **18** (web taşıma) — sağlayıcı kaynaklı gürültü temizlenir.
6. **10 + 13 + 9** (yönlendirme, rubrik, condenser).
7. **19 → 8** (izolasyon, sonra paralel deneme).
8. **11 → 20** (repo haritası, sonra çapraz tutarlılık).
9. **15 + 21 + 23 + 22** (adaptörler, yetenek keşfi, güvenlik, UX).
10. **12 + 14** (primitif kütüphanesi, koşu içi araç üretimi).
