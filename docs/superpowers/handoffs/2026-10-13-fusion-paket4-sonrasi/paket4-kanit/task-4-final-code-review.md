# Paket 4 son kaynak incelemesi

Karar: **APPROVE — belirtilen P4 kaynak ve düzeltme kapsamı için.** Bu statik kapıda raporlanacak somut CRITICAL/HIGH/MEDIUM/LOW bulgu saptanmadı. Tam kalite kapısının veya canlı kabulün tamamlandığı iddia edilmiyor.

## Kapsam ve yöntem

Ana depo `3e0b226e`, Kits `871afe26` tabanlarına karşı çalışma ağacı diff/stat ve status okundu. Staged değişiklik yok. Ana CLAUDE.md/RULES.md, task-4-inline-fix-report.md ve Python/React/TS yeniden inceleme raporları okundu. P4 model capability, reasoning, kimlik invalidasyonu, owned model seçimleri, kabul snapshot'ı, katalog UI ve gerçek çağrı makbuzu akışları kontrol edildi. Önceki uzmanların ayrıntılı incelemeleri bu son kapının girdisidir; aynı geniş incelemenin bağımsız tekrar koşumu gibi sunulmuyor.

Gerçek kaynak üzerinde özellikle ModelPicker, useActiveModel, useModelCatalog, Settings seçim yolu, SessionApplication bağlantısı, olayMetni; ModelSpec/ReasoningResolution, EventingProvider, LiteLlmProvider, factory/katalog, AppSession owned seçim ve kabul yolları, web evidence; Kits receipt normalizer, servis kapsamı ve FusionCard okundu. İlgili klavye ve makbuz regresyon testleri statik olarak incelendi. P5–16 RED hazırlıkları, eski notlar ve ortam içerikleri kapsam dışıdır. Kaynak/test değişikliği, ortam/kurulum, test koşusu, dış servis, ajan veya commit işlemi yapılmadı; yalnız bu rapor oluşturuldu.

## Son iki düzeltme

- `app/src/protocol/olayMetni.ts` eski yalnız reasoning taşıyan ModelCallFinished olayını yeniden `{ metin: "düşündü", dusunme }` olarak sunuyor. Model kimliği olan gerçek makbuzlar requested/observed ve requested/applied effort ayrımını koruyor; boş observed alanına istenen kimlik yazılmıyor. Kimlik ve reasoning olmayan olay boş satır üretmiyor.
- `app/src/screens/ModelPicker.tsx` active-descendant alanını `!busy && visible.length` koşuluyla üretir. Aynı `!busy` koşulu gerçek option render'ında kullanıldığı için yükleme sırasında saklanan eski seçenekler görünmezken combobox olmayan bir option'a işaret etmez. Klavye handler'ı da busy sırasında seçim yapmaz. Mevcut yükleme testi artık options doluyken active-descendant yokluğunu kontrol ediyor; retry Enter ve seçili modelden ayrı aktif hedef davranışları korunuyor.

## Sözleşme değerlendirmesi

ModelSpec kimlik değişiminde doğrulanmış effort kanıtını sıfırlıyor; factory başka fallback yaprağına birincil modelin kanıtını taşımıyor. Adaptör yalnız doğrulanmış effort gönderiyor ve aynı çözümlemeyi sonuç makbuzuna yazıyor. Web kanıtı scope ve gerçek adaptör kaynak fingerprint'iyle eşleştiriliyor; legacy izin ayrı unverified sunumla korunuyor. AppSession owned seçim görevini shield edip kabul kilidinde tutuyor; kabul edilen tur config snapshot'ını taşır. UI eski sahibin aktif modelini göstermez; seçim sonucu mevcut owner/pending/error/retry yolundan geçer. Kits gözlem yokluğunu null tutar, çağrı kimliğiyle upsert ve son 20 makbuz sınırını korur. Yeni geniş paralel mimari veya ikinci aktif-model store/istek yolu görülmedi.

## Kanıtın sınırları

Root ve uzman raporlarındaki etkilenen Python 410 PASS, yeni hedefli 46 PASS, App hedefli 87 PASS, Kits hedefli 24 PASS, canonical mypy 537 dosya ve TS/lint PASS burada yeniden çalıştırılmadı. İlk tam App koşusunun 1042 PASS/3 FAIL sonucu ile reasoning uyumluluk düzeltmesi ve diğer iki başarısızlık grubunun izole 48 PASS sonucu ayrı tutulmalıdır. İlk Kits koşusunun 360 PASS/4 timeout sonucu çözülmüş sayılmaz. Son seri tam App/Kits koşuları, tam Python kapısı ve live/native kabul bu kararın dışındadır. Legacy call/event/sequence yokluğunda aynı metadata taşıyan tekrar çağrıların ayrıştırılamaması mevcut belgelenmiş uyumluluk sınırıdır.

## Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: APPROVE — yalnız bu P4 statik kaynak incelemesi; tamamlanma veya tüm testlerin geçtiği iddiası değildir.
