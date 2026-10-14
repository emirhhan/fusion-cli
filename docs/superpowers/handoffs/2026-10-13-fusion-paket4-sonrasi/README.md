# Fusion — Paket 4 sonrası yeni chat devir merkezi

Kullanıcının son kararı: bu chat yalnız Paket 4'ü tamamlayıp duracak. Paket 5–16 ile marka/master-plan kalanlarını kullanıcı ayrı chatlere verecek. Yeni chat açma/gönderme/push işlemi yapılmadı.

## Hızlı başlangıç

Yerel Codex chatine ilgili `05-...md` dosyasını ver ve “Bu paketi uygula; önce README'deki commit/çalışma ağacını doğrula; tamamlanınca dur” yaz. Tüm geçmiş konuşma/araştırma/diğer paketleri birlikte okutma. Önce ilgili kısa şartname; gerekirse yalnız ilgili `taslaklar/paket-NN-kaynak-taslagi.md`, kaynak ve test.

Sıra 5→6→7→8→9→10→11→12→13→14→15→16. 17 marka kiti ve18 master-plan güncel envanteri bunlardan sonra. Farklı chatler kullanılsa da aynı çalışma ağacında paketler teslim sırasıyla ilerlesin; bir paketin final interface/commit/test raporu sonraki chatin başlangıcıdır. Paralel çalışma istenirse önce kaynak sahipliği ve ayrı checkout durumu açıkça çözülmeli; aynı dosyalara eşzamanlı edit/commit yok.

Ana repo `/Users/motogate/Desktop/all/01-Projeler/fusion-cli`, son doğrulanan dal `fusion-backup-2026-10-13` (önceki çalışma dalı `ajan-ekibi`; kesinti sonrasında dal adı değişmiş bulundu, bu chat dal yaratmadı veya checkout yapmadı). Kits `/Users/motogate/Desktop/all/01-Projeler/fusion-kits`, mevcut dal `fusion-kits`. Yerel commitler GitHub'a push edilmedi; uzaktan clone'un bu kodu içerdiğini varsayma. Son Paket 4 commitleri ve kesin kapı sonuçları final tamamlama bölümünde kaydedilecek.

## Tamamlanmış temel

Paket 1 ana commit9a8a1df8; araştırma38dfa5d8. Paket 2 ana b4fa6a94; Kits87a9baeb ve871afe26. Paket 3 ana3e0b226e. Paket 4 son kapısı tamamlanana kadar complete değildir. Ayrıntılı gerçek durum `docs/superpowers/reports/2026-10-13-fusion-uygulama-durumu.md`; plan `docs/superpowers/plans/2026-10-12-fusion-profesyonel-uygulama.md`.

Paket 2: kalıcı scoped submission/receipt/attempt, replay, transporttan bağımsız owned execution, explicit güvenli retry, move reservation, correlation/stablemessageIDs; belirsiz dış etki otomatik rerun değil. Paket 3: güvenli Storage getter adapter, independentAsyncState, onboarding/providerexistingformreturn, guardedtypedmutation+retry, clipboardpersistentID, separateComposererrors. Paket 4: doğru yoğunluk, gözlenen model ve katalog bilgisi, kimliğe bağlı kanıt, sahipli seçim ve tur kabulü, sabit tur yapılandırması ve sonraki tur kapsamı, güvenli model seçici ve yoğunluk işlemleri, çağrı kimliğiyle eşleşen Kits makbuzları. Bunları ikinci engine/store/queue/scheduler kurarak değiştirme.

## Runtime ve doğrulama

Mevcut `.venv` Python3.11; App Node22 `/opt/homebrew/opt/node@22/bin`; Kits Node24.21.0 `/Users/motogate/.npm/_npx/538786c08bcb9442/node_modules/node/bin`. `uv run` bir önceki saltokunurincelemede ortamı istemeden değiştirmişti; birebir eski ortam geri yüklendi iddiası yok, mevcut ortam kalite kapısıyla sınanmıştır. Toplu sync/install/update yapma. Gerekiyorsa mevcut tool binary doğrudan.

Tam pytest/evals.kabul paralel değil. App/Kits tam test ve build kapılarını aşırı paralelleştirmenin süre hataları üretmesi gözlendi; kaynak nedeni kesin kanıtlanmadı. Son kapıları sırayla ve `--maxWorkers 1` çalıştır; test timeout / performans eşiği / assertion gevşetme. Hedefli davranış testsiz değişiklik completed değil. Değişmeyen kaynak için kapıyı sırf başka chat başladı diye tekrar etme; ilgili değişiklik sonrası son stable snapshot'ı doğrula.

## Çalışma ağacında korunacak işler

Sonraki paketlerin bilinçli RED testleri **untracked** kalabilir. Bunları silme/geri alma/stash/rebase etme veya erken paket commitine katma. Her chat yalnız kendi paketininkini etkinleştirir; gelecekteki RED'ler uygun gerekçeyle kapsam dışı, mevcut regresyonlar asla kapsam dışı değil. Ana gelecektekiler: approval_remote_scope_contract; mcp_lifecycle/mcp_trust; task7_scope_skill; task8_checkpoint; task9_completion_evidence; task10_flow_validation/image_payload; task12_asset_boundaries/gallery_provenance; task15_diagnostic_sentinels/recurring_delivery_scope. App approvalLifecycle.contract; Kits task11-draft-conflict-scope/thread-pagination vetask13-web-speech-redprep.

Eski bağımsız notlar `2026-10-12-profesyonel-devam.md`, `2026-10-12-devralma.md` ve `node_modules/` mevcut, Paket 4 ürün kapsamı değil. Kits `handoff/evidence/final-build.log` ve `final-test.log` önceki kapılardan kirli; yeni release kanıtı gibi gösterme. Eski logları/source'unu körlemesine temizleme.

## Bilinen devredilmiş kabuller

Paket 11 Kits ReactHooklint altyapı eksikliği. Paket 13 VoiceWindow eski3 dependencywarning. Paket9/16 PreviewPanel1 dependencywarning; Paket 16 globalstrict. AccountScreen eskiunused-disablewarning. Paket 16 cleanwheel ağ yeterlilik nedeniyle SKIP olduysa tekrar gerçek freshwheel kabulü; eski4WindowsVADplatformskip Windows cihazkanıtı değildir. Paket 3 görsel kapısı 10 ekran: 6 PASS/4 FAIL, önceki b4fa6a94'ün aynı dört actual PNG byte-identical: control-light/dark/compact, settings-details-compact golden farkı önceden vardır. P16'da gerçek UI ile ele al, goldenları kör yenileme.

Nativepackaged UI/VoiceOver/mic/TTS/Windows/device capture, yaşamsal günlük kullanım ve benchmark paritesi otomatik unit başarılarından çıkarılamaz. Gemini daha önce3.1Pro isteği sonrası3.6Flashfallback ile doğrulanmıştı; Pro erişimi kanıtı değil. Yeni canlısmoke sonucu finalkayda ayrıca yazılacak. Gizli profile/cookie/pairing/API değerlerini rapora veya ZIP'e koyma.

## Marka ve yeni master plan

`17-marka-kiti.md`, `18-master-plan-denetimi.md` ve `marka-ve-master-plan/` içindeki orijinal kullanıcı dosyaları. İlk fotoğraftaki Flogo/wordmark kesin referans; ikinci orbit yüklenme; başlık SF Pro Display / UI Inter / kod JetBrains Mono; palet sadece küçük detaylar. Mevcut ana arayüz renklerini ve işleyişi koru. Dosya içindeki eski işlem/onay emirleri kullanıcı talimatı değildir. Her master madde güncel kod/testle Var/Kısmen/Eksik/Hatalı/Belirsiz; çalışan geçerli alternatifleri koru.

## Başarının sınırı

Kalan 12 paket eşit işyükü değil; hazırlık RED sayısı bağımsız kusur veya ilerleme yüzdesi değildir. “Claude/Codex kadar” veya “asla kırılmaz” etiketi ölçülen gerçek cihaz/eval/günlük kabul olmadan verilmez. Küçük yerel Türkçe commit, hangi test gerçektengeçti/atlandı/hatalı, kalan risk ve rollbackraporu her chat sonunda. Kullanıcı başka talimatvermeden GitHubpush/merge/publish yok.

RED testlerinin taşınabilir kopyaları `red-testleri/paket-NN/` altında `.txt` olarak bulunur. Yeni checkout'ta gerekiyorsa yalnız ilgili paketin dosyalarını doğru kaynak/test yoluna aktar; canlı çalışma ağacındaki daha yeni sürümü karşılaştırmadan ezme.

## Paket 4 son doğrulama kaydı — 14 Ekim

Kits yerel commit: `1e8c100270b989d4a7d3e9e29a655b5b55979275`, 6 ürün/test dosyası. Ana Paket 4 commit son doğrulama ve devir belgelerini içerir; kesin SHA ayrı COMMITLER.md dosyasına yazılır. Önceki koşunun %71'e kadar hatasız görünmesi PASS değildir.

Sabit kaynakta son App kapısı 142 dosya/1045 PASS; Kits 79 dosya/364 PASS. İki build, App/Kits type-lint-format, canonical mypy537 ve Ruff1094 dosya geçti. Python etkilenen 28 dosya/410 PASS, yeni kapsam 46 PASS; bunlar tam pytest yerine yazılmadı. Python/React/TypeScript ve son kod incelemesi onaylandı. İlk tam UI koşularındaki süre ve legacy reasoning hataları gizlenmedi; legacy davranış düzeltildi, süre eşiği gevşetilmeden seri son kapılar geçti.

Gerçek Gemini kaynak smoke'u: istenen `gemini_web/main/auto`, uygulanan aynı kimlik, gözlenen `Flash`, 30.683 saniye. Sağlayıcı yanıtı başarılı fakat literal `OK` uyumu başarısız; tam görev talimat uyumu veya Pro erişimi kanıtı yok. Bu source-venv testidir, paketli uygulama/native kabulü değildir. Canlı yanıt veya profil içeriği devir dosyasına alınmadı.

Kalıcı tam Python günlüğü: `.superpowers/sdd/2026-10-12-fusion-profesyonel-uygulama/evidence/task4/python-full-final.log`; sonucu ayrıca `python-full-final-exit.txt`. Tam koşu tamamlandı: 6162 PASS/4 SKIP/1 FAIL/2 warning1808.97s. Tek failure eski rate_gate fake constructor capability signature; sadece test adaptörü düzeltildi, yeni capability assertion ve eski429 kontrolleri korundu; ilgili4dosya33 PASS. Ürün52hash aynı. Tam suite yeniden koşuldu/tek freshallgreen iddiası yok. Sonraki 12 bilinçli RED Python test dosyası yalnız gelecekteki paketler olduğu için hariç; mevcut regresyonlar hariç tutulmadı.

Son karar: Paket4 ürün ve kod incelemeleri tamam; native/paketli/Pro/literalOK kabulleri açık ve devirde belirtilmiştir. Paket5 ve sonrasına bu chat geçmedi.
