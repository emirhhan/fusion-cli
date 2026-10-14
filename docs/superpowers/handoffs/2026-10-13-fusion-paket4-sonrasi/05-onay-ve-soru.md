# Chat görevi — Paket 5: onay-ve-soru

Bu chat yalnız aşağıdaki paketi uygulasın. Önceki paketlerin tamamlanmış commitlerini koru. Yeni branch/push/merge yapma; kullanıcı değişikliklerini geri alma. `.env`, cookie veya sır okuma. Repo `/Users/motogate/Desktop/all/01-Projeler/fusion-cli`; Kits gereken paketlerde `/Users/motogate/Desktop/all/01-Projeler/fusion-kits`. Önce CLAUDE.md/RULES.md, bu dosya ve belirtilen ilgili kaynakları oku. Gerçek davranışı incele; iyi mevcut alternatifleri yeniden yazma. Yapılmamış testleri geçmiş sayma. Varsayılan modelleri/bütçeleri tahminle değiştirme.

Tek yürütücüyle ilerle; tüm sohbet geçmişini yeni ajanlara taşıma. Yalnız ilgili kapsam için kısa uzman incelemesi yap. Doğrudan mevcut `.venv/bin/python`, App Node22 `/opt/homebrew/opt/node@22/bin`, Kits Node24 `/Users/motogate/.npm/_npx/538786c08bcb9442/node_modules/node/bin` kullan. `uv run`, toplu bağımlılık sync/update veya rastgele `npx` kurulumu yapma. Yeni bağımlılık gerekiyorsa gerekçesini açıkla. Ağır tam pytest ve `evals.kabul` aynı anda koşmasın; tam App/Kits kapıları da yük kaynaklı süre hatalarını azaltmak için sırayla koşsun. Önce anlamlı hedefli regresyon, sonra son stabil kaynak için gerekli kapı; değişmeyen kaynak için aynı kapıyı tekrar etme. Başarısız koşuları gizleme, eşiği/assertion'ı gevşetme.

Her paketin sonunda Türkçe, küçük yerel commit; gerçek değişiklik/test/atlanan kabul/kalan risk/sonraki interface raporu. Kullanıcı daha sonra adım adım push yapacak. Paket bitince sonraki pakete kendiliğinden geçme.

Kaynak plan: `/Users/motogate/Desktop/all/01-Projeler/fusion-cli/docs/superpowers/plans/2026-10-12-fusion-profesyonel-uygulama.md` içindeki Paket 5 ve Global Constraints.

## Paket şartnamesi

# Paket 5 uygulama şartnamesi

Önceki paket tamamlanıp root tarafından yetki verilmeden ürün edit yok. Kaynak otoritesi task-5-blueprint.md; ana plan Global Constraints ve aşağıdaki bölüm; araştırma raporundaki ilgili kabul sözleşmeleri. Önceki paket raporlarında değişen interface ve deferred bulguları oku.

## Sahiplik ve çalışma sınırı

Blueprint ve aşağıdaki kapsamın dosya/interface sahipliği bu işçiye aittir. Başka ajanlarla aynı repo: onların değişikliklerini geri alma. CLAUDE.md/RULES.md; mevcut branch; Türkçe metinler, typed contracts ve mevcut engine/store otoritesi. Sır/.env okuma, branch/push/merge/commit yok. Root fullgate/commit/review sahibi. .venv doğrudan Python; App Node22; Kits cached Node24.21.0. uv run veya paket yöneticisi sync/install/update yok; gerçekten yeni bağımlılık gerekiyorsa önce gerekçeyi roota bildir. Kendi reviewer/subagent spawn etme.

## Paket 5 — İşlem onayı ve soru yaşam döngüsü

**Kapsam:** U33–U35, E15–E22, R09/R15/R32. **Dosyalar:** `engines/agent/approval.py`, engine_tools/loop/clarify, appserver question/approval summary, App Approval/types, voice answer bridge. **Tüketir:** paket2 session/turn/request ids; D03 aktif göreve steer / açık bağımsız queue kararı.

**Önerilen interface:** mevcut SessionQuestion kimliği kullanılır; yanıt envelope'una `questionId`, `turnId` ve `decisionId` korelasyonu eklenir. `decision` izin için once/session/deny; bilgi için text/choice; timeout/cancel ayrı terminal. Existing protocol kelimeleri migration adapter'da korunur. AuthorizationScope sunucu/hesap/eylem/normalize hedef parmak izi tutar; raw secret içermez.

- [ ] A08–A11/A32: ardışık soru state reset, double send, stale ses cevabı, target değişikliği, policy revoke, Escape deny olmayan kart.
- [ ] Fail test; parent request kapsamını callback/key ile doğrula. Timeout önerilen seçeneği yanıt yapmaz.
- [ ] ApprovalMemory'yi mevcut shell scope'u bozmadan uzak hedef kapsamıyla genişlet; kullanıcı geniş izin seçiyorsa scope açık metinle göster. Deny/blocked/optional default ayrı.
- [ ] Kart pending iken disabled; gönderim fail ise retry; kapanışta odak geri. Async optional soru bağımsız işi durdurmaz; required dependent iş bekler.
- [ ] Approval/loop/voice ve UI testler; güvenli fixture dış etki tekliği; full gate. Onay politikası değişikliği görünür release notu.


## Teslim

Meaningful TDD RED→GREEN ve hedefli testler: import eksikliği davranış kanıtı değildir, assertion gevşetme/sleep uzatma yok. Mevcut doğru davranışı ölçüp kaydet, yeniden yazma. Beklenmedik failure kök nedenini teşhis et. Rapora exact changed files, commands/results, API/data migration contracts, remaining real/native acceptance ve deferred bulgular yaz. Rapor: task-5-report.md. Full pytest ve evals.kabul root tarafından sıralı; ağır/live koşuyu işçi açmaz. Root yetkili canlı kabul alt görevi ancak ayrı açık mesajla yürür.

## Ayrıntılı kaynak taslağı

`/Users/motogate/Desktop/all/01-Projeler/fusion-cli/docs/superpowers/handoffs/2026-10-13-fusion-paket4-sonrasi/taslaklar/paket-05-kaynak-taslagi.md`. Bu dosya devir paketinde mevcuttur. Bu taslak ilk hazırlık durumudur; önceki paketlerin yeni kod/interface/testleriyle tekrar karşılaştır.

## Tarihsel hazırlık raporu

# Paket 5 — sınırlı RED hazırlığı

13 Ekim 2026. Ürün uygulaması başlamadı. Paket 4 tamamlanması ve root açık ürün yetkisi bekleniyor. Yalnız aşağıdaki üç yeni dosya oluşturuldu; eski ürün/test, Python gate snapshot, defaults, secret/.env ve Kits kaynakları değiştirilmedi. Başka işçilerin değişiklikleri korunuyor.

## Dosyalar

- `tests/test_approval_remote_scope_contract.py`
- `app/src/screens/approvalLifecycle.contract.test.tsx`
- `.superpowers/sdd/2026-10-12-fusion-profesyonel-uygulama/task-5-report.md`

## Kaynak otoritesi ve eşleme

CLAUDE.md, RULES.md, ana plan Global Constraints/Paket 5, task-5-brief.md, task-5-blueprint.md ve Paket 2 raporu okundu. Paket 2 submission/admission ve event korelasyonu mevcut; bu hazırlık question/decision receipt için yeni wire sözleşmesi icat etmiyor.

- `src/fusion_cli/engines/agent/approval.py`: gerçek `build_request`, `build_policy`, `ApprovalMemory` ve public `decide` kullanılıyor. İlk oturum izninden sonra başka hesap/eylem/hedef için fake kullanıcı DENY cevabı hazırdır. Mevcut `_scope` uzak araçta yalnız tool.name döndürdüğü için yeniden kurulan politika bu reddi sormadan ALLOW veriyor. Üç parametrik örnek assertion RED; import veya eksik önerilen API hatası yok.
- Aynı test dosyası `bash` → `run_shell` alias'ında tam komut kapsamını public memory davranışıyla ölçer: aynı komut hatırlanıyor, farklı komut hatırlanmıyor (PASS).
- `app/src/dialogs/Approval.tsx`: gerçek bileşen render ediliyor; pending Promise dönen public `onCevap` sınırında tıklama + sayı tuşu iki callback çağırıyor, düğmeler açık kalıyor. Rerender ile sonraki soruda önceki Other metni korunuyor. `serbestCevap=false` iken sayı tuşu gizli Other input'unu açıyor. Dördü assertion RED.
- Legacy bilgi cevabının `{metin: "Örnek"}` envelope'u mevcut ve PASS. Callback/fake dışında ürün komponenti mock edilmedi.

## Gerçek komutlar ve sonuçlar

Repo kökünde:

```sh
.venv/bin/pytest tests/test_approval_remote_scope_contract.py -q
```

Exit 1: 3 FAIL, 1 PASS. Üç scope değişiminde beklenen DENIED yerine ALLOW. Shell dar kapsamı PASS. Yaklaşık 0.52 saniye; ağır fixture veya gerçek executor çağrısı yok. Offline executor yanlışlıkla çağrılırsa assertion fırlatır.

App kökünde:

```sh
PATH=/opt/homebrew/opt/node@22/bin:$PATH npm test -- --run src/screens/approvalLifecycle.contract.test.tsx --maxWorkers=1
```

Node `v22.23.3`; runtime kontrolü geçti. Exit 1: 4 FAIL, 1 PASS, tek dosya. Double send: beklenen 1 callback, gelen 2. Pending: beklenen disabled=true, gelen false. Ardışık soru: beklenen boş input, gelen `Eski proje`. Gizli Other: beklenen null, gelen input. Legacy metin envelope PASS. Vitest 1.17 saniye.

```sh
.venv/bin/ruff check tests/test_approval_remote_scope_contract.py
.venv/bin/ruff format --check tests/test_approval_remote_scope_contract.py
```

İkisi exit 0: All checks passed; 1 file already formatted.

## Sınırlar ve sonraki uygulama

Bu bounded hazırlık GREEN veya paket tamamlandı iddiası taşımaz. Full pytest, evals, browser/native/live koşu, ağ/gerçek remote etki, paket kurulumu, uv run, commit ve reviewer/subagent yok. Mevcut root full Python gate kanıtı değiştirilmedi ve bu RED testler için full gate tekrar açılmadı.

Remote fixture alanları sahte ve genel public ToolArgs girdisidir. Engine bu alan adlarından scope tahmin etmemeli: ürün aşamasında adapter'a ait typed normalized scope resolver kullanılır; scope çözülemiyorsa session izni genişletilmez. Test aynı scope'un remote tekrar kullanımını garanti etmez; bunu gerçek resolver interface'i sonrası ayrı kabul ölçmelidir.

UI ardışık soru testi public soru prop değişimini ölçer; SessionApplication identity/key wiring, host question/turn/decision receipt, retry failure, timeout/cancel, stale voice, policy revoke, focus dönüşü ve steering henüz ölçülmedi. Pending Promise fixture deterministiktir; timer/sleep ve gerçek transport yok. Correlated identity/key migration yetkili uygulamada mevcut SessionQuestion otoritesiyle bağlanmalıdır; metin değişimi ürün kimliği yapılmamalı.

Sonraki adım yalnız root açık Paket 4 tamamlandı / ürün uygulaması yetkisi sonrası RED→GREEN çalışmasıdır.

Hazırlık RED testleri ürün kabulü veya tamamlanma kanıtı değildir. Bu paket çalışma ağacındaki yeni testler yalnız bu pakette etkinleşir; sonraki paketlerin bilinçli RED testlerini bu kapıya katma. Gerçek full-suite kapsamını/exclusion nedenlerini kaydet.

Taşınabilir RED test kaynağı: `red-testleri/paket-05/`. `.txt` uzantısı yanlışlıkla toplanmasını önler; sadece bu pakette ilgili test yoluna aktar. Mevcut aynı dosya varsa önce karşılaştır; üzerine kör yazma.
