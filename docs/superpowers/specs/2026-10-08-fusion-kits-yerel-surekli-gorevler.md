# Fusion Kits: yerel sürekli görev ve yetenek planı

Kullanıcı, Dots’un yayımlanmış yeteneklerinin Fusion Kits’te gerçek araçlarla karşılanmasını istedi. Uzak makine ve sunucu maliyetini kesin reddetti. Bu tasarım yalnız mevcut bilgisayarda çalışır. Bilgisayar kapalıyken işlem yapmaz; görevleri kalıcı saklar, yeniden açılışta bekleyen işleri ele alır. Model, sağlayıcı, bağlam, retry, fallback ve bütçe ayarları değiştirilmez.

## Araştırma sonucu

Dots; hedefleri görevlere böler, zamanlanmış işler yürütür, bağlam ve not tutar, bağlı araçları kullanır ve etkinliği gösterir. Bir koşunun bitmesi hedefin gerçekleştiğini kanıtlamaz. [Görev ve bellek belgeleri](https://learn.chatgpt.com/docs/dots/tasks-and-memory).

Proaktif araştırma salt okunur sınırlar içinde yürütülür; takip eylemleri ayrı yetki gerektirir. İzin denetimi ajan tarafından değiştirilemeyen yürütme katmanında uygulanır. [Güvenlik açıklaması](https://openai.com/index/how-we-build-safety-security-and-privacy-into-dots/).

Bilgisayar kapalıyken devam etme Dots’un ayrı bulut bilgisayarına dayanır. Yerel bilgisayar erişimi, bağlı ve açık bilgisayar gerektirir. Fusion için bu altyapı alınmayacaktır. [Bilgisayar ve uygulama belgeleri](https://learn.chatgpt.com/docs/dots/computers-and-apps).

Bunlar yayımlanmış davranışlardır; kapalı iç scheduler, bellek veya reviewer API’lerinin birebir uygulaması biliniyor sayılmaz.

## Mevcut yapı ve tamamlanacak davranışlar

| İstenen davranış | Mevcut yapı | Tamamlama ölçütü |
|---|---|---|
| Kalıcı görev ve zamanlama | Kits SQLite Store/Runner lease, CLI schedule | Teslim sırasında crash olsa da görev kaybolmaz; tekrar teslim tek görev oluşturur. |
| Kesinti sonrası devam | Kits kalıcı sohbet, CLI checkpoint | Tamamlanmış yan etki yeniden yapılmaz; belirsiz sonuç doğrulanmadan başarı sayılmaz. |
| Araştırma | Kits research/parallel/public page tools | Canlı kaynak kanıtı korunur; sample veri canlı sonuç değildir. |
| Kod ve proje | Kits FusionService/FusionSession delegasyonu | Doğru proje/izin bağlamında gerçek çıktı ve sonuç kanıtı. |
| Belge ve içerik | Space page CRUD | Saklanan belge kimliği doğrulanır; PDF/PPTX/XLSX/DOCX ayrıca gerçek executor gerektirir. |
| Bilgisayar kontrolü | ComputerService ve CLI macOS AX/Quartz | Bağlı yerel araç, izin ve snapshot doğrulanır; desteklenmeyen platform dürüstçe belirtilir. |
| Uygulamalar ve MCP | CLI MCP discovery/registry | Kits’e yalnız gerçekten bağlı executor aktarılır; hesap varmış gibi davranılmaz. |
| Bellek ve tercihler | Kits learning/workspace ve CLI memory | Owner izolasyonu, kaynak ve silme kapsamı; sır saklanmaz. |
| Çok proje ve alt görev | Dot/thread ownership, Fusion delegasyonu | Proje kökü ve devredilen yetki korunur; farklı hedeflerin belleği karışmaz. |
| Proaktif takip | Mevcut araştırma kuyruğu | Salt okunur registry; araştırma bulgusu mesaj gönderme veya mutation yetkisi üretmez. |
| Ses ve kanallar | Mevcut voice/Slack yolları | Gerçek transport, owner, iptal ve kalıcı teslim; bağlı olmayan kanal unavailable. |
| Kalite ve teslim | CLI evidence/ledger/job delivery | Kits çıktıları aynı gerçek kanıt mantığına bağlanır; araç çağrısı tek başına tamamlanma değildir. |

## Uygulama sırası ve sahiplik

1. comparison_plan: CLI zamanlama için dayanıklı occurrence/pending/ack kaydı. Takvim ilerlemesi ve pending tek atomik yazım. Mevcut zamanlama davranışı ve aralıklar korunur. Yeni yürütme motoru oluşturulmaz.
2. animation_diagnosis: Kits gerçek DotAgent executor listesine bağlı sürümlü yetenek sözleşmesi. Eksik araç, izin ve sample/live ayrımı çalıştırma öncesinde görünür olur. Kullanılmayan paralel katalog kurulmaz.
3. Root ve bağımsız reviewer: yerel görev aktarımı için proje/thread bağlamını tasarlar; mevcut Kits lease otoritesine idempotent handoff bağlar. RAM-only frontend tesliminin yerini durable teslim alır.
4. Kesinti/izin/bellek izolasyonu ve gerçek çıktı kanıtları tamamlanır. Belge, kanal ve MCP açığı ayrı bounded fazlarla kapatılır.
5. Her yetenek için gerçek yerel senaryo yürütülür; yapılandırılmamış dış servis tamamlandı sayılmaz. Önceki dört üretim alanı ve eşkoşullu göreli %90 hedefi ayrıca doğrulanır.

Her kodfazı önce davranışın kırıldığı test, sonra ilgili testler, format/lint/tip denetimi, bağımsız review ve Türkçe yerel commit ile kapanır. Ürün çıktısına elle yama yapılmaz. Ağır koşular tek ve sıralıdır. Yerel sunucunun açılışta başlatılması sistem ayarı gerektiriyorsa somut kurulum hazırlanır; gizlice servis kurulmaz.

## İlk kabul senaryoları

- Vadesi gelen iş alındıktan sonra uygulama kapanır: yeniden açıldığında pending kayıt bulunur.
- Teslim başarılı ama ack cevabı kaybolur: yeniden teslim aynı görev kimliğine gider.
- İzin kaldırılır veya görev durdurulur: eski lease sonucu kabul edilmez.
- Kit talimatında araç adı vardır ama executor yoktur: çalışabilir ilan edilmez.
- Sample araştırma ve başarısız delegasyon: doğrulanmış teslim üretmez.
- Bilgisayar uyur/kapanır: bekliyor gösterilir; çalışıyor veya tamamlandı gösterilmez.

Bu belge uygulama planıdır; yeteneklerin tamamlandığına ilişkin kanıt değildir.
