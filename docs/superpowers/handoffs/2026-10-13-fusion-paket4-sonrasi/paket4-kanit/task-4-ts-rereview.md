# Paket 4 sınırlı TypeScript yeniden incelemesi

Karar: **APPROVE — önceki 1 HIGH ve 2 MEDIUM kapandı; incelenen düzeltmelerde yeni somut bulgu yok.** Yerel çalışma ağacı incelendi; PR merge readiness uygulanmaz. Ana CLAUDE.md/RULES.md, önceki TS raporu ve inline düzeltme raporu okundu. İnceleme yalnız önceki bulgular, düzeltmelerin doğrudan veri akışı ve useActiveModel sahiplik sözleşmesiyle sınırlıdır. Ürün/test değişikliği, kurulum, test koşusu, commit veya alt ajan yok.

## Kapanan bulgular

- **Yoğunluk seçimi:** Models artık Settings.selectMode üzerinden çalışıyor. Aynı işlem koruması tekrar çağrıyı engelliyor; typed command sonucu await ediliyor, ok:false/rejection mevcut tek hata/retry alanına gidiyor; başarı sonrası load gerçek kontrol snapshot'ını yeniliyor. Owner generation eski istemci sonucunu düşürüyor, pending seçimi ve ilgili düğmeleri kapatıyor. Yeni Settings.effort testleri başarılı yenileme, pending tekrar ve reddedilen komutun aynı komutla retry davranışını kapsıyor; mevcut operasyon koruma testleriyle birlikte okunmuştur.
- **Action Enter:** ModelPicker keyboard handler artık yalnız arama input'una bağlı. Retry/connect düğmelerinin Enter olayı üst menü tarafından yakalanmıyor; native düğme aktivasyonu model seçimiyle yer değiştirmiyor. Saf ARIA incelemesi React reviewer kapsamındadır.
- **Yoğunluk makbuzu:** App olayMetni ve Kits FusionCard requested/applied effort değerlerini reason boşken de gösteriyor. Eksik/null applied değer desteklenen bir düzeyle doldurulmuyor; “gönderilmedi” olarak sunuluyor. Eksik requested değer “doğrulanamadı” olarak sunuluyor. İki değer de yoksa sahte yoğunluk makbuzu üretilmiyor.
- **Kits kimliği:** Normalizer call_id, ardından event_id kullanıyor; legacy fallback session/turn/sequence ve model/effort metadata üzerinden deterministik anahtar üretiyor. FusionCard makbuz key'i callId, index değil. Mevcut servis session/turn filtresi ve callId upsert korunuyor.

## Aktif model sözleşmesi

useActiveModel mevcut kontrol isteğinin ince adaptörüdür. Snapshot istemci ve oturum sahibiyle tutuluyor; render sırasında sahibi farklıysa boş/unknown model dönüyor. Effect cleanup geç eski sonucu düşürüyor. Aynı sahibi yenileme reddedilince son doğru model korunuyor; yeni sahibin başarısız yanıtında önceki sahibin modeli gösterilmiyor. SessionApplication tek producer'ı kullanıyor; ikinci store/request yolu eklenmemiş. Bu davranış için eklenmiş iki sahiplik testi okundu; testler yeniden çalıştırılmadı.

## Doğrulama ve sınırlar

- App Node 22: mevcut kurulu tsc --noEmit ve eslint src **exit 0**; 0 error, mevcut AccountScreen.tsx:40 unused-disable warning.
- Kits önceden kurulu Node 24: mevcut kurulu tsc --noEmit ve canonical eslint src tests scripts vite.config.ts **exit 0**, uyarı yok.
- Root'un App 87 / Kits 24 PASS kanıtı tekrar koşulmadı. Full gate, build, Python/backend authority ve live/native doğrulama bu raporun onayı kapsamında değildir.
- Legacy olayda call/event/sequence yoksa aynı metadata'ya sahip gerçek tekrar çağrılar tamamen ayrıştırılamaz; raporlanan uyumluluk sınırı korunuyor. Yeni üretimde call_id otoritesi kullanılır.

Bu karar yalnız belirtilen TS düzeltmelerinin onayıdır; tüm Paket 4 için tamamlanma veya canlı çalışma iddiası değildir.
