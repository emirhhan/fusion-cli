# Fusion karşılaştırma girdi envanteri

Bu belge [kontrollü karşılaştırma sözleşmesinin](2026-10-08-fusion-kontrollu-karsilastirma-sozlesmesi.md) yürütme hazırlığıdır. Üretim veya %90 gelişim kanıtı değildir. Gelecek koşuların A byte metinleri ve nihai B briefleri public girdi paketine kaydedildi; eski çıktılara yeni rubrik uygulanmaz. Paket eş koşullu üretime hazır değildir.

## Byte olarak sabitlenen kaynaklar ve kalan kanıtlar

Özgün kirli tabanın kesin motor revizyonu bilinmiyor. Açık referansın tam SHA’sı `3fd76ae292bbcbe5c21bc41b73f17c43908a184f`; özgün taban olduğu iddia edilmez. Güncel motor ve denetim SHA’ları bütün hazırlık tamamlanınca ayrı ayrı kaydedilecek. Bu belgenin hazırlanması sırasında gözlenen HEAD gelecekteki koşuyu otomatik sabitlemez.

| Alan | A metninin kesin kaynak dosyası/alanı | Mevcut üretim süresi | Eksik hazırlık |
|---|---|---:|---|
| Oyun | `evals/kabul/areas/html_game.py`, `TASK` | 3600 sn | A exact metin/hash hazır; A bölüm kuralları sayısal cap içermiyor, bu durum değiştirilmedi |
| Remotion | `evals/kabul/areas/remotion.py`, `TASK` | 5400 sn | Beş kaynak girdinin eksiksiz kopyası/hash; bağımsız render ve bütün sahne/final kare takvimi |
| Site A | `evals/kabul/areas/site_clone.py`, `TASK_TEMPLATE`, `SOURCE_URL=https://www.sneaksup.com` | 5400 sn | Aynı kaynak içerik/görselleri; mobil ve renkli karşılaştırma paketi |
| Animasyon | `evals/kabul/areas/animation.py`, `TASK` | 3600 sn | A/B exact metin/hash hazır; mobil, etkileşim ve reduced-motion denetimi eksik |
| Site B | `evals/kabul/areas/site_clone_second.py`, `SOURCE_URL=https://www.desa.com.tr`; ortak `TASK_TEMPLATE` | 5400 sn | Ayrı kaynak snapshotı ve aynı alışveriş kontrolleri |

A için yeniden özet yazmak yerine kaynak `TASK` UTF-8 byte metni, varsa önceden sabitlenen ek ve bunların SHA-256’sı tutulur. Site A/B için template doldurulduktan sonraki gerçek metin hashlenir. Oyun mevcut metni süre/nesne sınırlarını sayısal olarak belirtmiyor. Gerekçeli sayılar hazır olmadığı için bu belge yeni cap veya süre uydurmaz; sayısal cap eklenerek A sonradan değiştirilmez. Bölüm sırası/oynanabilirlik bağımsız işlev kapısıdır; aynı özgün brief iki motora da verilir.

Remotion hazırlığı `fusion-tanitim/` içine `logo.png`, `logo.svg`, `YETENEKLER.md`, `README.md`, `KITS.md` kopyalar. Kaynakları sırasıyla `app/src-tauri/icons/icon.png`, `app/public/fusion.svg`, `docs/YETENEKLER.md`, repo `README.md` ve kardeş `fusion-kits/README.md` dosyalarıdır. Mevcut `prepare` eksik dosyayı atlar; kontrollü karşılaştırmada beşinin de mevcut ve aynı hashli olduğu doğrulanmadan koşu hazır değildir. İki motora aynı belgeler verilir; güncel motor kit/becerileri referans motorun kaynak paketine enjekte edilmez.

## Nihai gelecek B briefleri

Tam metinler [brief eklerinde](2026-10-08-fusion-brief-ekleri.md) bulunur. Oyun B platform türündedir; anahtar/kapı tamamlanma kuralı açıktır, yeni nesne sayısı/süre cap'i uydurulmaz. Remotion B aynı beş gerçek belge/logo girdisini kullanarak yeni kullanım-yolculuğu anlatısı kurar; iddialar belgelere dayanır. Animasyon B kurgusal Atölye Günü'nün sabit üç kartını, filtre/detay/klavye/odak kontrollerini içerir. Site B ortak template'in Desa URL'siyle doldurulmuş byte metnidir.

İşlev kontrol noktaları sonuç görülmeden brief ekiyle kaydedildi. **Arena/nişancı inspector'ı platform B'yi doğrulamaz.** B platformun anahtar, kilitli/açık kapı, bölüm sırası, kazanma/kaybetme ve reset bağımsız denetimi gerekir. Animasyonun filtre/detay/odak kontrolü de salt hareket sayımıyla doğrulanamaz. Bunlar hazır olmadan `functional_B_inspectors` kapısı açılmaz. Yeni puan/rubrik geçmiş çıktılardan türetilmez.

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

Seçilmiş motor bootstrap/import proof ve çözülmüş config receipt zinciri artık uygulanmıştır; kabul runner ve seçilmiş model önkontrolü bu seçenekleri taşır. Bu altyapı tek başına iki motorun eşitliğini kanıtlamaz. Eski yürütme taslağı: alt çekirdek süreci `PYTHONPATH=<seçilmiş-motor>/src:<sabit-evals-kökü>` ve boş çalışma köküyle açılabilir. Bu yalnız yürütme taslağıdır: import edilen motor yolu gerçekten doğrulanmalıdır. Editable kurulumun veya güncel `fusion` executable yolunun referansı seçtiği varsayılmaz. Ön-kontrol model çağrısı da seçilmiş motorla yapılır; aksi halde preflight farklı motoru sınamış olur.

Saf `run_manifest` eksikleri kapalı tutar; public input package byte girdileri yazıldı. Kabul CLI’sinde tam B/manifest/per-run bellek yürütme adapterı henüz yok. İleride küçük manifest adapterı sabit `Area(task=B)` ile aynı `run_job`, preparer ve inspector zincirini kullanabilir; denetim kaynakları ve Remotion girdileri ayrı sabit pakette bulunmalıdır. Bu belgede adapter yazılmadı veya koşu başlatılmadı.

Ön-kontrolün mevcut **5 GB** boş disk sınırı düşürülmez veya atlanmaz. Ağır koşular seri yürür; WindowServer60% sınırında yeni görsel yük başlatılmaz. Sağlayıcı/denetçi arızası ve uyku, kanıtlı geçerlilik sorunları olarak ayrılır; normal bütçedeki eksik üretim veya gerçek ürün kusuru geçersiz diye gizlenmez.

Bu hazırlık tamamlandıktan sonra bile tek A çifti yalnız o brief/denemeyi, tek B yalnız örnek aktarımı gösterir. Sözleşmedeki %90 göreli hesap, referans0 için tanımsızlık ve referans55+ için endeksin matematiksel tavanı korunur; mutlak90 veya kusur azalması kullanıcı hedefinin yerine konmaz.

## Gerçek public paket kaydı

Yeni paket: `/Users/motogate/Desktop/all/01-Projeler/fusion-kabul/comparison-inputs/frozen-2026-10-08/`.
Manifest SHA-256: `78185f38428260afc23ab7d9909f4a4125688e0c1be3a47a4d7859bff5b2cbee`.
`briefs/` sekiz A/B UTF-8 dosyasını, `sourceassets/fusion-tanitim/` beş eksiksiz gerçek girdi dosyasını; `sources/` A kaynak modüllerini, brief ekini ve karşılaştırma sözleşmesini içerir. Her dosyanın exact byte boyutu/SHA-256'sı `manifest.json` içindedir. A TASK metinleri modül import/execute edilmeden AST literalinden çıkarıldı; site metni yalnız mevcut literal template ile dolduruldu. B bütçeleri ilgili A'nın özgün alan bütçesidir. Üretim, reference kit enjeksiyonu veya sağlayıcı çağrısı yapılmadı.

Paket `unverified`, 12 koşunun tamamı `runnable=false`. Hazır brief/assets ile eksik eş koşul kanıtları ayrıdır: current/reference seçilmiş source manifestleri, efektif config eşitliği, authentication etkisi, cache başlangıcı, bellek izolasyonu, dinamik context etkisi, üretim kaynak snapshotı, sabit inspection/rubric/dependency sürümleri ve görev türüne uygun B denetçileri eksiktir. Paket içindeki rubrik belgesinin hash'i, dış denetim snapshotının dondurulduğu anlamına gelmez. Özgün kirli baseline provenance bilinmiyor; explicit reference yine özgün taban diye sunulmaz.

Tekrar üretme yolu: `evals.kabul.input_package.materialize_package(PublicSources(...explicit public allowlist...), yeni_hedef, briefs, assets)`. A kaynağı `extract_task` ile çözülür; annex'teki literal B metinleri byte olarak verilir; helper mevcut hedefe yazmayı reddeder. Gerçek kaynak dosyaları değişirse yeni klasör/manifest gerekir. Model/loader/config/env/cache okunmaz. Bu teslim hazırlığı, ürün kalitesi veya %90 gelişim sonucu değildir.
