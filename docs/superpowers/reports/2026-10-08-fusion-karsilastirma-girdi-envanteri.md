# Fusion karşılaştırma girdi envanteri

Bu belge [kontrollü karşılaştırma sözleşmesinin](2026-10-08-fusion-kontrollu-karsilastirma-sozlesmesi.md) yürütme hazırlığıdır. Üretim veya %90 gelişim kanıtı değildir. Taslak briefler henüz dondurulmadı; eski çıktılara yeni rubrik uygulanmaz.

## Mevcut kaynaklar; henüz koşu girdisi olarak dondurulmadı

Özgün kirli tabanın kesin motor revizyonu bilinmiyor. Açık referansın tam SHA’sı `3fd76ae292bbcbe5c21bc41b73f17c43908a184f`; özgün taban olduğu iddia edilmez. Güncel motor ve denetim SHA’ları bütün hazırlık tamamlanınca ayrı ayrı kaydedilecek. Bu belgenin hazırlanması sırasında gözlenen HEAD gelecekteki koşuyu otomatik sabitlemez.

| Alan | A metninin kesin kaynak dosyası/alanı | Mevcut üretim süresi | Eksik hazırlık |
|---|---|---:|---|
| Oyun | `evals/kabul/areas/html_game.py`, `TASK` | 3600 sn | Dalga başlangıç/bitiş kuralı, süre ve düşman üst sınırı eki; exact nihai metin/hash |
| Remotion | `evals/kabul/areas/remotion.py`, `TASK` | 5400 sn | Beş kaynak girdinin eksiksiz kopyası/hash; bağımsız render ve bütün sahne/final kare takvimi |
| Site A | `evals/kabul/areas/site_clone.py`, `TASK_TEMPLATE`, `SOURCE_URL=https://www.sneaksup.com` | 5400 sn | Aynı kaynak içerik/görselleri; mobil ve renkli karşılaştırma paketi |
| Animasyon | `evals/kabul/areas/animation.py`, `TASK` | 3600 sn | Exact metin/hash; mobil, etkileşim ve reduced-motion kanıt takvimi |
| Site B | `evals/kabul/areas/site_clone_second.py`, `SOURCE_URL=https://www.desa.com.tr`; ortak `TASK_TEMPLATE` | 5400 sn | Ayrı kaynak snapshotı ve aynı alışveriş kontrolleri |

A için yeniden özet yazmak yerine kaynak `TASK` UTF-8 byte metni, varsa önceden sabitlenen ek ve bunların SHA-256’sı tutulur. Site A/B için template doldurulduktan sonraki gerçek metin hashlenir. Oyun mevcut metni süre/nesne sınırlarını sayısal olarak belirtmiyor. Gerekçeli sayılar hazır olmadığı için bu belge yeni cap veya süre uydurmaz; ilk üretimden önce tamamlanması zorunludur.

Remotion hazırlığı `fusion-tanitim/` içine `logo.png`, `logo.svg`, `YETENEKLER.md`, `README.md`, `KITS.md` kopyalar. Kaynakları sırasıyla `app/src-tauri/icons/icon.png`, `app/public/fusion.svg`, `docs/YETENEKLER.md`, repo `README.md` ve kardeş `fusion-kits/README.md` dosyalarıdır. Mevcut `prepare` eksik dosyayı atlar; kontrollü karşılaştırmada beşinin de mevcut ve aynı hashli olduğu doğrulanmadan koşu hazır değildir. İki motora aynı belgeler verilir; güncel motor kit/becerileri referans motorun kaynak paketine enjekte edilmez.

## B brief taslakları

Aşağıdaki metinler yalnız kullanıcı hedeflerinden türetilmiş aktarım taslaklarıdır. Önceki çıktıların kusurlarına göre puan/rubrik eklemez. Nihai metin ve varlık listesi üretimden önce dondurulmalıdır.

**Oyun B taslağı:**

> Masaüstü tarayıcıda çalışan, yan görünüşlü bir platform oyunu üret. Tek klasörde `index.html` ve yerel CSS/JS/görsellerle, dosyaya çift tıklanarak da açılsın. Başla düğmesi oyunu gerçekten başlatsın. Üç ayrı bölüm sırayla oynansın; ilk bölüm atlanmasın. Oyuncu yön tuşlarıyla hareket edip boşlukla zıplasın; toplanabilir nesneler, tehlikeler, bölüm kapısı ve giderek artan zorluk bulunsun. Kapı, bölümün önceden belirlenmiş tamamlanma şartı sağlanmadan sonraki bölüme geçirmesin. Skor/can ve bölüm göstergesi okunur olsun; menü ve HUD oyun alanını örtmesin. Kaybetme ekranı ve düğme veya R ile tam yeniden başlatma çalışsın; bölüm, oyuncu ve geçici nesne durumu sıfırlansın. Tutarlı yerel sprite’lar üretip gerçekten kullan. Normal oynanışta konsol hatası, donma veya yatay taşma olmasın. Nihai brief ekinde bölüm tamamlanma şartları, nesne/tehlike sınırları ve görsel listesi üretimden önce sabitlenecek.

**Remotion B taslağı:**

> Remotion ile 30 saniyelik, 1920×1080, 30 fps bir ürün lansman videosu üret ve `out/video.mp4` olarak gerçek render al. Başlangıç girdisi paketindeki ürün metinleri, logo ve görselleri oku; doğrulanmayan ürün özelliği uydurma. Anlatı problem, ürünün özellikleri, kullanım örneği ve çağrı/kapanış sahneleri sırasını izlesin. Sahne metinleri ve ürün özellikleri nihai girdi paketinde önceden listelenecek. Tipografi, hiyerarşi ve geçişler tutarlı, metinler okunur olsun; anlamlı içerik taşmasın veya çakışmasın, sahne ve final boş kalmasın. Hareketi Remotion’un kare tabanlı API’leriyle kur. Strict TypeScript denetimi ve gerçek render başarılı olmadan teslimi tamamlandı sayma.

Ürün adı, iddiaları, sahne metinleri ve varlıkları eksik olduğu için bu taslak doğrudan koşuya açılamaz. Bunlar kullanıcı hedefini değiştirmeyen ayrı girdi paketinde tamamlanır.

**Animasyon B taslağı:**

> Bir etkinlik/program arayüzü için animasyonlu tek sayfalık web arayüzü üret. Çalışma klasöründe `index.html` ve gerekiyorsa yerel CSS/JS/görseller bulunsun. Program kartları kategori filtresiyle düzen değiştirsin; kart seçimi detay açsın, kapatma çalışsın. Hover geri bildirimi, kaydırmayla görünür olan bölümler ve amaca uygun easing/hareket bulunsun. Metinler okunur, görsel hiyerarşi ve renkler tutarlı olsun. Masaüstü ve mobilde içerik/kontroller erişilebilir kalsın; yatay taşma veya konsol hatası oluşmasın. `prefers-reduced-motion` seçildiğinde gereksiz hareketi azaltırken filtre, detay ve içerik çalışmaya devam etsin. Etkinlik adı, program metinleri, kategoriler ve varlık listesi nihai brief paketinde üretimden önce sabitlenecek.

Site B’nin tam metni mevcut template ve Desa URL’sinden üretilebilir; kaynak erişimi ve snapshot eşitliği ayrıca doğrulanmalıdır.

## Yapılandırma ve bellek eşitliği

Mevcut `fusion-kabul/taban-config.yaml` dosyası yalnız sır içermeyen alan allowlist’i ile incelendi. Açık agent modeli `nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b`; öğretmen rolü açıkça tanımlı değil. `judge`, `candidates`, `web_sessions`, `mcp_servers` ve `task_model_map` alanları mevcut; bunların ham değerleri bu belgeye taşınmaz. Açık runtime harcamaları `workflow_step_calls=40`, `workflow_recovery_calls=20`, `workflow_final_verification_calls=4`; ayrıca `workflow_max_model_calls` alanı mevcut fakat değeri bu envanterde sabitlenmedi.

Efektif değerler YAML dosyasının tek başına hash’iyle kanıtlanamaz. Her motorun `config/defaults.yaml`, loader ve rol seçimi aynı allowlisted çözülmüş özeti üretmelidir: agent/judge/öğretmen kimlikleri, strict/tags, sıralı fallback, context ve çıktı token sınırları, request timeout, retry ve bekleme politikası, model/araç/workflow bütçeleri, takeover ve öğretmenless davranışı. Küçük LLM için ayarlanmış parametreler bu hazırlık nedeniyle değiştirilmez. İki revizyon aynı yapılandırmayı çözemiyorsa eşitlik sağlanmış sayılmaz. `.env`, authentication vault, token, cookie, session URL/query ve tüm ortam dökümü okunmaz veya manifestte saklanmaz.

Her koşuya ayrı boş `FUSION_MEMORY_DIR` verilir. Bu, bellek ile CLI session’ın bu kök altındaki workflow-checkpoint/artifact kayıtlarını ayırır. Tek başına tüm küresel öğrenim/cache etkisini ayırdığı iddia edilmez: `CapabilityRegistry(home, root)`, kullanıcı veri kökü, öğretmen plan/oturum/cache yolu ve kurulmuş ek beceriler ayrıca kontrol edilmelidir. Yeni çalışma dizinindeki öğretmen günlüğü de boş başlar. Authentication kopyalanarak veya kullanıcının uygulaması kapatılarak izolasyon sağlanmaz. Üretime etkili küresel durum eşit veya etkisiz olduğu kanıtlanmadan karşılaştırma başlamaz.

## Denetim ve kaynak snapshotı

Mevcut bağımsız tarayıcı yardımcısı oyun/animasyon için 1280×800 kullanır; site denetçisi 1440×900 kullanır. Sözleşmenin 390×844 mobil denetimi, renkli aynı-viewport kareler, reduced-motion ve gerçek etkileşim paketleri ayrıca sabitlenir. Remotion için çözünürlük/FPS/süre, strict tsc, gerçek render, bütün sahneler ve final saniyelerinin kare zamanları aynı dış denetim sürümünde dondurulur. Dosya/hash veya drawImage kaydı görsel kalite kanıtı değildir.

Mevcut site denetçisi canlı kaynağı yeniden alır. Aynı URL, aynı kaynak girdisi demek değildir. Üretim öncesi kaynak sayfa/görsel snapshotı ve karşılaştırma referansı sabitlenmeli; üreticinin hangi snapshotı kullandığı da kanıtlanmalıdır. Yalnız hakem karelerini sabitlemek üretim girdisini sabitlemez. Canlı kaynak değişirse karşılaştırmanın eş koşullu olduğu ileri sürülmez; değişiklik kanıtı ayrı geçerlilik kararıyla raporlanır. Tarihî kaynak/engine kimliği eksik site çıktıları bu matrise sonradan eklenmez.

## Uygulanabilir manifest taslağı

Tek ortak header ve aşağıdaki 12 ayrı kayıt yeterlidir:

| Alan | Referans A | Güncel A | Güncel B |
|---|---|---|---|
| Oyun | `game.refA` | `game.curA` | `game.curB` |
| Remotion | `remotion.refA` | `remotion.curA` | `remotion.curB` |
| Site | `site.refA` | `site.curA` | `site.curB` |
| Animasyon | `animation.refA` | `animation.curA` | `animation.curB` |

Header: sözleşme/hash; açık referans tam SHA; güncel motor tam SHA; sabit denetim SHA/tree hash; allowlisted efektif config/hash; bağımlılık/browser/renderer sürümleri; `parallel=1`, `repeat=1`; aynı dış kabul ve önceden sabit profesyonellik rubriği. Referans A ile güncel A’nın brief ve başlangıç girdileri byte/hash eşit olur; B bunlardan ayrı üretimdir.

Her kayıt: run kimliği, alan ve A/B; seçilmiş motor kaynak yolu ve gözlenen `fusion_cli.__file__`; tam brief yolu/hash; alanın mevcut süre bütçesi; ayrı boş çalışma/bellek kökü ve cache başlangıç kanıtı; kaynak varlık/hash listesi; viewport/FPS/reduced-motion/etkileşim-kare takvimi; başlangıç/bitiş/uyku/kesinti kayıtları; çıktı ve bağımsız denetim kanıt yolları; geçerlilik ve kritik işlev kapısı sonucu. Sır içeren ham config veya ortam konmaz.

Motor seçimi için güncel `evals` sabit kaynak paketinden koşulur; alt çekirdek süreci `PYTHONPATH=<seçilmiş-motor>/src:<sabit-evals-kökü>` ve boş çalışma köküyle açılabilir. Bu yalnız yürütme taslağıdır: import edilen motor yolu gerçekten doğrulanmalıdır. Editable kurulumun veya güncel `fusion` executable yolunun referansı seçtiği varsayılmaz. Ön-kontrol model çağrısı da seçilmiş motorla yapılır; aksi halde preflight farklı motoru sınamış olur.

Mevcut kabul CLI’sinde B brief parametresi ve per-run bellek seçimi yok. İleride küçük manifest adapterı sabit `Area(task=B)` ile aynı `run_job`, preparer ve inspector zincirini kullanabilir; denetim kaynakları ve Remotion girdileri ayrı sabit pakette bulunmalıdır. Bu belgede adapter yazılmadı veya koşu başlatılmadı.

Ön-kontrolün mevcut **5 GB** boş disk sınırı düşürülmez veya atlanmaz. Ağır koşular seri yürür; WindowServer60% sınırında yeni görsel yük başlatılmaz. Sağlayıcı/denetçi arızası ve uyku, kanıtlı geçerlilik sorunları olarak ayrılır; normal bütçedeki eksik üretim veya gerçek ürün kusuru geçersiz diye gizlenmez.

Bu hazırlık tamamlandıktan sonra bile tek A çifti yalnız o brief/denemeyi, tek B yalnız örnek aktarımı gösterir. Sözleşmedeki %90 göreli hesap, referans0 için tanımsızlık ve referans55+ için endeksin matematiksel tavanı korunur; mutlak90 veya kusur azalması kullanıcı hedefinin yerine konmaz.
