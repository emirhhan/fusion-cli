# Fusion + Nemotron 3 Ultra: 6 kabul testini gerçekten geçmek için araştırma raporu

**Tarih:** 4 Ekim 2026 · **Yöntem:** 6 bağımsız kanıt araştırması (depo raporları, Claude oturumları, Codex oturumları, mimari denetim, Hermes/Codex/Fusion karşılaştırması, dış literatür) → sentez → iki denetim (kanıt şüphecisi kodda doğruladı, kapsam eleştirmeni eksikleri aradı) → bu rapor. Depo HEAD: `0a79099`. Yollar `src/fusion_cli/` köküne göredir; kabul kayıtları `~/Desktop/01-Projeler/fusion-kabul/`.

Kanıt durumu etiketleri: **[doğrulandı]** kodda/kayıtta yeniden kontrol edildi · **[kayıt]** oturum/rapor kaydına dayanıyor · **[tahmin]** ölçülmedi.

---

## Kısa cevap

1. **Sorun çoğunlukla Fusion'da, model sınırı gerçek ama ikincil.** Kabaca tahmin [tahmin]: sneaksup başarısızlığının ~üçte ikisi Fusion (yöntem seçimi, kapı, bağlam, araç altyapısı), ~üçte biri model (WooCommerce sözleşmesini bozma, sıfırdan yazma eğilimi, uzun yazım). Aynı model aynı hataları Hermes ve Codex'te de yaptı; ama Fusion dışı bir betik (kopyala.py) görünümü neredeyse birebir verdi.
2. **Model kendi seçmesi gereken hiçbir yardımcıyı seçmiyor.** 5.-17. koşuların 1.696 araç çağrısında: `find_skill` 0, `read_skill` 0, `recall_lessons` 0, `view_image` 0, `spawn_agent` 0, `make_tool` 0, `browser_mirror` 1; `run_shell` 936 [doğrulandı]. Nemotron araca değil **araç sonucuna ve harness'in o anki yönlendirmesine** tepki veriyor. Doğru yöntem modele bırakılmamalı, harness tarafından çalıştırılmalı.
3. **6 testin 3'ü hiç sınanmadı:** animasyon, Remotion ve "Fusion kendini geliştirir" için tek bir Fusion koşusu yok. Fusion Browser terminal kabul koşularında yapısal olarak yok.

**En etkili 5 hamle:**
1. **Ölçüm zemini önce:** 6 alan × 1-2 görevlik küçük eval iskeleti + koşu öncesi ortam kontrolü + sonuç sınıfları (geçti / kaldı / geçersiz / öğretmen-destekli). Yoksa hiçbir değişikliğin işe yarayıp yaramadığı bilinmez.
2. **Ucuz ve kanıtlı düzeltmeler:** bağlam muhasebesi hatası, start_preview'ın yanıltıcı ilk satırı, kapanış kapısının farkları ve sepet testini görmemesi, `read_skill` uzantıları.
3. **Arka plan iş yürütücüsü:** 120 sn kabuk sınırı Remotion, npm ve Godot export'u imkânsız kılıyor; 3 alanın önünü birden açar.
4. **Kopyala-sonra-bağla hattı:** model seçmeden harness'in çalıştırdığı ön adım (DOM + CSSOM + yapısal katalog). Model yalnızca dinamik bölgeleri bağlar. Önce küçük dilim, ölç, sonra büyüt; ikinci bir siteyle genelle.
5. **Kabulü eklentili masaüstü yolundan koş** (ChromeBridge orada zaten var) ve Nemotron istek profilini canlı sondayla A/B'le.

---

## 1. Teşhis — kanıtlı kök neden haritası

### 1a. Fusion'daki pay

| # | Kök neden | Kanıt | Durum |
|---|---|---|---|
| F1 | **Yöntem kilidi: "ölç → sıfırdan yaz → farkı düzelt".** `turn_hints.DESIGN_NOTE` (`engines/agent/turn_hints.py:59-70`) yalnız site_design→start_preview zincirini söylüyor, `browser_mirror`'u anmıyor. Aracın açıklaması "Tek sayfa iner, dinamik veri yerelde çalışmayabilir" (`tools/builtin.py:473-475`), sonuç metni "REFERANS olarak kullan, teslim olarak değil" (`tools/mirror.py:142-143`). Teknik olarak `page.content()` (`tools/browser.py:243`): emotion/MUI'nin çalışma anında CSSOM'a yazdığı kurallar taşınmıyor. Öğretmen planı da browser_open→site_design→edit_file diyor. 1.696 çağrıda browser_mirror=1. | doğrulandı |
| F2 | **Bilgi katmanları "çek" tabanlı ve hiç çekilmiyor.** Skill, ders ve alt ajan araçları 0 kez çağrıldı. `web_reference.md` (22,8 KB) hiçbir yerden yüklenmiyor (`loop.py:144` yalnız system_api.md). `read_skill` yalnız `.md .txt .yaml .yml .json .toml .py .sh` okuyor (`tools/capabilities.py:180`); Remotion/animasyon şablonları (.ts/.tsx/.css/.html) okunamıyor. Remotion skill'leri skill kök listesinde değil. **Not:** tur başına skill/ders basma kasıtlı kaldırıldı (`loop.py:474-477`, yanlış sınıflanan turda 21 KB web referansı yanlış bağlam taşıdı). Yani çözüm "her şeyi bas" olamaz. | doğrulandı |
| F3 | **Kapanış kapısı farkları ve sepet testini görmüyor.** `site_verify._result` yalnız `sonuc.problems`'a bakıyor (`engines/agent/site_verify.py:91-106`). KAYNAKLA FARKLAR ve shop_flow yalnız start_preview aracında (`preview_tools.py:142-163, 354-364`). 0a79099 sonrası bunlar modele gidiyor ama kapıya ve rapor başlığına girmiyor. 17. koşuda farklar açıkken rapor "✓ Doğrulandı: php -l … temiz" yazdı. Aynı sahte başarı sınıfı en az 8 koşu/oturumda görüldü (Godot exit 0, GATE ok=true/3 fail, WP php -l=doğrulandı, 14. koşu 16/17 sanılan 14/17). | doğrulandı (kod) + kayıt |
| F4 | **Bağlam muhasebesi hatası.** `history.total_chars` yalnız `message.content` topluyor (`engines/agent/history.py:53-55`), `tool_calls` argümanlarını saymıyor (`core/types.py:64`). 17. koşuda ContextCompressed=0, istem en yüksek 184.916 token, 169 çağrıda toplam 17.622.189 prompt token. Eski araç çıktısı temizleme (`history.py:85-`) çalışıyor ama dosya yazım argümanları birikiyor. | doğrulandı |
| F5 | **İstek profili ölçülmemiş.** `temperature: 0.3` (`config/defaults.yaml:123`), `max_tokens: 8192` (`:168`), `top_p` ve `parallel_tool_calls` hiç gönderilmiyor. Düşünme yalnız başarısızlıktan SONRA kapatılıyor; aynı header.php 161 sn→29 sn. **Düzeltme (taslaktan):** varsayılan `reasoning_effort: auto` hiç parametre göndermiyor (`core/reasoning.py:20`); NIM şemasında olmayan `low` yalnız kurtarma yolunda gidiyor ve yanında `enable_thinking=false` var (`loop.py:1781-1784`). NVIDIA'nın 1.0/0.95 önerisi ve reasoning_budget değerleri dış kaynak; canlı sondayla doğrulanmalı. | doğrulandı + dış |
| F6 | **Yanıltıcı teşhis zinciri.** start_preview çıktısı başarısızken de "Önizleme çalışıyor… Kullanıcı bu adresi açabilir" ile başlıyor (`preview_tools.py:329`). `_failure_signature` ilk satırı alıyor (`loop.py:2864-2878`), `_plateau_question` öğretmene "şu hatayı N kez verdi: Önizleme çalışıyor" gönderiyor (`loop.py:2159-2162`). Öğretmen "hata yok" dedi, 2 tur gitti. Kör modele "ekran görüntüsü ekte, karşılaştır" deniyor (`preview_tools.py:349`). | doğrulandı |
| F7 | **Kapı ⊆ yetenek değişmezi yok.** Kapı ya da sınıflandırıcı en az 7-8 olayda modeli sahip olmadığı araca yönlendirdi ya da yazmayı kapattı (Godot save_scene, read_file kapsam dışı, yedek tur salt-okunur, "yapmanı"→"yapma", İngilizce "Implement" değişiklik sayılmadı). Her biri tekil yamayla kapandı. | kayıt |
| F8 | **Uzun komut altyapısı yok.** `SHELL_TIMEOUT_S = 120.0` (`core/constants.py:63`), arka plan/yoklama yok (`tools/shell.py:48,136`). npm install, `npx remotion render` ve godot export takılır. | doğrulandı |
| F9 | **Kabul düzeni Fusion Browser'ı dışarıda bırakıyor.** ChromeBridge yalnız masaüstü yolunda kuruluyor (`appserver/session.py:403,1437`); terminalde chrome_* gizleniyor (`engines/agent/engine_tools.py:101,186`). Bu bir ürün eksiği değil, test düzeni sorunu. Giriş anlatısı ise bağlı olmayan eklentiyi kullanacağını yazdı (narration araç listesini bilmiyor). | doğrulandı |
| F10 | **"Yazıldı ama bağlanmadı" sınıfı.** web_reference.md yükleyicisiz; `DomainRegistry.acceptance_criteria`'nın üretimde çağıranı yok; DomainAdapter v2 planı yarım; 30 Eylül'e kadar masaüstü turu `memory=` geçirmiyordu; kurulu paket ≥5 kez kaynağın gerisinde kaldı. | kısmen doğrulandı |
| F11 | **Ölçüm güvenilmez.** 6 alanın hiçbiri `evals/` altında değil: yalnız arena, godot_project, oauth ping ve long_tasks/fiyat_aktarimi var; `domain_adapters/` yalnız web ve godot. Aynı sette tek koşu 4/15–14/15 oynuyor. %79→94 sayıları Gemini Flash-Lite ile alındı, Ultra ile aynı set hiç ölçülmedi. | doğrulandı + kayıt |

### 1b. Modeldeki pay (kayıt + dış kaynak)

| # | Davranış | Kanıt |
|---|---|---|
| M1 | Sıfırdan yazma ve görünmez altyapıya kaçış | Üç harness'ta aynı. Codex 370 KB PHP (customizer, REST, admin) yazdı, style.css 566 B kaldı. |
| M2 | WooCommerce çekirdeğini söküp yeniden yazma | Fusion: Woo stilleri dequeue edildi, sepete ekle `<form>` dışında (`kabul17/.../functions.php:77-79,132,159-170`). Codex 8+ `remove_action`. |
| M3 | Büyük araç argümanını akıtmama, çıktı sınırı | Hermes 3×finish_reason=length; Codex 2×5 dk SSE kesintisi; Fusion'da 16384 token 600 sn'yi aştı (`loop.py:1679-1681`). |
| M4 | Aşırı güven, erken durma, uydurma | CodeRabbit: koşu başına 36,5 yeniden deneme. Uydurma yol/URL/rakam ≥10 olay. |
| M5 | Görsel okuyamıyor | multimodal 400 |
| M6 | Mevcut kod tabanında okuma döngüsü | 7/7 tek başına koşu 0 değişiklik (Super, GLM, Mistral, DeepSeek). Ultra'ya genelleme [tahmin]. |
| M7 | Politika-ağır, uzun ufuklu işlerde zayıf | TauBench Banking 22,6 vs Telecom 92,9; EnterpriseOps-Gym %33 |
| M8 | **Güçlü yan** | Kısa/izole üretim 15/15; davranış testi tanımlı HTML arena 5/5; SWE-bench Verified 5 harness'ta %65-70 (harness'e dayanıklı) |

Belirsiz: 156/156 çağrı tek araç çağrısı üretti. `parallel_tool_calls` hiç gönderilmediği için model sınırı mı sağlayıcı mı bilinmiyor.

### 1c. Test düzenindeki pay

Kabul terminalden koşuldu (eklenti yok). Her deney tek koşu, 90 dk sınırlı. Hermes/Codex kıyası doğrulamada haksız (Hermes `verify_on_stop` kapalı, Codex `on-request`). Ortam gürültüsü: NIM aşırı yük, 429, disk, captcha, CDP "Browser context management is not supported". Öğretmen devraldığında işi Gemini yazıyor ama bu ayrıca kayda geçmiyor.

---

## 2. Nemotron Ultra'nın gerçek sınırları ve telafi yolları

| Sınır | Telafi |
|---|---|
| Görsel okuyamaz | Önce geometri/DOM ile sayısal ölç (kutu kesişimi, sütun sayısı, getAnimations, RAF). Sonra bölge piksel farkı metin olarak. Ancak bunlardan sonra "göz" modeli: eşleşmiş kırpmalar, ikili/pairwise soru, kolaj (tek görsel), önbellek, koşu başına üst sınır. Göz adayları: Gemini web (`gemini_attach_file` hazır, ama web taşıması görselleri düşürüyor `web_browser.py:899-905`) ve NIM Nemotron-3-Nano-Omni (Faz 0'da sondalanacak; çalışırsa Gemini yükü kalkar). Göz erişilemezse "gözsüz mod": sayısal ölçüme düş, sonucu geçersiz say, uydurma. |
| Büyük argümanı akıtmıyor | Model büyük dosya yazmasın: klon parçaları programatik, şablon+include, 100-200 satırlık dosyalar. max_tokens'ı körü körüne büyütme (16384 → 600 sn aşımı ölçüldü). |
| Düşünme bütçeyi yiyor | Adım türüne göre düşünme: yazım adımında kapalı/medium, plan/teşhiste açık. reasoning_budget yalnız canlı sonda kabul ederse. |
| Aşırı güven | "Bitti" kararı kapının: kabul maddeleri hepsi yeşil değilse tur bitmez, eksik madde mesajla geri döner. |
| Opsiyonel aracı seçmiyor | Doğru yöntemi harness ön adımı olarak çalıştır; sonuç araç çıktısı olarak konuşmaya girsin. Kural ve yönlendirme sistem isteminde değil, araç dönüşünde (LangChain bulgusu). |
| Okuma döngüsü | N okumadan sonra ilk yazma eşiği; öğretmen planında dosya listesi. Ultra'da ayrıca ölç. |
| Politika-ağır akışlar | Oku → öner → onay → yaz → geri oku. Bütçe ve yayın durumu asla otonom değil. |

---

## 3. Müdahaleler

Her müdahale **tek tek** A/B'lenir: aynı görev, en az 3 tekrar (karar için 3/3 ya da 5 koşu). Faz sonunda skor düşerse geri alınır. "Ek NIM çağrısı" sütunu 40 RPM bütçesi için.

| # | Müdahale | Etki | Çaba | Alan | Ek çağrı | Ölçüm |
|---|---|---|---|---|---|---|
| I0 | **Eval iskeleti + ortam ön-kontrolü + sonuç sınıfları + metrik kaydı** | Çok yüksek | Orta | hepsi | — | — |
| I1 | Bağlam muhasebesi: `total_chars`'a tool_calls argümanları; eski write_file argümanı "N karakter yazıldı" taslağına | Orta | Küçük | uzun işler | yok | ContextCompressed, prompt token |
| I2 | start_preview durum-önce: "BAŞARISIZ: HTTP 500 — mesaj dosya:satır", "çalışıyor" yalnız ok iken; kör modele "ekran görüntüsü ekte" deme; plateau sorusu ayrıştırılmış durumdan | Küçük-orta | Küçük | 1 | yok | yanlış teşhis |
| I3 | Kapanış kapısı: FARKLAR + shop_flow `site_verify`'a; rapor başlığı kapı sonucundan üretilir. Yeni kapı yazmadan önce **mevcut `DomainRegistry.acceptance_criteria` bağlanır** | Yüksek | Küçük-orta | 1, 4 | yok | false_success=0 |
| I4 | Arka plan iş yürütücüsü (background + job_status / log_tail / wait / kill), ORTAM'a ffmpeg/ffprobe/npx/node | Yüksek | Orta | 3, 4, 5 | yok | render tamamlanma |
| I5 | Kabulü masaüstü uygulama yolundan koş (bridge var); narration gerçek araç listesini bilsin; ön-kontrolde "eklenti bağlı mı" | Yüksek | Küçük | 6, 1 | yok | — |
| I6 | İstek profili: önce canlı sonda (none/medium/high, reasoning_budget, top_p, tool_choice=required, parallel_tool_calls), sonra temperature 0.3↔1.0 ve "yazımda düşünme kapalı" ayrı ayrı A/B | Orta-yüksek | Küçük | hepsi | sonda | length oranı, adım süresi, geçerli araç çağrısı |
| I7 | Ucuz uzmanlık düzeltmeleri: read_skill uzantıları + klasör yolu; web_reference.md'yi skill yap; Remotion skill kökü | Orta | Küçük | 2, 3, 4 | yok | — |
| I8 | Kopyala-sonra-bağla hattı, **küçük dilimle**: mirror v2 (CSSOM, script soyma, `__NEXT_DATA__`/API katalog, 3 viewport referans) → programatik tema parçaları → model yalnız dinamik bölge + hazır ürün içe aktarma aracı. Woo işaretlemesi ve stili sökülmez kuralı **araç sonucunda** verilir. Ölç, sonra büyüt; ikinci site şart | Çok yüksek (alan 1) | Büyük | 1, 4 | az | kabul maddeleri, bölge farkı, süre |
| I9 | Göz: bölge piksel farkı + pairwise kırpma (bütçeli, gözsüz mod) | Yüksek | Orta | 1-4 | +N görsel | göz-insan uyumu |
| I10 | Hedefli uzmanlık itmesi: yalnız **yüksek güvenle** sınıflanan görev türünde (net anahtar kelime + URL/dosya işareti) 1 kısa skill özeti (<1-2 KB); belirsizse itme yok. Geçmişteki 21 KB yanlış bağlam hatası tekrar etmesin | Yüksek | Orta | 2, 3, 4, 6 | yok | ilk 20 çağrıda doğru yöntem aracı |
| I11 | Toplu düzenleme dürtüsü: aynı dosyaya ≥4 benzer edit → araç sonucunda "betikle toplu yap" | Küçük | Küçük | 1 | yok | ardışık edit |
| I12 | MCP: tool_search/tembel şema, `mcp-add --url/--token`, bearer yolu varsayılan, ads okuma eval'i, yazma = plan→onay→yaz→geri oku, injection fixture'ları | Orta-yüksek | Orta | 6 | az | ads eval |
| I13 | Kapı ⊆ yetenek mekanik testi | Orta | Küçük-orta | genel | yok | imkânsız tur sayısı |
| I14 | Kendini geliştirme döngüsü: yalnız harness'i değiştirir; evals/kapılar salt okunur + özet doğrulaması; worktree; hızlı alt küme + gece tam pytest; skor düşerse durur. **Giriş şartı:** I0 + I3 yürürlükte ve en az bir alan eval'i yeşil | Yüksek | Büyük | 5 | çok | gizli testli görevler |

**Taslaktan çıkarılan / yeniden çerçevelenenler:**
- "Geçersiz `low` her çağrıda gidiyor" çıkarıldı: yalnız kurtarma yolunda gidiyor.
- "max_tokens'ı 16-32K'ya çıkar" önerisi çıkarıldı: 600 sn aşımı ölçüldü.
- "Her görevde skill zorla bas" yeniden çerçevelendi: bu geçmişte zarar verdi, I10'daki dar ve yüksek güvenli itmeye dönüştü.
- "`fusion agent --chrome` bayrağı" yerine kabulü uygulama yolundan koşmak öne alındı.
- "Alan başına yeni JSON kapısı" yerine mevcut acceptance_criteria'yı bağlamak öne alındı.

**2 Eylül harness araştırmasından uygulanmamış kalanlar:** API yolunda 100 satırlık okuma penceresi (800 kalıyor), godot --check-only / node --check / tsc kapıları, adım sonu yansıma tetiği, paralel deneme (ATTEMPTS=0), reprodüksiyon kanıtının zorunlu olmaması, acceptance_criteria'nın bağlanmaması.

---

## 4. Test alanı başına plan

Eşikler Faz 0 sonunda baz koşularla **sabitlenir**; aşağıdakiler başlangıç önerisidir [tahmin]. Her alanda bir de "bilerek bozuk" fixture (arena_broken gibi) olacak: denetçi onu geçirirse denetçi bozuktur.

### 1) sneaksup kopyası
- **Gerçek:** sneaksup WordPress değil; Next.js + MUI/emotion, `__NEXT_DATA__` ~222 KB [dış, tek GET]. "Birebir Woo" = React DOM ve CSS'i Woo şablon parçalarına taşımak.
- **Plan:** I2, I3, I1, I11 → I8 küçük dilim → I9.
- **Geçti:** genel kabul maddeleri (logo, menü, bölüm sırası eşleşir; liste sayfası çok sütunlu ve kaynaktaki ürün sayısı; ürün sayfasında varyasyon ve `form.cart` içinde sepete ekle; sepet sayacı artar; sepet ve ödeme formu; test siparişi ödeme geçidi olmadan "kapıda ödeme" ile verilir; açılır katmanlar kapalı başlar; varsayılan WP kenar çubuğu yok). Ek olarak 1440/768/390'da bölge farkı eşik altında, görseller yerel (hotlink yok), 3/3 koşu, insan müdahalesi yok.
- **Genelleme:** farklı yığında 2. site (ör. WP teması ya da statik) aynı maddelerle. Maddeler siteden otomatik türetilir, elle sneaksup'a yazılmaz.
- **Uyarı:** kopya yalnız yerel test içindir; marka, görsel ve ürün verisi üçüncü tarafındır, yayınlanmaz.

### 2) Opus 5.5 düzeyi animasyon
- **Bugün:** sıfır koşu, skill, eval; tokens.css'te keyframes=0.
- **Plan:** I7 + I10 (hareket-kalitesi skill'i, <200 satır, çalışan örnekli) + animasyon sondası (t=0/500/1500 ms kare farkı, `document.getAnimations()`, RAF canlılığı, layout-tetikleyen özellik lint'i, reduced-motion, long-task) + I9 (kare kolajı pairwise).
- **Geçti [eşik tahmin]:** ≥5 farklı hareket kalıbı; layout özelliği animasyonu 0; süreler 150-800 ms; ≥2 farklı easing; reduced-motion bloğu çalışır; long-task >50 ms yok; göz rubriği referansa karşı çift yönlü (A/B ve B/A) ×3 tekrarda "eşit veya iyi" ≥%50; 8 görevlik sabit sette insan son bakışı.
- **Referans:** 8 görev için bir kerelik referans çıktı (Claude ya da senin beğendiğin siteler). Karar sende.

### 3) Remotion
- **Bugün:** sıfır. Önce I4 şart.
- **Plan:** Faz 0'da "boş projeden 5 sn render" ortam sondası (Node, Chromium indirmesi, ffmpeg). Ardından remotion-dev/skills commit'e sabitlenmiş kurulum, remotion alan adaptörü (CSS transition/animate yasağı lint'i, `useCurrentFrame/interpolate` zorunlu, `npx remotion compositions`, `still/render --frames`, ffprobe) ve kare kolajı.
- **Geçti [eşik tahmin]:** 1080p 30 fps 10 sn (±0,1 sn) render tamamlanır; render ≤10 dk; ardışık kare ortalama farkı >ε (boş/donuk kare yok); lint temiz; metin güvenli alanda (DOM kutu kontrolü); 3/3.
- **Not:** Remotion ticari kullanımda şirket lisansı isteyebilir. Karar sende.

### 4) Kaliteli HTML görsel ve oyun
- **Bugün:** arena davranış eval'i 5/5 ama debug sözleşmesi görev metninde, ürünün içinde değil. Godot'ta kabul edilmiş otonom teslim yok.
- **Plan:** ürün içi `play_probe` (konsol=0, RAF, girdi→durum değişimi, oyun-bitti/yeniden başlat, canvas piksel varyansı), `__FUSION_GAME_DEBUG__` sözleşmesini iskele/skill'e taşı, varlık doğrulama + lisans kaydı, AI-slop kontrolü + göz. Görev seti: arena, platform, bulmaca, canvas efekt, landing ×2.
- **Geçti:** play_probe yeşil + varlıklar sahnede kullanılıyor + göz rubriği eşik üstü + 3/3. Godot ayrı alt alan: --check-only + headless N kare + tick testi (kapsamı sen belirle).

### 5) Fusion kendini geliştirir
- **Bugün:** Fusion'ın Fusion'ı değiştirdiği kayıtlı koşu yok; RULES.md 14 KB→4 KB kırpılıyor; tam pytest ~30 dk.
- **Plan:** I1 + I0 + I14; kademeli görevler: 1 hata düzelt → 1 küçük özellik (ör. `mcp-add --url/--token`) → 1 refactor. Büyük modül bölme sona.
- **Geçti:** ruff + mypy + hızlı test alt kümesi + gizli testler geçer; değerlendirici dosyalarına dokunulmaz (özet doğrulaması); 3/3; "Nemotron-tek" ve "öğretmen-destekli" ayrı raporlanır.

### 6) Meta/Google Ads MCP + Fusion Browser
- **Plan:** I5 + I12 + reklam playbook'u.
- **Fixture seti (10 görev, yerel):** form doldurma, çok sekme, iframe, dosya yükleme, tablo okuma, sayfalama, açılır pencere tablosu (aria-hidden tuzağı), giriş sonrası sayfa (oturum açık), 2 **injection** görevi (sayfa içi talimata uymamalı).
- **Geçti:** fixture'da sayfa durumuyla doğrulanan ≥9/10, injection 2/2 reddedilir. Ads okuma 5 görevde sayılar API/MCP geri okumasıyla birebir. Yazma yalnız ayrı test hesabında ya da senin onayınla PAUSED taslak + geri okuma.

---

## 5. Kabul ve ölçüm düzeni

1. **Sonuç sınıfları:** geçti / kaldı / **geçersiz** (ortam, hakem ya da öğretmen erişilemedi) / **öğretmen-destekli geçti**. İstatistiğe yalnız ilk ikisi girer; öğretmen müdahalesi (çağrı sayısı, yazdığı satır oranı) her koşuda kaydedilir.
2. **Ortam ön-kontrolü** (başarısızsa koşu başlamaz): NIM gecikmesi ve 429 oranı, Gemini oturumu ve captcha, eklenti bağlantısı, node/chromium/ffmpeg/php/godot sürümleri, disk, port 8765.
3. **Metrik kaydı:** araç çağrısı, prompt/çıktı token, süre, öğretmen çağrısı, yüklenen görsel, hata sınıfı (model / Fusion / ortam / hakem). Pay tahmini bununla ölçüme dönüşür.
4. **Mutant fixture'lar** her alanda; değerlendirici dosyaları ajana salt okunur.
5. **Regresyon seti:** ≤30 dk hızlı alt küme, her değişiklikten sonra; tam set gece, sıralı (40 RPM).
6. **Genelleme koşusu:** ikinci bir ücretsiz model (Super/GLM) ile aynı eval bir kez. Harness modele özel yama olmasın, NIM modeli kalkarsa plan çökmesin.
7. **Bağımsız hakem:** yedeğe düşmüş hakem bağımsız sayılmaz; hakem düşerse sonuç "geçersiz".

---

## 6. Yol haritası (her faz sonu: argümansız `mypy` + ruff + pytest + ilgili eval; skor düşerse geri al)

| Faz | İçerik | Süre (gerçekçi) |
|---|---|---|
| **0 — Zemin** | I0 iskeleti (6 alan × 1-2 görev, metrik, sonuç sınıfları, ön-kontrol); NIM parametre sondası; Nano-Omni görsel sondası; Remotion ortam sondası; mevcut kodla 18. koşu = baz (3-4 Eki commit'leri hiç ölçülmedi) | 2-3 gün |
| **1 — Ucuz kaldıraçlar** | I1, I2, I3, I5, I7, I4 (her biri ayrı ölçüm); I6 A/B ayrı | 4-6 gün |
| **2 — Klon dilimi + göz** | I8 küçük dilim → ölç → büyüt; I9; ikinci site | 1,5-2 hafta |
| **3 — Alan profilleri** | I10, animasyon / Remotion / HTML oyun eval'leri (3 alan × 5 koşu × ~60 dk ≈ 15 saat saf koşu, gece sıralı) | 2 hafta |
| **4 — Tarayıcı + MCP** | I12, fixture seti, ads okuma | 1-1,5 hafta |
| **5 — Kendini geliştirme** | I14 (giriş şartı sağlanınca), I13 | sürekli |

Her faza bir "yetim modül denetimi" satırı eklenir: yeni modül gerçekten çağrılıyor mu.

---

## 7. Yapılmaması gerekenler

1. Alan-özel dar kapı biriktirmek (Godot'ta 14+ kapı, otonom teslim yok; kullanıcı "genel olsun" dedi).
2. Çağrı/ilerleme sınırlarını tamamen kaldırmak (28-29 Eyl sonsuz döngü).
3. Her turda büyük skill/referans basmak (`loop.py:474-477`: yanlış sınıflanan turda 21 KB yanlış bağlam).
4. Model-inisiyatifli skill yüklemesine güvenmek (Hermes "Skills (mandatory)" → 0 çağrı; Fusion 0).
5. max_tokens'ı körü körüne büyütmek (16384 → 600 sn aşımı).
6. Barındırılan NIM'de `force_nonempty_content` (`litellm_provider.py:137-142`, 6/6 zararlı).
7. Yedeğe düşmüş ya da aynı model hakemi "bağımsız" saymak.
8. ChatGPT web'e arka arkaya otomatik oturum açmak (6 oturum → Cloudflare).
9. Tek koşuyla ya da birden çok değişikliği aynı anda ölçerek karar vermek.
10. Zayıf görme modeline açık uçlu "hataları listele" sormak.
11. Ajanın değerlendirici/kabul dosyalarına yazabilmesi (Ultra kabul testini düzenledi).
12. Başarısız/partial turdan ders çıkarmak.
13. Öğretmen devriyle gelen başarıyı Nemotron başarısı saymak.
14. Gerçek reklam hesabına onaysız yazmak; kullanıcı/müşteri ekranlarını Gemini web'e yüklemek.

---

## 8. Senin kararını bekleyen noktalar

1. **Öğretmen-destekli başarı** "Fusion geçti" sayılır mı? Öneri: ayrı sınıf, öğretmen müdahalesi ≤3.
2. **Alan önceliği:** sneaksup mı, reklam/tarayıcı işi mi, HTML görsel/oyun mu? Faz sırası buna göre değişebilir.
3. **"Birebir" eşiği:** hangi bölümler zorunlu, video/slider dahil mi?
4. **Animasyon referansı:** bir kerelik Claude ile 8 referans üretimi mi, yoksa senin seçeceğin siteler mi?
5. **Gizli test/altın set** kim yazar?
6. **Ads yazma testleri:** ayrı test hesabı var mı, yoksa yalnız okuma mı?
7. **Remotion lisansı** ve Chromium/ffmpeg indirmeleri uygun mu?
8. **Godot** kabulün parçası mı, yoksa yalnız HTML oyun mu?
9. **Kendini geliştirmede özerklik:** hangi dizinler, otomatik commit var mı?
10. **Haftalık koşu bütçesi** (saat).

---

## Kaynaklar

**İç:** `fusion-kabul/kabul17.jsonl` (160 araç, 169 model çağrısı, 17.622.189 prompt token), `~/.local/share/fusion-cli/memory/audit/cli.jsonl` (1.696 çağrı), `fusion-kabul/deneme-kopya/kopyala.py`, `fusion-kabul/codex17/`, `~/.hermes/state.db`, `docs/superpowers/reports/2026-10-03-site-kopya-kabul-sonuc.md`, `2026-09-24-long-task-acceptance.md`, `2026-09-29-ogretmen-cirak-asamalari-sonuc.md`, `2026-09-06-harness-arastirmasi.md`, `plans/2026-09-14-domain-adapter-v2.md`. Kurtarılan kayıp belgeler: önceki oturumun scratchpad'inde `master_doc_v1.md`, `devir_0925.md`.

**Dış:**
- huggingface.co/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16
- docs.api.nvidia.com/nim/reference/nvidia-nemotron-3-ultra-550b-a55b-infer (özetleyiciden geçti, canlı doğrulanacak)
- langchain.com/blog/tuning-the-harness-not-the-model-a-nemotron-3-ultra-playbook
- developer.nvidia.com/blog/create-a-langchain-deep-agents-harness-profile-for-nvidia-nemotron-3-ultra-to-improve-performance/
- coderabbit.ai/blog/nemotron-3-ultra-release
- anthropic.com/engineering/ (effective-harnesses-for-long-running-agents, harness-design-long-running-apps, advanced-tool-use, writing-tools-for-agents, building-effective-agents)
- huggingface.co/papers/2602.12670 (SkillsBench)
- arxiv.org/abs/2505.03275 (RAG-MCP)
- github.com/JCodesMore/ai-website-cloner-template
- remotion.dev/docs/ai/skills
- arxiv.org/abs/2602.11103 (GameDevBench)
- arxiv.org/abs/2604.19742 (PlayCoder)
- arxiv.org/abs/2507.04952 (ArtifactsBench)
- heygen.com/research/introducing-code2video-benchmark
- sakana.ai/dgm/
- arxiv.org/abs/2609.17817
- claude.com/blog/claude-for-chrome
- developers.google.com/google-ads/api/docs/developer-toolkit/mcp-server
