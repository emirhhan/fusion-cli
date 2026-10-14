# Chat görevi — Paket 10: gorsel-uretim-ve-akislar

Bu chat yalnız aşağıdaki paketi uygulasın. Önceki paketlerin tamamlanmış commitlerini koru. Yeni branch/push/merge yapma; kullanıcı değişikliklerini geri alma. `.env`, cookie veya sır okuma. Repo `/Users/motogate/Desktop/all/01-Projeler/fusion-cli`; Kits gereken paketlerde `/Users/motogate/Desktop/all/01-Projeler/fusion-kits`. Önce CLAUDE.md/RULES.md, bu dosya ve belirtilen ilgili kaynakları oku. Gerçek davranışı incele; iyi mevcut alternatifleri yeniden yazma. Yapılmamış testleri geçmiş sayma. Varsayılan modelleri/bütçeleri tahminle değiştirme.

Tek yürütücüyle ilerle; tüm sohbet geçmişini yeni ajanlara taşıma. Yalnız ilgili kapsam için kısa uzman incelemesi yap. Doğrudan mevcut `.venv/bin/python`, App Node22 `/opt/homebrew/opt/node@22/bin`, Kits Node24 `/Users/motogate/.npm/_npx/538786c08bcb9442/node_modules/node/bin` kullan. `uv run`, toplu bağımlılık sync/update veya rastgele `npx` kurulumu yapma. Yeni bağımlılık gerekiyorsa gerekçesini açıkla. Ağır tam pytest ve `evals.kabul` aynı anda koşmasın; tam App/Kits kapıları da yük kaynaklı süre hatalarını azaltmak için sırayla koşsun. Önce anlamlı hedefli regresyon, sonra son stabil kaynak için gerekli kapı; değişmeyen kaynak için aynı kapıyı tekrar etme. Başarısız koşuları gizleme, eşiği/assertion'ı gevşetme.

Her paketin sonunda Türkçe, küçük yerel commit; gerçek değişiklik/test/atlanan kabul/kalan risk/sonraki interface raporu. Kullanıcı daha sonra adım adım push yapacak. Paket bitince sonraki pakete kendiliğinden geçme.

Kaynak plan: `/Users/motogate/Desktop/all/01-Projeler/fusion-cli/docs/superpowers/plans/2026-10-12-fusion-profesyonel-uygulama.md` içindeki Paket 10 ve Global Constraints.

## Paket şartnamesi

# Paket 10 uygulama şartnamesi

Önceki paket tamamlanıp root tarafından yetki verilmeden ürün edit yok. Kaynak otoritesi task-10-blueprint.md; ana plan Global Constraints ve aşağıdaki bölüm; araştırma raporundaki ilgili kabul sözleşmeleri. Önceki paket raporlarında değişen interface ve deferred bulguları oku.

## Sahiplik ve çalışma sınırı

Blueprint ve aşağıdaki kapsamın dosya/interface sahipliği bu işçiye aittir. Başka ajanlarla aynı repo: onların değişikliklerini geri alma. CLAUDE.md/RULES.md; mevcut branch; Türkçe metinler, typed contracts ve mevcut engine/store otoritesi. Sır/.env okuma, branch/push/merge/commit yok. Root fullgate/commit/review sahibi. .venv doğrudan Python; App Node22; Kits cached Node24.21.0. uv run veya paket yöneticisi sync/install/update yok; gerçekten yeni bağımlılık gerekiyorsa önce gerekçeyi roota bildir. Kendi reviewer/subagent spawn etme.

## Paket 10 — Görsel üretim iş protokolü

**Kapsam:** K27–K35, R26/R27/R29. **Dosyalar:** appserver/image_create/image_flows, providers/image_generation/web_image/nim_image, ImageCreate/akis/akisCalistir/AkisTuvali.

**Önerilen interface:** `ImageJobReceipt {jobId:string; state:'queued'|'running'|'partial'|'completed'|'failed'|'cancelled'; assetIds:string[]; error:string|null}`. Gerçek dosya teslimi current image core üzerinden; yeni provider implementasyonu gerekmez. RPC jobId/cancel existing tools/jobs ile eşdeğer ise onu kullan. Cancellation external provider'ı durduramıyorsa kesin “uzak iş iptal edildi” iddiası yok; sonraki varyasyonun başlaması engellenir.

- [ ] A28–A31: initial load error, DAG duplicate/cycle/NaN, atomic save interruption, exact_size unknown, cancel after first image, MIME fake/login HTML, missing target.
- [ ] Fail test; server-side DAG validation ve atomic flow persistence; progress/cancel task ownership, partial results retain.
- [ ] Basit üretim ve advanced flow; provider capability'ye göre oran/referans/seed. Hedef asset görünür; asset yoksa iş durur.
- [ ] Viewer focus trap/return; gallery partial badge; missing variant retry yalnız eksik varyasyona. Test/unit/full gates.
- [ ] Mevcut bağlı sağlayıcıyla dar gerçek generate/edit smoke; dosya açılır, dimensions/alpha ve referans gözle kıyaslanır. Model metni dosya kanıtı değildir.


## Teslim

Meaningful TDD RED→GREEN ve hedefli testler: import eksikliği davranış kanıtı değildir, assertion gevşetme/sleep uzatma yok. Mevcut doğru davranışı ölçüp kaydet, yeniden yazma. Beklenmedik failure kök nedenini teşhis et. Rapora exact changed files, commands/results, API/data migration contracts, remaining real/native acceptance ve deferred bulgular yaz. Rapor: task-10-report.md. Full pytest ve evals.kabul root tarafından sıralı; ağır/live koşuyu işçi açmaz. Root yetkili canlı kabul alt görevi ancak ayrı açık mesajla yürür.

## Ayrıntılı kaynak taslağı

`/Users/motogate/Desktop/all/01-Projeler/fusion-cli/docs/superpowers/handoffs/2026-10-13-fusion-paket4-sonrasi/taslaklar/paket-10-kaynak-taslagi.md`. Bu dosya devir paketinde mevcuttur. Bu taslak ilk hazırlık durumudur; önceki paketlerin yeni kod/interface/testleriyle tekrar karşılaştır.

## Tarihsel hazırlık raporu

# Paket 10 — Sınırlı RED hazırlık raporu

Durum: yalnız yeni test hazırlığı tamamlandı; ürün uygulaması başlamadı. P9 tamamlanması ve root'un açık ürün yetkisi bekleniyor. Bu rapor GREEN veya paket kabulü değildir.

## Yeni dosyalar

- `tests/test_task10_flow_validation_redprep.py`
- `tests/test_task10_image_payload_redprep.py`
- `.superpowers/sdd/2026-10-12-fusion-profesyonel-uygulama/task-10-report.md`

Mevcut ürün, eski testler, P3 ImageCreate dosyaları, P2 donmuş kaynakları ve diğer işçilerin dosyaları değiştirilmedi. Branch/commit/push yok; sır veya `.env` okunmadı. Yeni bağımlılık yok.

## Komutlar ve gözlenen sonuçlar

Repo kökünde:

```text
.venv/bin/python -m pytest --noconftest -q tests/test_task10_flow_validation_redprep.py tests/test_task10_image_payload_redprep.py
```

Çıkış 1, 10 örnek: 3 PASS, 7 FAIL. Import/toplama başarısızlığı yok. Gerçek public `validate_flow` ve `save_images` çağrıldı; tarayıcı/sağlayıcı/HTTP/üretim işlevleri çağrılmadı. Test I/O yalnız `tmp_path`; PNG örneği standart kitaplık ile yerel üretildi.

Davranış RED kanıtı: duplicate raw node ID kabulü; girişsiz bağlantısız bileşendeki iki düğümlü cycle kabulü; NaN/+Infinity/-Infinity koordinat kabulü; dört PNG prefix baytından sonra login HTML içeren bozuk dosyanın galerilik PNG diye yazılması; geçerli 1×1 PNG için DOM'dan gelen 1024×768 iddiasının gerçek ölçü yerine kullanılması.

GREEN baseline: bağlantısız geçerli düğümler korunuyor; geçerli PNG baytları ve doğru verilen ölçüler kaydediliyor; sıradan login HTML hiç dosya yayımlanmadan reddediliyor. Bu doğru davranış yeniden yazılmamalı.

```text
.venv/bin/ruff check tests/test_task10_flow_validation_redprep.py tests/test_task10_image_payload_redprep.py
.venv/bin/ruff format --check tests/test_task10_flow_validation_redprep.py tests/test_task10_image_payload_redprep.py
```

İlk format denetimi bir yeni test dosyasında satır biçimi bildirdi; yalnız o yeni dosya `ruff format` ile düzeltildi. Son check: `All checks passed!`; son format: iki dosya biçimli. Tam kalite kapısı/mypy/full pytest/evals çalıştırılmadı.

## Sözleşme ve kalan kabul

API/data migration yok; yalnız mevcut public işlevlere yeni test sözleşmeleri eklendi. `save_images` mevcut geçersiz payload için boş liste sözleşmesi korunarak bozuk PNG de yayımlanmamalı; gerçek decoded dimensions bayt kanıtından gelmeli. Receipt/cancel/capability/revision arayüzleri bu hazırlıkta icat edilmedi ve test edilmiş sayılmadı.

Kalanlar: atomik/CAS flow save, raw ID truncation, edge port/cardinality, gerçek dosya decode/strict base64, MIME/JPEG format tutarlılığı, missing target/reference ve değişen revision gate, exact_size unknown, capability kanıtı, seed/lineage, owned progress/cancel, ilk çıktı sonrası partial retention ve missing-only retry. Viewer focus/galeri seçimi için ayrı native/UI kabul gerekiyor. P9 raporu henüz mevcut değildi; ürün yetkisi sonrası P9 interface değişiklikleri yeniden okunmalı.

Bağlı sağlayıcıyla gerçek generate/edit, dosya açma, alpha/decoded dimensions ve referans görsel karşılaştırması yapılmadı. Native/live/browser/server/Chromadb/ağır test ve alt ajan açılmadı. Yeni dosyaların merkezi code-review kontrolü root'a bırakıldı; bu hazırlık ürün uygulamasına geçiş yetkisi vermiyor.

Hazırlık RED testleri ürün kabulü veya tamamlanma kanıtı değildir. Bu paket çalışma ağacındaki yeni testler yalnız bu pakette etkinleşir; sonraki paketlerin bilinçli RED testlerini bu kapıya katma. Gerçek full-suite kapsamını/exclusion nedenlerini kaydet.

Taşınabilir RED test kaynağı: `red-testleri/paket-10/`. `.txt` uzantısı yanlışlıkla toplanmasını önler; sadece bu pakette ilgili test yoluna aktar. Mevcut aynı dosya varsa önce karşılaştır; üzerine kör yazma.
