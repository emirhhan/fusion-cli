# Faz 4 — Öğretmen Protokolü: Uygulama Planı

> Bu doküman KOD YAZMADAN, yalnızca kod okunarak (keşif ajanı) hazırlanmıştır.
> `docs/superpowers/plans/2026-09-22-cirak-katmani.md` ile aynı biçimi izler;
> görev görev uygulanır. Önerilen beceri `superpowers:subagent-driven-development`.

**Kaynak:** 17 Eylül denetimi (`docs/superpowers/plans/2026-09-17-claude-paritesi.md`,
Faz 4 satırları 40-45, bulgular A3, A5, A6, A11, C7, C8). Mimari yön dokümanın
girişinde tanımlı: Öğretmen–Çırak — çırak = ücretsiz API modelleri (Faz 3'te
kuruldu), öğretmen = ChatGPT/Gemini **web** oturumları (plan, takılmada danışma,
son denetim; tur başına en fazla 4 çağrı).

**Dal:** `fusion-runtime-hardening-20260827-022831` (mevcut dal üzerinde devam),
push yok, commit kuralları CLAUDE.md'deki gibi geçerli.

---

## 1. Mevcut durum haritası (keşif ajanı, 22 Eylül)

### 1.1 "Öğretmen" kavramı kodda henüz İSİMLENDİRİLMEMİŞ

Bugün "zor kararda danışma" yolu `council` aracı (`engine_tools.py:207-240`,
`_council_tool`) — `run_fusion(..., task_type="reasoning", synthesis=True)`
çağırır, `CouncilConsulted` yayınlar. Açıklaması net: "zor kararlar için, basit
adımlarda kullanma." Ama bu **çoklu-model** bir yol, özellikle "web öğretmene
danış" değil.

Web sağlayıcı (ChatGPT/Gemini web) altyapısı `providers/web_*.py`'de zaten var
ve SAĞLAM: `web_browser.py` (2247 satır), `web_session.py`, `web_registry.py`,
`web_control.py`, `web_shared_browser.py`, `web_transport.py`, `web_markdown.py`.
Bugün bu altyapı yalnızca normal çırak model zincirinde BİR ADAY olarak
kullanılıyor (`chatgpt_web/...`, `gemini_web/...`) — "çırak takılınca öğretmene
danış" diye ayrı bir tetikleyici YOK. Alttaki mekanik (oturum havuzu, hız
ayarlama, kota/insan-doğrulama algılama) yeniden kullanılabilir durumda.

"Çırak"/"öğretmen" terminolojisi bugün yalnızca `apprentice` tarafında var
(`config/model_select.py:129-162` `APPRENTICE_TIER_NAME="low"`,
`providers/capabilities.py:84 apprentice_active`) — "öğretmen" karşılığı yok.

### 1.2 Dosya yükleme mekanizması YOK

`web_browser.py`/`web_control.py` içinde `upload`, `file_chooser`,
`set_input_files` için hiçbir eşleşme yok. Yol haritasındaki "74 bin karakter
8 sn, doğru cevap" ölçümü yalnızca DÜZYAZIDA geçiyor (plan dokümanı satır 9 +
`engines/effects/detect.py:186-188` yorumu) — bu bir YETENEK değil, 17 Eylül
denetiminin bir gözlemi, ve orada metin PROMPT'A YAPIŞTIRILMIŞ, dosya olarak
YÜKLENMEMİŞ. `web_browser.py:440-470`'teki `trim_to_prompt_budget` bugün
UZUN METNİ KIRPIYOR — Faz 4'ün istediğinin (kırpmak yerine yüklemek) tam tersi.
Bu görev SIFIRDAN yazılacak; Playwright sayfa-etkileşim desenleri
(`web_control.py`) yeniden kullanılabilir ama gerçek dosya yükleme (ChatGPT/
Gemini web arayüzünde `<input type=file>` bulup dosya vermek) CANLI TARAYICIDA
doğrulanmadan "çalışıyor" sayılamaz.

### 1.3 "Brief" derleyici YOK

Durum+kod+denenenler+tek-soru paketleyen bir modül yok. En yakın parçalar:
`engine_tools.py:567-627` (`read_session`, `READ_SESSION_CHAR_BUDGET=12_000`) —
karakter bütçeli sayfalama deseni, 25k karakter sınırına örnek olabilir ama
özetleyici değil. `web_browser.py:470-542` `format_browser_prompt` — geçmişi
tek promota birleştiriyor, en yeniden kullanılabilir iskele ama "ilgili kodu
seç" / "denenenleri listele" YAPMIYOR. Bu görev de büyük ölçüde SIFIRDAN.

### 1.4 `.fusion/` dizini YERLEŞİK bir kural

`tools/forge.py:28` (`.fusion/tools`), `tools/capabilities.py:229`
(`.fusion/skills`), `core/constants.py:126` (`.fusion` tarama dışı) — dizin
zaten var ve bu deseni izliyor. `.fusion/ogretmen.md` bu kurala UYUYOR. Ama
`.fusion/*.md` defter deseni YENİ — önce yoktu.

### 1.5 Mevcut ders sistemiyle ÇAKIŞMA RİSKİ

`memory/lessons.py` (`ChromaLessonMemory`, ChromaDB, `agent_lessons` koleksiyonu,
alaka eşiği + yazma kilidi) + `engines/agent/learning_steps.py` (tur-sonu ders
çıkarımı, `RECALL_LIMIT=6`) + `engine_tools.py:300-328` (`recall_lessons`,
model-tetikli) — bu ANLAMSAL ARAMA tabanlı, düz metin defter DEĞİL. Faz 4'ün
"`.fusion/ogretmen.md` ders defteri" istemi FARKLI bir şey: insan-okunur bir
öğretmen-oturumu günlüğü. **Karar gerekiyor** (bkz. §6.3): iki paralel "ders"
sistemi açılmasın diye öğretmen dersleri de `ChromaLessonMemory`'ye mi yazılsın,
yoksa `.fusion/ogretmen.md` sadece bir DENETİM GÜNLÜĞÜ mü kalsın?

### 1.6 Günlük çağrı bütçesi YOK

Var olan: tur/oturum ölçekli hız ayarlama — `web_browser.py` `ConversationPacer`
(~802) + `browser_turn_budget()` (1087) sağlayıcının kendi hız sınırına
çarpmamak için; `providers/key_rotation.py` anahtar rotasyonu (kalıcı sayaç
değil); `providers/circuit.py` devre kesici; `providers/retrying.py:11` günlük
kotayı KALICI hata sayıp yeniden denemiyor ama SAYMIYOR da. Yani proaktif
"bugün kaç öğretmen çağrısı yaptım" sayacı YOK — yeni, küçük bir durum dosyası
gerekiyor (`.fusion-leases` deseniyle tutarlı olabilir). Uygulama katmanı
(`circuit.py`, `retrying.py`, `key_rotation.py`) zaten var, yalnızca SAYAÇ eksik.

### 1.7 Kademe düşme bildirimi KISMEN var, KULLANICIYA GÖRÜNMÜYOR

`web_browser.py:1736-1753` `observed_tier()` sayfadan kademe etiketini
(ör. "Flash-Lite") okuyor. `web_browser.py:1241-1254` kademe değişince yalnız
LOG'a yazıyor. `web_session.py:110,179-216` → `ModelResult.served_by`
(`core/types.py:271`) → `ui/text.py:137-153` `format_served_model` CLI
satırında PASİF olarak gösteriyor (ör. `gemini_web/auto · Flash-Lite`).
"Beklenen kademeyle karşılaştır, düşerse UYAR" yok. `web_browser.py:1865-1868`
geçmişte bir kademe-değişim banner'ının turu yanlışlıkla düşürdüğünü belgeliyor
— yani kod BİLİNÇLİ olarak kademe değişimini hata saymıyor; Faz 4 aktif bir
karşılaştırma+bildirim eklemeli, mevcut `observed_tier`/`served_by` veri
kaynağını kullanarak.

---

## 2. Hedef akış (özet)

1. Çırak bir işte TAKILIRSA (araç hatası tekrarlanıyor / plan adımı
   ilerlemiyor / model kendisi belirsizlik bildiriyor) **brief derleyici**
   durumu + ilgili kodu + denenenleri + TEK soruyu ≤25k karaktere paketler.
2. Paket web öğretmene (ChatGPT/Gemini web) gönderilir; 25k'yı aşan ekler
   (uzun metin, ekran görüntüsü) KIRPILMAK yerine DOSYA olarak yüklenir, kırpma
   olursa kullanıcıya/loga bildirim düşer.
3. Öğretmenin cevabı turun geçmişine döner; oturum sonunda önemli bir ders
   çıkarsa `.fusion/ogretmen.md`'ye insan-okunur biçimde eklenir (bkz. §6.3
   kararı).
4. Kullanıcı öğretmensiz çalışmayı seçebilir (`teacherless kip`) — bu kipte
   council/öğretmen danışma araçları modele hiç SUNULMAZ.
5. Öğretmen turu gözlenen kademesi beklenenden düşükse (ör. Flash yerine
   Flash-Lite) kullanıcıya görünür bir bildirim çıkar; günlük çağrı sayacı
   dolduysa yeni öğretmen çağrısı YAPILMADAN önce kullanıcıya söylenir.

---

## Genel kısıtlar

- Model kimlikleri / eşik değerleri uydurulmaz; her sabit gerekçeyle konuşulur
  ve mümkünse CANLI ölçümle doğrulanır (Faz 3'teki disiplin aynen geçerli).
- Dosya yükleme özelliği **AĞ GEREKTİRİR**: gerçek bir tarayıcı oturumunda
  (Playwright, gerçek ChatGPT/Gemini web sayfası) dosya seçici bulunup
  doğrulanmadan "yapıldı" sayılmaz.
- Var olan `council` aracıyla ilişkisi netleştirilmeli (bkz. §6.1) — aynı işi
  yapan ikinci bir yol açılmasın (RULES "DRY").

## Görev bağımlılıkları ve paralellik

- **Görev 1** (brief derleyici) diğer her şeyin önkoşulu — önce biter.
- **Görev 2** (dosya yükleme) ve **Görev 4** (kademe bildirimi + günlük bütçe)
  Görev 1'den bağımsız, paralel yürütülebilir.
- **Görev 3** (ders defteri + görev defteri + öğretmensiz kip) Görev 1'in
  ürettiği "öğretmen turu" kavramına bağımlı, ondan sonra gelir.
- **Görev 5** tüm görevler bitince, gerçek koşuyla doğrular (Faz 3'teki Görev 5
  deseniyle aynı: ağ gerektiren/gerektirmeyen senaryolar ayrı işaretlenir).

---

### Görev 0: Başlangıç durumu (salt okuma)

- [ ] `ruff check . && mypy && pytest -q` çalıştır, sayıyı kaydet; kırmızıysa DUR.
- [ ] Kullanıcıya §6'daki açık kararları sor.

### Görev 1: Brief derleyici (A3, A5)

**Olası dosyalar:** yeni `engines/agent/teacher_brief.py` (ya da benzer),
`engine_tools.py`'ye yeni bir `ask_teacher` aracı (bkz. §6.1 kararına göre isim
değişebilir).

- [ ] Ne zaman tetiklenir: "takılma" sinyalinin kesin tanımı §6.2'de
      netleştirilmeli (araç hatası N kez tekrarlarsa mı, modelin kendisi mi
      karar verir, yoksa ikisi birden mi).
      `step_verification.py`/`reflexion` mekanizmasındaki mevcut "tekrar hata"
      sayaçları incelenip varsa ONLAR kullanılır — yeni bir sayaç icat edilmez.
- [ ] Paket biçimi: durum özeti (son N tur) + ilgili kod (dokunulan dosyalar,
      `read_file` geçmişinden) + denenenler listesi (başarısız araç çağrıları)
      + tek soru. `format_browser_prompt` (`web_browser.py:470-542`) taban
      alınır, genişletilir; `READ_SESSION_CHAR_BUDGET` deseniyle 25.000
      karakter SERT sınırı uygulanır, aşan kısım kırpılır+not düşülür.
- [ ] `council` aracıyla ilişki netleştirilir (§6.1): ya `_council_tool` bu
      brief'i üretecek şekilde GENİŞLETİLİR, ya da ayrı bir `ask_teacher` aracı
      açılır ve `council` yalnız çoklu-model (web dışı) senaryoda kalır. İKİSİ
      BİRDEN AÇILMAZ.
- [ ] Testler: sahte (fake) sağlayıcıyla brief içeriğinin doğru derlendiği,
      25k sınırının uygulandığı, sınır aşımında kırpma bildiriminin çıktığı.

### Görev 2: Dosya yükleme + kırpma bildirimi (A5, A6) — TAMAM (22 Eylül)

**Dosyalar:** `providers/web_browser.py`.

- [x] **(AĞ GEREKİR, canlı ölçüldü)** Gerçek Gemini web oturumunda (kullanıcının
      kendi hesabı) `Yükleme ve araçlar` → `Dosya yükleyin` yolu bulundu,
      105.032 karakterlik gerçek bir metin dosyası `set_input_files` ile
      yüklendi; modelin içeriği GERÇEKTEN okuduğu doğrulandı (benzersiz bir
      işaret dizisini cevabında birebir aktardı, `[cite: 1]` ile kaynak
      gösterdi). Seçiciler dil-bağımsız özniteliklere dayanır (`jslog` düğme
      kodu, `data-test-id`) — yalnızca TR arayüzde ölçüldü, başka dillerde
      AYNI kaldığı varsayılır ama doğrulanmadı.
      **ChatGPT'de DENENMEDİ**: headless Chrome'da bir bot-doğrulama sayfasında
      ("Bir dakika lütfen…") takıldı. Bu YENİ bir bulgu değil — kod zaten 17
      Eylül'den beri bunu belgeliyordu (`recommended_window_mode` alanı,
      "ChatGPT görünmez Chrome'da Cloudflare doğrulamasına takıldı, 7 turun
      7'si düştü"); bugünkü canlı deneme bunu yeniden doğruladı. Bu yüzden
      yükleme yalnız `definition.id == "gemini_web"` iken denenir.
- [x] `format_browser_prompt(..., trim=False)` ile karar `_send_turn`'e taşındı
      (yalnız o `page`'e erişebilir): 30k karakter tavanını aşan prompt önce
      `_prepare_prompt_for_composer` içinde yüklenmeye çalışılır, HERHANGİ bir
      adımda (seçici yok, tıklama zaman aşımı, ...) başarısız olursa MEVCUT
      `trim_to_prompt_budget`'a sessizce düşülür — yükleme turu ASLA düşürmez.
      Testler (`tests/test_teacher_upload.py`, 7 senaryo, sahte sayfa) bu
      geri-düşüşü ve mevcut kırpma testlerinin (`test_prompt_butcesi.py`)
      bozulmadığını kilitler.

**Yan not (şeffaflık için kayıtlı):** canlı ölçüm sırasında "dosya ekle"
düğmesini dil-bağımsız bulmaya çalışırken bir ara adımda kapsam fazla geniş
tutuldu ve sayfa genelindeki buton etiketleri (kenar çubuğundaki gerçek sohbet
başlıkları dahil) bir kerede okundu — içerik değil yalnız BAŞLIKLAR, ama
amaçlanmamış bir genişlik. Sonraki denemeler yalnızca composer'ın kendi
kapsayıcısına daraltıldı.

### Görev 3: Ders defteri + görev defteri + öğretmensiz kip (C7, C8) — TAMAM (22 Eylül)

**Dosyalar:** yeni `engines/agent/teacher_notebook.py`, `engines/agent/teacher_lessons.py`;
`config/models.py` (`RuntimeConfig.teacherless`, `.teacher_lesson_sync`),
`config/writer.py` (`write_runtime_flag`), `cli/app.py` (`fusion config
teacherless` / `teacher-lesson-sync`), `core/memory.py` (`LessonSource.TEACHER`).

- [x] §6.3: `.fusion/ogretmen.md` HER ZAMAN yazılır (insan-okunur günlük,
      modele geri beslenmez). Ayrıca `runtime.teacher_lesson_sync` (varsayılan
      AÇIK) ile `ChromaLessonMemory`'ye de yazılır — yeni `LessonSource.TEACHER`
      etiketiyle. Çakışma kontrolü: `memory.recall(question, limit=3)` (VAR OLAN
      sorgu, yeni bir arama motoru İCAT EDİLMEDİ) ile benzer dersler çekilir;
      tam biri olumsuzlama işareti taşıyıp diğeri taşımıyorsa (`değil, yapma,
      kullanma, etme, asla, sakın, olmaz, yanlış` — kaba ama belirsizlikte
      YAZAN bir sezgi) yazılmaz, `.fusion/ogretmen.md`'ye gerekçesiyle düşülür
      VE `ask_teacher`'ın döndürdüğü metne kullanıcıya görünür bir not eklenir
      (`fusion config teacher-lesson-sync false` ile kapatma yolu gösterilir).
- [x] §6.4 kararı uygulandı: ayrı bir "görev defteri" AÇILMADI (BACKLOG'da
      kaldı), `.fusion/ogretmen.md` yalnız öğretmen oturumlarının günlüğü.
- [x] `teacherless=true` iken `ask_teacher` `build_agent_registry`'de hiç
      kaydedilmez (`deps.config.teacher is not None and not
      deps.config.runtime.teacherless`); `council` bundan ETKİLENMEZ — ayrı
      test bunu kilitler (`test_teacherless_kapaliyken_council_etkilenmez`).
- [x] CLI: `fusion config teacherless true|false` ve `fusion config
      teacher-lesson-sync true|false`, `write_runtime_flag` üzerinden `runtime:`
      bölümüne kalıcılaşır (diğer ayarlar korunur — `write_theme` ile AYNI
      desen). **Düzeltme:** plandaki "Faz 3 Görev 2'deki RPC+CLI deseni"
      varsayımı YANLIŞ çıktı — o özelliğin yalnızca masaüstü RPC'si vardı,
      terminal CLI komutu hiç yoktu; bu görev o boşluğu da kapattı.

### Görev 4: Kademe düşme bildirimi + günlük çağrı bütçesi (A11)

**Olası dosyalar:** `providers/web_browser.py` (`observed_tier` çağrı yeri),
`ui/renderer.py`/`ui/text.py` (bildirim), yeni küçük bir sayaç modülü
(`.fusion-`  önekli dosya deseniyle, `web_shared_browser.py`'deki kira
dosyalarına benzer).

- [ ] "Beklenen kademe" nereden gelir: model kimliğinden mi (`/auto` sonekli
      olanlarda beklenmez, açık kademe seçilmişse ondan) çıkarılır? Karar
      §6.5'te netleşir.
- [ ] `observed_tier()` sonucu beklenenle KARŞILAŞTIRILIR; düşükse
      `TierDegraded` gibi yeni bir olay yayınlanır (mevcut `CouncilConsulted`
      desenindeki gibi), UI'da GÖRÜNÜR bir satır olarak basılır (yalnız log
      değil). `web_browser.py:1865-1868`'deki geçmiş hatadan ders çıkarılır:
      bu bildirim turu DÜŞÜRMEZ, yalnız BİLGİLENDİRİR.
- [ ] Günlük öğretmen-çağrı sayacı: **(AĞ GEREKMEZ, ama sabit gerekçelendirilir
      — bkz. §6.6)** `.fusion/` altında tarihe göre sıfırlanan küçük bir sayaç
      dosyası; sınıra ulaşınca yeni öğretmen çağrısı YAPILMADAN önce kullanıcıya
      söylenir (RULES "sabitler uydurulmaz" — günlük limit değeri kullanıcıya
      sorulacak, bkz. §6.6).

### Görev 5: Gerçek koşuyla doğrulama (tüm görevler bitince)

- [ ] Kalite kapısı: `ruff check . && mypy && pytest -q`.
- [ ] **(AĞ GEREKİR)** Gerçekten takılan bir görevde (ör. var olmayan bir API'yi
      çağırmaya çalışan bir görev) brief'in gerçekten öğretmene gittiği, gerçek
      bir cevap döndüğü, turun bundan yararlandığı uçtan uca doğrulanır.
      Gerçek dosya yükleme senaryosu (Görev 2) ayrıca doğrulanır.
      Kademe düşürme bildirimi gerçek bir "Flash-Lite'a düştü" anında (ya da
      taklit edilerek) gözlemlenir.
- [ ] **(AĞ GEREKMEZ)** `teacherless` kipte `ask_teacher`/`council` aracının
      GERÇEKTEN sunulmadığı sahte sağlayıcıyla doğrulanır. Günlük sayaç
      sınırına ulaşınca gerçek bir ağ çağrısı YAPILMADIĞI (sahte sağlayıcı
      hiç çağrılmadığı) doğrulanır.

---

## Genel kısıtlar (tekrar)

Faz 3'teki disiplin aynen geçerli: sabit uydurulmaz, faz yarım bırakılmaz,
kalite kapısından geçmemiş kod commit'lenmez, commit mesajında faz/görev
numarası geçmez.

---

## 6. Kararlar

### 6.1 `council` aracıyla ilişki — KARARLANDI: ayrı araç

`council` çoklu-API-model aracı olarak AYNEN kalır. Web öğretmene özel, YENİ
bir `ask_teacher` aracı açılır; brief derleyiciyi bu kullanır. İki farklı amaç
(çoklu-model oylama vs. web öğretmene tek-soru danışma) iki farklı araçta
netleşir — `council`'a dokunulmaz.

### 6.2 Tetikleme — KARARLANDI: ikisi birden

Brief derleyici HEM otomatik önerilir (aynı araç N kez art arda hata verirse
— N, mevcut `step_verification.py`/reflexion tekrar-sayaçları OKUNARAK
belirlenir, UYDURULMAZ) HEM modelin kendi inisiyatifiyle çağrılabilir
(council'daki gibi serbest çağrı). Otomatik öneri modeli ZORLAMAZ — yalnız
"öğretmene danışmayı düşün" notu enjekte eder, karar modelde kalır (RULES
"yönlendirme modele bırakılır" — Faz 2 Görev G4 ile aynı ilke).

### 6.3 Ders defteri — KARARLANDI: açılır/kapanır ChromaLessonMemory entegrasyonu

Öğretmen oturumundan çıkan önemli dersler VARSAYILAN olarak
`ChromaLessonMemory`'ye de yazılır (modelin `recall_lessons` ile geri
çağırabileceği), AMA bu entegrasyon config'te AÇIK/KAPALI bir anahtardır
(ör. `teacher.lesson_sync: true|false`, `providers/capabilities.py` ya da
`config/models.py`'de Faz 3'teki `apprentice_active` deseniyle aynı katmanda).

**Çakışma önleme:** yazmadan önce yeni öğretmen dersi, konu/anahtar kelime
örtüşmesi olan MEVCUT derslerle karşılaştırılır (mevcut `ChromaLessonMemory`
alaka-eşiği sorgusu yeniden kullanılır — yeni bir benzerlik motoru İCAT
EDİLMEZ). Doğrudan ÇELİŞEN bir ders bulunursa (ör. biri "X yap" biri "X
yapma" diyorsa) o ders YAZILMAZ, `.fusion/ogretmen.md`'ye "çakışma nedeniyle
atlandı" notuyla düşülür ve kullanıcıya kısa (iki cümlelik) bir açıklamayla
`teacher.lesson_sync`'i kapatma seçeneği sunulur (mevcut onay/bildirim
akışıyla aynı yerde, `ui/renderer.py`). Kapatılırsa sistem sessizce
`.fusion/ogretmen.md`-yalnız denetim-günlüğü kipine düşer — davranış BOZULMAZ,
yalnız ikinci depoya yazma durur.

### 6.4 Görev defteri — ÖNERİ (itiraz yoksa bu şekilde ilerlenir)

Mevcut `todo_write` görev yönetimiyle çakışmaması için Faz 4'te AYRI bir
"görev defteri" dosyası AÇILMAZ; `.fusion/ogretmen.md` yalnızca öğretmen
oturumlarının günlüğünü tutar, aktif görev listesi zaten var olan
`todo_write`/plan motorunda kalır. Yol haritasındaki "görev defteri" ifadesi
bu haliyle BACKLOG'a düşer (yeniden gerekirse ayrı, küçük bir görev olarak
açılır).

### 6.5 "Beklenen kademe" — ÖNERİ (itiraz yoksa bu şekilde ilerlenir)

Bildirim yalnızca kullanıcı AÇIKÇA bir kademe seçtiğinde (ör.
`gemini_web/pro`) anlamlı sayılır ve karşılaştırma o zaman yapılır. `/auto`
seçili modellerde "beklenen kademe" tanımsızdır — bildirim üretilmez (gürültü
olmasın diye).

### 6.6 Günlük öğretmen çağrı bütçesi — KARARLANDI: canlı ölçümle, ama GÜVENLİK NOTU var

Kullanıcı CAPTCHA/insan-doğrulama tetiklenme riskine göre canlı ölçüm istedi.
**Bu ölçüm kullanıcının GERÇEK ChatGPT/Gemini web hesabında** (ortak Chrome
profili, bkz. proje belleği) yapılacağından, CAPTCHA'yı KASITLI TETİKLEMEK
(ör. çok kısa aralıklarla art arda onlarca çağrı göndermek) hesabı geçici
kısıtlamaya/işaretlenmeye sokma riski taşır — bu geri alınamaz bir yan etkidir.
Kullanıcı KASITLI CAPTCHA testi yerine güvenli yolu seçti (22 Eylül): Görev
4'ün bütçe ölçümü şöyle yapılacak: (a) ÖNCE mevcut kodun insan-doğrulama
algılama/hız-ayarlama yorumlarında (bkz. §1.6, `ConversationPacer`,
`modal-conversation-history-rate-limit`) zaten belgelenmiş bir eşik/gözlem var
mı taranır, varsa O kullanılır ve gerekçesi alıntılanır; (b) belgelenmiş bir
eşik YOKSA, kasıtlı CAPTCHA tetikleme yapılmadan, saatte 25'in ÜSTÜNDE
(kullanıcının verdiği alt sınır) ihtiyatlı bir günlük/saatlik bütçe sabiti
kullanılır — kesin sayı bu görev sırasında koddaki gerçek turlar-arası
aralık/pacing sabitleriyle TUTARLI olacak şekilde seçilir (RULES "sabitler
uydurulmaz" — seçilen sayı mevcut `ConversationPacer` aralığıyla çarpılarak
gerekçelendirilir, boşluktan atılmaz).

---

### Kritik dosyalar (implementasyon için)

- `/Users/motogate/Desktop/01-Projeler/fusion-cli/src/fusion_cli/engines/agent/engine_tools.py`
- `/Users/motogate/Desktop/01-Projeler/fusion-cli/src/fusion_cli/providers/web_browser.py`
- `/Users/motogate/Desktop/01-Projeler/fusion-cli/src/fusion_cli/providers/web_control.py`
- `/Users/motogate/Desktop/01-Projeler/fusion-cli/src/fusion_cli/memory/lessons.py`
- `/Users/motogate/Desktop/01-Projeler/fusion-cli/src/fusion_cli/engines/agent/learning_steps.py`
- `/Users/motogate/Desktop/01-Projeler/fusion-cli/src/fusion_cli/config/model_select.py`
- `/Users/motogate/Desktop/01-Projeler/fusion-cli/src/fusion_cli/ui/text.py`
