# Chat görevi — Paket 13: ses-ve-pencere-sahipligi

Bu chat yalnız aşağıdaki paketi uygulasın. Önceki paketlerin tamamlanmış commitlerini koru. Yeni branch/push/merge yapma; kullanıcı değişikliklerini geri alma. `.env`, cookie veya sır okuma. Repo `/Users/motogate/Desktop/all/01-Projeler/fusion-cli`; Kits gereken paketlerde `/Users/motogate/Desktop/all/01-Projeler/fusion-kits`. Önce CLAUDE.md/RULES.md, bu dosya ve belirtilen ilgili kaynakları oku. Gerçek davranışı incele; iyi mevcut alternatifleri yeniden yazma. Yapılmamış testleri geçmiş sayma. Varsayılan modelleri/bütçeleri tahminle değiştirme.

Tek yürütücüyle ilerle; tüm sohbet geçmişini yeni ajanlara taşıma. Yalnız ilgili kapsam için kısa uzman incelemesi yap. Doğrudan mevcut `.venv/bin/python`, App Node22 `/opt/homebrew/opt/node@22/bin`, Kits Node24 `/Users/motogate/.npm/_npx/538786c08bcb9442/node_modules/node/bin` kullan. `uv run`, toplu bağımlılık sync/update veya rastgele `npx` kurulumu yapma. Yeni bağımlılık gerekiyorsa gerekçesini açıkla. Ağır tam pytest ve `evals.kabul` aynı anda koşmasın; tam App/Kits kapıları da yük kaynaklı süre hatalarını azaltmak için sırayla koşsun. Önce anlamlı hedefli regresyon, sonra son stabil kaynak için gerekli kapı; değişmeyen kaynak için aynı kapıyı tekrar etme. Başarısız koşuları gizleme, eşiği/assertion'ı gevşetme.

Her paketin sonunda Türkçe, küçük yerel commit; gerçek değişiklik/test/atlanan kabul/kalan risk/sonraki interface raporu. Kullanıcı daha sonra adım adım push yapacak. Paket bitince sonraki pakete kendiliğinden geçme.

Kaynak plan: `/Users/motogate/Desktop/all/01-Projeler/fusion-cli/docs/superpowers/plans/2026-10-12-fusion-profesyonel-uygulama.md` içindeki Paket 13 ve Global Constraints.

## Paket şartnamesi

# Paket 13 uygulama şartnamesi

Önceki paket tamamlanıp root tarafından yetki verilmeden ürün edit yok. Kaynak otoritesi task-13-blueprint.md; ana plan Global Constraints ve aşağıdaki bölüm; araştırma raporundaki ilgili kabul sözleşmeleri. Önceki paket raporlarında değişen interface ve deferred bulguları oku.

## Sahiplik ve çalışma sınırı

Blueprint ve aşağıdaki kapsamın dosya/interface sahipliği bu işçiye aittir. Başka ajanlarla aynı repo: onların değişikliklerini geri alma. CLAUDE.md/RULES.md; mevcut branch; Türkçe metinler, typed contracts ve mevcut engine/store otoritesi. Sır/.env okuma, branch/push/merge/commit yok. Root fullgate/commit/review sahibi. .venv doğrudan Python; App Node22; Kits cached Node24.21.0. uv run veya paket yöneticisi sync/install/update yok; gerçekten yeni bağımlılık gerekiyorsa önce gerekçeyi roota bildir. Kendi reviewer/subagent spawn etme.

## Paket 13 — Ses ve tarayıcı gerçek kabulü

**Kapsam:** K18–K22/K24/K25, R05/R32. **Dosyalar:** main voice ask/answer, Kits local voice/CallView, web login/browser host, computer panel.

- [ ] A32 + mikrofon reddi, speaker unavailable, TTS fail, hangup pending, same profile lock, visible window false-positive fixtures.
- [ ] Fail test; task/question correlation, owned cancel; TTS fail text preserved; buffer/receipt idempotency.
- [ ] Kullanıcı cihazında native visible login, mikrofon giriş, local STT/TTS ve browser devralma. Şifre/çerez okunmaz. Açılan pencere ekranda doğrulanmadan “açtım” başarı metni yok.
- [ ] Unit/full relevant gates + L12 kanıt. Kullanıcının cihaz adımı gereken yerde gerçek blocker olarak açık söylenir; diğer bağımsız işler sürdürülür.


## Teslim

Meaningful TDD RED→GREEN ve hedefli testler: import eksikliği davranış kanıtı değildir, assertion gevşetme/sleep uzatma yok. Mevcut doğru davranışı ölçüp kaydet, yeniden yazma. Beklenmedik failure kök nedenini teşhis et. Rapora exact changed files, commands/results, API/data migration contracts, remaining real/native acceptance ve deferred bulgular yaz. Rapor: task-13-report.md. Full pytest ve evals.kabul root tarafından sıralı; ağır/live koşuyu işçi açmaz. Root yetkili canlı kabul alt görevi ancak ayrı açık mesajla yürür.

## Ayrıntılı kaynak taslağı

`/Users/motogate/Desktop/all/01-Projeler/fusion-cli/docs/superpowers/handoffs/2026-10-13-fusion-paket4-sonrasi/taslaklar/paket-13-kaynak-taslagi.md`. Bu dosya devir paketinde mevcuttur. Bu taslak ilk hazırlık durumudur; önceki paketlerin yeni kod/interface/testleriyle tekrar karşılaştır.

## Tarihsel hazırlık raporu

# Paket 13 — sınırlı offline RED hazırlığı

13 Ekim 2026. Yalnız iki yeni davranış testi hazırlandı; ürün aşaması açılmadı.
P12 tamamlanması ve root'un açık ürün uygulaması yetkisi bekleniyor.
Native L12 kabulü yapılmadı. P2 donmuş ürün ve mevcut testler korunmuştur.

## Yeni dosyalar ve mevcut API

- Kits `tests/task13-web-speech-redprep.test.ts`.
- Main `.superpowers/sdd/2026-10-12-fusion-profesyonel-uygulama/task-13-report.md`.

Testler gerçek exported `WebSpeechEngine.speak(text)` çağırır. Yeni önerilen
interface import edilmez. Boş `SpeechWindow` ve enjekte edilen sahte
`SpeechSynthesis`/utterance dışında cihaz kontrolü yoktur. İkinci test gerçek
metnin sahte synthesizer'a aynen verildiğini ayrıca doğrular; bu, UI caption
veya durable transcript korunma kanıtı değildir.

Kaynak nedeni: `web-speech.ts` eksik synth/constructor için `Promise.resolve()`
döndürüyor; mevcut `onerror` aynı `done` callback'iyle `resolve()` yapıyor.
Bu nedenle kullanıcıya seslendirme başarısızlığı ile tamamlanması ayırt
edilebilir biçimde iletilmiyor. Test beklentisi mevcut Promise<void> API'sinde
Error rejection'dır; yeni typed status sözleşmesi ürün aşamasına aittir.

## Exact komutlar ve sonuçlar

CWD `/Users/motogate/Desktop/all/01-Projeler/fusion-kits`.
Cached Node24.21.0 doğrudan kullanıldı; package manager veya kurulum yok.

```sh
/Users/motogate/.npm/_npx/538786c08bcb9442/node_modules/node/bin/node node_modules/vitest/vitest.mjs run tests/task13-web-speech-redprep.test.ts
/Users/motogate/.npm/_npx/538786c08bcb9442/node_modules/node/bin/node node_modules/eslint/bin/eslint.js tests/task13-web-speech-redprep.test.ts
/Users/motogate/.npm/_npx/538786c08bcb9442/node_modules/node/bin/node node_modules/prettier/bin/prettier.cjs --check tests/task13-web-speech-redprep.test.ts
/Users/motogate/.npm/_npx/538786c08bcb9442/node_modules/node/bin/node node_modules/prettier/bin/prettier.cjs --write tests/task13-web-speech-redprep.test.ts
```

İlk Vitest exit 1: 1 file / 2 assertion FAIL. Eksik synth testi
`promise resolved undefined instead of rejecting`; onerror testi
`completed` yerine `failed` bekliyor. Toplama/import hatası yok.
İlk ESLint exit 0; ilk format check exit 1. Yalnız yeni test Prettier write
ile biçimlendirildi. Son seçili koşu yine 2 beklenen assertion FAIL;
son ESLint ve Prettier check exit 0. Davranış GREEN yoktur; metin aktarımı
assertion'ı geçer, fakat caption/transcript kabulü olarak sunulmaz.

## Bağımlı sözleşmeler ve kalan işler

P2 raporundaki task/attempt/receipt otoritesi değiştirilmedi. P5 soru/decision
korelasyonu, P8 owned cancellation, P11 host AbortSignal ve P12 host capability
matrix henüz sınırlı hazırlık aşamasındadır; uygulanmış kabul sayılmadı.
API/data migration yapılmadı. Ürün yetkisi sonrası mevcut motor sözleşmesinde
hata bildirimi, useLocalVoice caption/full transcript korunması ve yalnız aynı
answer/generation için TTS retry doğrulanmalı; model turn tekrar çalışmamalı.

Stale question/task answer, eski recognition generation, owned hangup + pending
fetch/server task cancellation, durable end receipt, native ses.bekle failure,
same-profile lock ve spawn-success/visible-window false-positive bu iki testte
ölçülmedi. Yeni engine/loop/receipt otoritesi icat edilmedi. Bu dar hazırlık
paket tamamlandı veya RED→GREEN uygulandı iddiası taşımaz.

L12 için gerçek kullanıcı cihazı kanıtı hâlâ gerekir: packaged App/Kits'te
mikrofon deny→text→allow recovery; kullanıcının kısa Türkçe sözüyle gerçek STT
ve call/task korelasyonu; kullanıcının duyduğu Türkçe TTS ve mute/interrupt;
thinking sırasında owned hangup ve diğer session korunması; görünür native
provider login penceresi/profile busy/handoff; kullanıcı tarafından şifre/2FA;
aynı host nonce/call/task ile bir gerçek tur. Bu görev sınırları gerçek
mikrofon/speaker/browser/window/profile/login/OS permission kullanımını
yasakladığından native adımlar burada test edilemez.

Ağ/provider/server/heavy/fullgate/Chromadb/uv run/env/package install,
branch/commit/push ve alt ajan açılması yok. Sır/.env okunmadı. Root merkezi
review ve fullgate sahibidir; yeni RED test P2 commit kapsamına alınmamalıdır.
Sınırlı hazırlık burada durdu; açık P12 complete/product yetkisi bekleniyor.

Hazırlık RED testleri ürün kabulü veya tamamlanma kanıtı değildir. Bu paket çalışma ağacındaki yeni testler yalnız bu pakette etkinleşir; sonraki paketlerin bilinçli RED testlerini bu kapıya katma. Gerçek full-suite kapsamını/exclusion nedenlerini kaydet.

Taşınabilir RED test kaynağı: `red-testleri/paket-13/`. `.txt` uzantısı yanlışlıkla toplanmasını önler; sadece bu pakette ilgili test yoluna aktar. Mevcut aynı dosya varsa önce karşılaştır; üzerine kör yazma.
