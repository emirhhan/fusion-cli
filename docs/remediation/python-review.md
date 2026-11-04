# Bağımsız Python incelemesi — ilk tur

Kapsam: baseline `2b2c8fe4` üzerine `/tmp/fusion-python-review-20261104.diff`
immutable snapshot; A01–A03 backend, B01–B07, C01–C06 ve screenshot yönlendirmesi.
A04–A07 devam eden worker değişiklikleri ve D eval uygulaması bu verdict kapsamında değil.
RULES.md, spec, plan ve B/D raporları okundu. Üretim kodu değiştirilmedi;
gerçek ağ/model/hesap/kurulum erişimi yapılmadı. Alt ajan kullanılmadı.

**Kabul verdict: BLOCK.** Aşağıdaki üç kontrol akışı açığı kapatılmadan
C02/C05/screenshot kabulü tamamlanmış sayılamaz.

**Kod kalitesi verdict: BLOCK.** İki P1 akış kusuru ve iki P2 akış/kaynak bütçesi
kusuru var. Yerel/scoped test başarısı bu entegrasyon yollarını kanıtlamıyor.

## Bulgular

### PR01 — P1: Artifact-only dalı teslim/video kapılarını da atlıyor

Snapshot: `src/fusion_cli/engines/agent/loop.py:4920` (`artifact_only` dalı).
`core/artifact_kind.py` PDF/Office ve video uzantılarını da artifact sayıyor.
Bu dal composite verifier yerine yalnız `verify_artifact_changes` çağırdığı için
OutputPathVerifier'ın istenen hedef, bu turda üretim ve video decode/plan kontrolleri
çalışmıyor. Kullanıcı `report.pdf` isterken yalnız `screen.png` yazılması durumunda
PNG biçimi inceleniyor, eksik PDF engelleyici bulunamıyor. Video tesliminde de
önceki oynatılabilirlik/Remotion kapıları örtülüyor.

Düzeltme: artifact görevinde yalnız proje kod komutlarını atla; çıktı, video,
Remotion ve artifact ölçümlerini normal composite hattında koru. Gerçek
`build_verifier` ile screenshot+missing requested PDF ve bozuk video regresyonu
önerildi. Controller bulguyu kabul etti; yeni yapı kontrolü için re-review bekleniyor.

### PR02 — P1: Öz-denetim fingerprint'i teslim yollarına kör

Snapshot: `src/fusion_cli/engines/agent/loop.py:1529`.
`take_fingerprint` varsayılanı `dist`, `build`, `.fusion` gibi yolları dışlıyor.
Öz-denetim bu yollar altında bir dosyayı değiştirse bile önce/sonra fingerprint
aynı kalıyor. `has_new_mutation` yalnız fingerprint `None` iken etkili olduğundan
eski kapı başarısı yeni dosyaya taşınabiliyor.

Çalıştırılmış sentetik kanıt: geçici kökte `dist/index.html` içerik `valid`→`invalid`;
önce `{}`, sonra `{}`, `same_fingerprint=True`, gerçek dosya değişmiş.

Düzeltme: değişiklik kaydındaki/touched teslim dosyalarının sürümünü ayrıca ölç;
yalnız proje tarayıcısının kör olduğu mutasyonu değişikliksiz sayma. Varsayılan
fingerprint'in gürültü sözleşmesini genel olarak değiştirmek gerekmiyor.

### PR03 — P2: Hiç yazılmayan açık teslim isteği yeni çıktı kapısına ulaşmıyor

Snapshot: `src/fusion_cli/engines/agent/loop.py:4918`.
OutputPathVerifier doğrudan çağrıldığında artık touched boşken eksik dosyayı
reddediyor. Ancak `_verify`, `mutating_tool_calls_made == 0` için önce `None`
döndürüyor. Normal `run_agent` çağrısında `require_local_mutation=False` varsayılan;
yerel mutasyon zorunluluğu yalnız doğrulama düzeltmesi dalında uygulanıyor.
Dolayısıyla doğal dilde açık çıktı isteyen, modelin hiçbir çıktı üretmediği kök
turda yeni çıktı koşulu hiç ölçülmeyebilir.

Düzeltme: `requested_outputs` varsa çıktı kapısı mutasyon sayısından bağımsız
çalışmalı; sıradan soru-cevap turunda proje kod komutu çalıştırılmaması korunmalı.
Saf verifier testi yanında kök agent veya `_verify` entegrasyonu gerekli.

### PR04 — P2: Yeni dosya okuyucuları sınırsız bellek/çözme işi yapıyor

Snapshot: `src/fusion_cli/engines/agent/artifact_verify.py:49`–59.
JSON/metin `read_text` ile tamamen belleğe alınıyor; JSON tekrar parse ediliyor.
Office arşivinde `testzip` tüm üyeleri çözüyor, gerekli XML de limitsiz `read` ile
belleğe alınıyor. Büyük veya yüksek sıkıştırmalı bir agent çıktısının kapanış
kontrolü uygulamayı bellek/süre açısından zorlayabilir. `to_thread` bu bütçeyi
sınırlamaz.

Düzeltme: dosya, gerekli XML üyesi ve toplam açılmış arşiv boyutunu ölç;
kapasite aşımında açık ölçülmedi/UNVERIFIED sonucu üret. Kırpılmış veriyi geçerli
format diye parse ederek PASSED verme.

## Olumlu değerlendirme ve sınırlar

- A01 seçim korunumu, A02 pending snapshot ve A03 backend kabul/ret ayrımı
  incelenen snapshot'ta kök hatalara uygun; yeni A04–A07 protokol değişiklikleri
  ayrıca incelenmeli.
- B kayıtları doğru model kimliğine bağlanmış; bilinmeyen yedeğe birincilin
  doğrulanmış yeteneği aktarılmıyor.
- Araştırma projeksiyonunda çağrı/URL metadata bütçesi hesaba katılmış;
  temsil mümkün değilse özgün geçmiş korunuyor. Taşmada bağlamın küçülmemesi
  açık sınırlama; canlı sentez kabulünün açık bırakılması doğru.
- B03 ara kullanıcı mesajları birebir taşınıyor. Özetler rol/yetki yükseltmiyor.
- C01 aynı kapsamda geçen tekrarın eski başarısızlığı aşması tutarlı.
- C03 ölçülmedi kriteri ve uyarı payload'a taşınıyor. C04 boşluklu quoted adlar
  ile kök içi mutlak hedefler ele alınmış; kök dışı hedef kabul edilmiyor.
- C06 spawn/readiness/install iptallerinde owned process cleanup eklenmiş;
  gerçek süreç regresyonları yalnız mock çağrı sayısına dayanmıyor.

## Araç kanıtı

- `git diff -- '*.py'` incelenmek üzere alındı; esas immutable snapshot yukarıdaki.
- Scoped mypy (`MYPYPATH=$PWD/src`, research_evidence, artifact_verify,
  output_verify, loop, preview_server/launch, web/web_evidence,
  model_lookup, providers/factory): **Success: no issues found in 10 source files**.
- Snapshot dosyaları üzerinde canlı Ruff check: devam eden A worker'ın
  chrome_bridge.py:496 uzun satırı ve test_remediation_artifact_routing.py
  import sırası çıktı. Format check: output_verify ve preview_server format
  istedi. Bunlar çalışma sürerken görülen statik sonuçlar; davranış kusuru
  olarak sayılmadı, son kalite kapısında temizlenmeli.
- Implementer raporlarındaki testler tekrar çalıştırılmadı; review saf kontrol
  akışı, snapshot ve yukarıdaki geçici dosya fingerprint repro'suna dayalıdır.

## Re-review

Controller PR01 düzeltmesini kabul etti. Yeni diff/test kanıtı gelince yalnız
bu bulguların kapanışı yeniden kontrol edilecek; ilk tur BLOCK henüz kaldırılmadı.

# Scoped re-review — PR01–PR04 fix wave

Yeni inceleme paketi: `/tmp/fusion-python-fix-review.diff`; mevcut kaynakla
karşılaştırıldı. Kapsam bu dört bulgu ve bunların düzeltme wiring'iyle sınırlıdır.

- **PR01 asıl bypass kapandı:** `_verify` normal composite'a dönüyor;
  `CommandVerifier` yalnız artifact-only dosyalarda kod komutlarını atlıyor.
  OutputPathVerifier, video ve diğer normal kapılar artık bu dallanmada silinmiyor.
  Ancak ArtifactChangeVerifier'ın koşulsuz kurulması mevcut bütün kapıları kapatma
  semantiğini değiştiriyor: boş projede web/browser/visual=False ve komut yokken
  `build_verifier` artık None dönmüyor. Aynı web_verification koşuluna taşınması
  controller'a iletildi; PR01 kapanışı bu küçük wiring düzeltmesini bekliyor.
- **PR02 kapandı:** proje fingerprint'ine ek olarak changes/touched dosyalarının
  size/mtime_ns/ctime_ns sürümleri ölçülüyor; dist/build/.fusion kapsam dışı
  bırakılmıyor. Sürümler okunamazsa ek mutasyon temkinli yeniden doğrulama açıyor.
  Controller'ın a.py/dist/a.py × mutation/no-mutation 4/4 kanıtı tasarımla tutarlı.
- **PR03 kapandı:** açık requested_outputs bulunan sıfır-mutation turunda doğrudan
  OutputPathVerifier çalışıyor. Sıradan soru-cevapta proje kod komutu açılmıyor.
- **PR04 kapandı:** merkezi 8MiB dosya/üye, 16MiB toplam ZIP açılımı ve 16M piksel
  bütçeleri okuyucudan önce uygulanıyor. Aşım problem/PASSED olarak sunulmuyor;
  açık ölçülmedi uyarısı upper-layer UNVERIFIED kriterine dönüşüyor. İmaj reader
  ayrıca gerçek load yapıyor. 9MB JSON ve sıkıştırılmış 9MB Office testleri bu
  önceki sınırsız yolları hedefliyor.

Static re-review: scoped mypy **4 source files temiz**; controller'ın ayrı
`/tmp/fusion-controller-mypy2.log` kaydı **5 source files temiz**. Scoped Ruff
check yalnız yeni ArtifactChangeVerifier importunun sırasını işaretledi;
controller son format/lint kapısında düzeltecek. Yeni davranış testleri review'da
tekrar çalıştırılmadı; controller'ın exact red/green kanıtı ve gerçek kaynak
kontrol edildi.

**Bu ara scoped kabul verdict: PR02–PR04 APPROVE; PR01 wiring düzeltmesi bekliyor.**
**Bu ara scoped kalite verdict: PR01 düzeltme kaynaklı konfigürasyon semantiği
nedeniyle henüz BLOCK; dört asıl defect için yeni açık bulunmadı.**

## Final scoped kapanış

PR01'in son wiring'i mevcut `verification.py:234` üzerinde tekrar okundu:
ArtifactChangeVerifier artık `web_verification and tool_context is not None`
koşuluyla kuruluyor. Normal composite korunuyor; kod komutunun atlanması yalnız
CommandVerifier'ın artifact-only kontrolü içinde. Böylece ilk bypass ve fix
sırasında doğan konfigürasyon semantiği sorunu birlikte kapandı.

Son scoped `ruff check` (artifact_verify, change_digest, loop, verification):
**All checks passed!** Controller'ın `/tmp/fusion-review-wave-tests.log` kaydı
okundu: **59 test işareti, %100**, hata çıktısı yok. Bu testler inceleyici
adına yeniden koşulmadı; uygulayıcı kanıtı olarak kaydedildi.

**Final scoped kabul verdict: APPROVE — PR01, PR02, PR03, PR04 kapalı.**
**Final scoped kod kalitesi verdict: APPROVE — bu dört düzeltmede kalan
P1/P2 bulgu yok.**

Bu onay ilk snapshot'ın tanımlı Python kapsamı ve dört düzeltme dalgası içindir;
A04–A07 yeni worker değişikliklerinin, D eval uygulamasının, tüm repo testlerinin
ve gerçek platform/canlı model kabullerinin onayı değildir. İlk BLOCK raporu
geçmiş kanıt olarak korunmuştur; güncel scoped verdict bu bölümdedir.

# Son küçük Python delta incelemesi — aday 283cc3bd sonrası

Kapsam yalnız `/tmp/fusion-web-delta-review.diff` içindeki üç dosya:
`tools/web.py`, `tests/test_web_provenance_remediation.py`,
`tests/test_eval_criteria_sound.py`. Paket SHA256:
`9f56a42d625b50bebb1b23a44077e0747dfa5a17a1700c9839bf1a1e35900ae2`.
Diğer aday kodu veya tamamlanan shard'lar bu deltanın yeniden test kanıtı sayılmadı.

- `web_fetch`: erişim duvarı varsa protokol öneki tekrar ilk satırda;
  provenance bunun ardından, gerçek gövde en sonda. Duvar olmayan normal sonuçta
  provenance bilgisi korunuyor. `structured.source` alanı değişmedi.
  Yeni regresyon hem prefix davranışını hem final URL/erişim zamanının kalmasını
  ölçüyor. Başarılı HTTP erişimi erişim duvarının başarı kanıtı haline getirilmemiş.
- Eval referans helper'ı: raw shell/Python değiştirme yerine üretimdeki
  `plan_acceptance` ve `_verification_env` yolunu kullanıyor. Scratch cwd içinde
  evaluator modülünün bulunması ve güvenilir yorumlayıcı başlangıcı aynı
  sözleşmeye bağlanmış. Exit-code assertion kaldırılmamış veya gevşetilmemiş;
  testin kontrol ettiği çözüm/kriter değişmemiş.

Statik doğrulama bu üç dosyada çalıştırıldı:
`ruff check`: **All checks passed!**;
`ruff format --check`: **3 files already formatted**;
`MYPYPATH=$PWD/src mypy --follow-imports=silent src/fusion_cli/tools/web.py`:
**Success: no issues found in 1 source file**.
Controller'ın fresh `/tmp/fusion-web-delta-tests.log` çıktısı okundu:
**82 passed in 16.99s**. Bu inceleme testleri ayrıca yeniden çalıştırmadı.

**Son delta kabul verdict: APPROVE.**
**Son delta Python stil/tip/semantik güvenlik verdict: APPROVE.**
Bu üç dosyalık farkta kalan actionable P1/P2 bulgu yok. Tam adayın tüm testleri
ve sonraki deadlock koşusu için controller'ın ayrı fresh kanıtı gereklidir.
