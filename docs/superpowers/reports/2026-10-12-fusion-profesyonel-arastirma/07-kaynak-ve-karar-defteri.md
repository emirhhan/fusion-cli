# Kaynak, karar ve bağımsız inceleme defteri

## Kanıt sınıfları

- **Ölçülen:** bu oturumda App Node22 testleri, App/Kits TypeScript, Python tam koşunun üç hatası, gerçek Gemini OK ve fallback.
- **Kaynakta görülen:** U/E/K incelemeleri; kaynak ve test tanımı, runtime başarı iddiası değil.
- **Görsel araştırma:** mevcut depoda kaydedilmiş screenshot fixture'larının gözle incelenmesi; yeni canlı ekran değil.
- **Dış resmî kaynak:** aşağıdaki belgeler 12 Ekim 2026 tarihinde açılarak kontrol edildi. Kaynak erişimi ürün aboneliği/yetenek erişimi kanıtı değil.
- **Öneri:** R listesi, paket planı, yeni interface alanları ve aşağıdaki ürün kararları. Bunlar kullanıcının geçmişte söylediği kararlar diye sunulmaz; araştırmacının uygulamayı netleştiren önerileridir.

## İnceleme sonrası netleştirilen sözleşmeler

Bu bölüm, R08/R09/E02 ve Paket2/5/6'daki genel ifadeleri kesinleştirir. Katalogda bunlarla çelişen kısa ifade varsa burada yazan davranış uygulanır.

### D01 — Kalıcı gönderim tekilleştirme

**Önerilen karar:** tekilleştirme otoritesi host/backend'dir; UI düğmesini kapatmak yeterli değildir. Mevcut conversation/task persistence'e typed receipt adapter eklenir; ikinci agent runtime yapılmaz.

- Anahtar: host kullanıcı profili + kanonik workspace/project kimliği + conversationId + requestId. UI requestId ilk gönderimde üretir ve retry'da korur; backend kabulü aynı anahtarla atomik kaydeder.
- queued/accepted/running aynı kimlikle tekrar gelirse mevcut receipt döner; yeni task açılmaz. completed/cancelled/failed terminal receipt aynen döner, implicit replay yapılmaz.
- Kullanıcının açık “yeniden dene” eylemi aynı **task** altında yeni attemptId oluşturur. Aynı attemptId duplicate gelirse yine aynı receipt. Request submission dedup ile tool side-effect dedup farklı seviyelerdir; ilki ikincisini garanti etmez.
- Core/app restart sırasında unfinished receipt “sonucu belirsiz / kurtarma gerekli” olarak restore edilir; otomatik failed veya completed yapılmaz. Yerel kuyruk kabulü hiç gerçekleşmemişse aynı requestId ile gönderilebilir; kabul edilmiş belirsiz iş önce observation/checkpoint ile ele alınır.
- Dış etki gerçekleşmiş olabilir: external idempotency key/receipt varsa onu doğrula; yoksa mevcut recovery OBSERVE_FIRST yolunu kullan. Sonuç gözlenemiyorsa otomatik yeniden yazma yok; kullanıcıya somut belirsizlik ve karar sunulur.
- Receipt saklama: transcript/checkpoint yaşam döngüsüne bağlı. Unfinished/ambiguous kayıt kullanıcı açıkça çözene veya ilgili konuşmayı yetkili biçimde silene kadar TTL ile düşürülmez. Terminal receipt, konuşma saklandığı sürece korunur. Uygulamanın mevcut retention politikasında konuşma silinirse aynı kimliği tekrar üretme; sonraki bağımsız işe yeni requestId ver.
- Test: accepted write+lost response+restart+retry yalnız bir executor effect. UI crash ve backend crash ayrı fixture. Terminal failed tekrar isteğinde yeni attempt açık eylem olmadan açılmaz.

Sayı temelli retention günü bu araştırmada uydurulmaz. Storage quota/migration uygulanırken kullanıcıya retention seçenekleri ayrıca ürün ayarı olarak sunulur; açık/ambiguous işin güvenlik kaydı silent eviction olmaz.

### D02 — MCP güven ve migration

**Önerilen karar:** yeni sunucunun başlangıcı “güven doğrulanmadı”. Yerel STDIO veya localhost olması otomatik güven vermez. Bağlandı/giriş yapıldı/trusted farklı alanlardır.

- Güven kullanıcı tarafından sunucu kimliği, origin/executable kaynağı ve açık yetenek açıklaması görüldükten sonra sunucu kapsamında verilir. Trust, bütün araçlara genel write izni değildir; mevcut ApprovalPolicy ayrı uygulanır.
- Mevcut configured sunucular migration'da legacy/unreviewed olarak işaretlenir. Daha önce kullanıcının açık verdiği dar izinler korunur; konfigürasyonda bulunmak yeni read exemption yaratmaz. Yeni/destructive/changing scope izin genişletmesi eski onaydan türetilmez.
- Güvenilmeyen sunucuda readOnlyHint yalnız iddiadır, tek başına onayı gevşetmez. Kullanıcı açık dar read scope allow vermişse o kayıt işler; bu legacy permission preservation davranışı “sunucu trusted” diye gösterilmez.
- Sunucu kimliği/origin/executable source veya araç etki sözleşmesi değişirse ilgili trust/allow scope yeniden değerlendirilir; her metin açıklama değişimi bütün izinleri silmez. Schema signature değişimi E03 denetimine girer.
- Çelişkili readOnly=true/destructive=true için öneri daha ihtiyatlı destructive kararıdır. Bu, standart zorunluluğu veya Codex davranışının bug olduğu iddiası değildir. Kullanıcıya politika değişikliği gösterilir.
- Onay fırtınasını önleme: bütün read çağrılarını “bu tur once” sormak yerine açık server+read scope izni ve iptal yönetimi sunulur. İlk trust gözden geçirme yapılınca sonraki aynı scope gereksiz tekrar sorulmaz.
- Test: existing explicit allow migration, unreviewed configured server, new local stdio, changed origin, contradictory annotations ve revoke. Bağlandı kartı trust rozeti üretmez.

### D03 — Çalışırken gelen mesajın otoritesi

**Önerilen karar:** aktif iş sırasında normal composer gönderimi varsayılan olarak **aktif göreve ek talimat**tır. Ayrı “Sonraki görev olarak sıraya ekle” eylemi bağımsız iş üretir. Gönderim yanında kısa mod etiketi görünür; kullanıcı tercihine göre varsayılan değiştirilebilir. Bu, bugünkü queue-only davranışını değiştiren yeni ürün kararıdır.

- Talimat güvenli tool boundary'de ana döngüye eklenir; host queued/applied receipt verir. Model yanıtı gelmeden veya sıradaki mutasyon başlamadan yeni talimat kuyruğu kontrol edilir. Already running dış işin geçmişteki etkisi bu mesajla geri alınmış sayılmaz.
- Kesin iptal için mevcut **Durdur** eylemi host cancellation'dır ve model sınıflandırmasına bağlı değildir. Doğal dil “bunu yapma” yeni kısıt olarak ana modele taşınır; hedef tekil ve belliyse pending scope durdurulur. Belirsiz hedefte yeni dış mutation bekletilip kısa soru sorulur. İn-flight tamamlanan etki “talimat gelmeden başlamış/tamamlanmış” makbuzuyla görünür; undo varsa ayrı onaylı workflow.
- “Durum” UI eylemi read-only status projection'ıdır. Yazılı durum sorusu agent tarafından yanıtlanırken original task korunur; status cevap yeni task tamamlanması sayılmaz.
- Mesaj hangi işte uygulandı ve hangi boundary'de alındı görünür. Kullanıcı görev değiştirmek istiyorsa açık sıra eylemi kullanır; model gizlice diğer conversation'a görev açmaz.
- Test: uzun fake provider beklerken steer, pending tool öncesi steer, in-flight external receipt, status preserved, independent queue ve stop. Parent task kimliği ve bütçe süreklidir.

Bu karar bütünüyle inference classifier'a bırakılmaz. Varsayılan göndermenin hedefi UI ve host kimliğinden bellidir; model sadece talimatın içeriğini yorumlar. Onay ve cancellation host sınırında kalır.

### D04 — Paket kapsamı ve token bütçesi

R22/R23 (öğretmen açıklaması/ders geri alma) P2; Paket7'nin zorunlu teslimi değil. Paket7 skill/ajan scope ve kanıt işlerini yapar. R24 task reçetesi Paket9'da yalnız teslim kanıtı uyumu, Paket14'te seçilen gerçek görevler kapsamında; geniş reçete kataloğu P2 olarak kalır.

Mevcut TurnBudget token sayacı içermez. E12'nin token ortak tavanı yeni additive usage entegrasyonu önerisidir. Provider token usage bildirmiyorsa kesin token üst sınırı kanıtlanamaz; mevcut çağrı/doğrulama/süre sınırları yine uygulanır. UI unknown maliyeti veya token'ı sıfır gibi göstermemeli.

### D05 — MCP yeni ve eski adapter

Yeni 2026-07-28 protokol ile legacy initialize/initialized akışı ayrı desteklenir. Yeni adapter handshake/Mcp-Session-Id göndermez; protokol version, method/name headers, `_meta`, optional `server/discover` fixture'ı vardır. Legacy adapter eski sunucuları çalıştırır. SDK sürüm destek matrisi yapılmadan mevcut initialize yolu silinmez. Bu ayrı migration paketidir; günlük MCP hardening'e sıkıştırılmaz.

## Resmî kaynaklar ve kullanım amacı

| Kaynak | Raporda desteklediği dar ilke |
|---|---|
| [OpenAI GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) | low desteği, none/minimal ayrımı ve Responses tool-calling; hesabın ücretsiz erişimi iddiası yok |
| [ChatGPT projects](https://learn.chatgpt.com/docs/projects) | proje/sohbet/dosya/talimat bağlamı |
| [Agent approvals](https://learn.chatgpt.com/docs/agent-approvals-security) | izin ile teknik sandbox ayrımı; read annotation önceliği örneği |
| [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) | STDIO/Streamable HTTP ve authentication; host ortak config yaklaşımı |
| [Build skills](https://learn.chatgpt.com/docs/build-skills) | progressive disclosure ve explicit/implicit skill |
| [Image generation](https://learn.chatgpt.com/docs/image-generation) | referans, viewer, yorum ve seçili görsel iş akışı |
| [Claude permissions](https://code.claude.com/docs/en/permissions) | host tarafından izin enforcement; prompt grant değil |
| [Claude checkpointing](https://code.claude.com/docs/en/checkpointing) | kod/konuşma/summarize farklı rewind türleri |
| [Claude subagents](https://code.claude.com/docs/en/sub-agents) | izole alt görev context/scope yaklaşımı |
| [Claude skills](https://code.claude.com/docs/en/skills) | skill workflow ve subagent farkı |
| [MCP annotations](https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/) | hint≠enforcement, untrusted beyan |
| [MCP2026 duyurusu](https://blog.modelcontextprotocol.io/posts/2026-07-28/) | stateless yeni core ve migration zorunluluğu |
| [Agent Skills formatı](https://agentskills.io/specification) | frontmatter ve progressive yükleme; allowed-tools experimental |
| [MCP skills extension](https://skills.extensions.modelcontextprotocol.io/specification/stable/skills) | per-origin namespacing, remote allowed-tools implicit grant değil |
| [WCAG2.2](https://www.w3.org/WAI/WCAG22/quickref/) | erişilebilir UI kabulünün kapsamı |

## İnceleme sonucu

Bağımsız builder, D01/D02/D03 açıklarını ve R22/R23 kapsam çelişkisini buldu. Yukarıdaki önerilen ürün kararları ve plan güncellemesiyle giderildi. Teknik reviewer E12 token sayacı ve E24 unknown-tool davranışının yanlış çağrışımlarını buldu; düzeltildi. Plan yolu düzeltildi. Her reviewer kaynak/document incelemesi yaptı; bu süreç ürün kodunun runtime doğrulaması değildir.
