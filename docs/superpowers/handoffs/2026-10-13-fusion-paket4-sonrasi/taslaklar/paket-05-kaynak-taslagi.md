# Paket 5 uygulama taslağı — onay, soru, ses ve aktif göreve talimat

Kaynak: plan Paket 5; rapor U33–U35/E15–E22/R09/R15/R32; karar D03 ve Paket 2/D01 korelasyonu; kabul A08–A11/A32. CLAUDE.md/RULES.md okundu. Yalnız kaynak incelemesi: ürün/test/credential erişimi yok. Paket 2–4 final interface'lerinin üstüne uygulanır; diğer agent değişiklikleri korunur.

## Mevcut otoriteler ve gerçek açıklar

| Kaynak / sembol | Mevcut davranış | Minimal düzeltme |
|---|---|---|
| `engines/agent/approval.py::ApprovalPolicy/build_policy` | Karar tek policy'de; ALLOW/DENIED/BLOCKED ayrı | Aynı otorite genişler; UI/voice izin üretmez |
| `ApprovalMemory::_scopes`, `_scope` (~388) | Shell alias'ları kanonik run_shell:exact-command; diğer scope yalnız tool.name | Shell scope korunur; remote scope server/account/action/normalized-target fingerprint olur |
| `ApprovalMemory` | Remember/is_remembered var; revoke/clear/revision yok | Exact scope revoke + clear; policy değişimi effective decision'a bağlanır |
| `resolve_request` (~276) | effect_resolver doğrudan await; timeout/exception typed blocked sonucu yok | Config budget ile bounded resolver; error/timeout fail-closed, executor yok, görünür reason |
| `_AskingApproval.decide/_ask_and_remember` | preallowed/auto/session/once kaynağı ayrı kayıt olarak çıkmıyor | Additive decision evidence; aynı policy kararından kaynak/gerekçe üret |
| `loop.py::_execute_checked` (~2995) | resolve→policy await→ToolStarted→execute; approval sonrasında yeni steer/policy revision kontrolü yok | Güvenli boundary revalidation; beklerken değişen talimat/target/authorization eski cevabı kullanamaz |
| `appserver.bridges::PendingQuestions` | Sayısal sayaç, questionId→future; resolve pop eder; turn/decision korelasyonu yok; cancel_all boş dict | Paket 2 attempt namespace'i; typed lifecycle ve dedup decision; tek terminal transition |
| `ProtocolPrompter::_ask_wire` | Yalnız payload/id ve indefinite await; finally discard, genel terminal closed event yok | Context session/turn/parent-tool-call ile sahiplik; answered/cancelled/timed-out/unavailable ayrı; kapalı olay tüm yollar |
| `ProtocolPrompter::confirm/ask` | confirm missing answer DENY; ask missing answer boş str | Unavailable/cancelled/timeout ile gerçek deny/text ayrı typed adapter |
| `AppSession::resolve_reply`, `_chrome_answer` | İkisi pending.resolve kullanıyor; Chrome başarılı cevap SoruKapandi yayınlıyor; genel receipt yok | Tek answer authority helper; kaynak UI/Chrome/voice aynı validation/dedup/receipt |
| `appserver/server.py::serve` | Legacy cevap envelope ack beklemez; hatalı id ProtocolError | Legacy envelope korunur; yeni istemci typed question answer request veya correlated ack event kullanır |
| `sessions/useSessions.ts::answer` | Aktif question'ı okur, client.reply void gönderir, kartı hemen null yapar | Explicit expected question/turn/decision ID al; host accepted/terminal sonrası kapat; failure retry |
| `dialogs/Approval.tsx` | onCevap void; Other state mount-only; numeric Other serbestCevap=false iken de açılır; double click guard yok | Correlated identity prop/key, pending ref guard, result/promise adapter, disable/visible retry |
| Approval Escape | Soru boş metinle atlanır; deny yoksa noop fakat hint kapat | Skip/cancel typed; deny yoksa gerçek close callback veya açık Esc işlevsiz metni; önerilen seçenek timeout cevabı değildir |
| `SessionApplication.tsx` voice ask/answer (~1059) | VoiceAsk kimliksiz; answer yalnız string; soruTuruRef güncel sorunun türünü kullanıyor | VoiceAsk + VoiceAnswer sessionId/turnId/questionId/decisionId taşır; eski evet yeni soruya uygulanmaz |
| `voice/VoiceWindow.tsx` | matchSpokenAnswer belirsiz konuşmayı reddeder; kimi branch askRef'i kapatıp emit'i await etmiyor | Recognition başlangıcındaki soru snapshot'ı doğrula; host ack gelene kadar pending; emit fail kart/cevap korunur |
| `core/steering.py::SteeringQueue` | string queue; drain user harness-note mesajları üretir | Aynı queue typed item ID/parent-turn/boundary receipt ile genişler; ikinci steering queue yok |
| `loop.apply_steering`, `_drive` (~1088) | Yalnız sonraki model çağrısından önce drain | Model yanıtından sonra ve her mutation öncesi de kontrol; stale tool batch yeni talimattan sonra kör yürütülmez |
| `cli/session.py::run_agent_task` → AgentDeps | AgentDeps steering alanı mevcut fakat run_agent_task parametresi/wiring yok | Optional steering parametresi ekleyip aynı AgentDeps'e geçir |
| `appserver/session.py` / App controller.send | Desktop steering route yok; mevcut busy send bağımsız queue | D03 varsayılan aktif göreve ek talimat; ayrı sonraki görev queue eylemi; mevcut queue mekanizması korunur |
| `engine_tools.py::UserAsker`, `_ask_user_tool` | ask str döner; required/optional/recommended semantics yok; her soru await bloklar | Typed result ve question spec; required dependent work bekler; optional ayrı owned pending task |
| `clarify.py::clarification_hint` | İlk tur/yeni proje/200 karakter sınırı; uzun ama veri kaynağı eksik yeni proje kaçıyor | Kritik eksik bilgi/önceden verilmiş karar kontrolü; uzunluk tek karar ölçütü olmaz |
| `core/checkpoint.py::WorkflowCheckpoint` | Question kararları yok; mevcut plan/evidence/budget/repair snapshot var | Additive typed question decision ledger; aynı checkpoint/store migration, ikinci karar deposu yok |

## Core sözleşmesi ve migration

- `core/question.py` gerekirse küçük frozen QuestionContext, QuestionSpec, QuestionResult, DecisionReceipt, AuthorizationScope. Context: session/conversation, parent task/attempt/turn, question ID, tool call ID, authorization revision. Terminal: answered/denied/cancelled/timed-out/unavailable/skipped; pending/sending UI state bunlardan ayrı. Unknown kritik decision reddedilir, additive alanlar tolere edilir.
- Wire Türkçe mevcut `cevap.id`, `secim:once/session/deny`, `metin` korunur. Context ve karar kimliği additive alanlarla taşınır. Yeni `soru.cevapla` request en küçük host-ack yolu olabilir; legacy Reply aynı helper'a normalize edilir. Client.reply erken kart temizleme otoritesi olmaz.
- Question ID mevcut sayaçtan üretilebilir fakat Paket 2 attempt namespace'iyle ayrıştırılır; yeni parallel UUID üreticisi yok. decisionId UI mevcut identity helper'ından bir kez alınır; retry korur. Aynı decision duplicate aynı receipt; farklı cevabı aynı kapalı question'a göndermek stale/closed olur. Terminal future iki kez çözülemez.
- Legacy context'siz reply yalnız mevcut canlı backend generation'ındaki exact pending ID'ye uygulanır; restart sonrası aynı sayısal id yeni soruya çevrilmez. Voice string legacy payload yeni correlated prompt'u yetkilendiremez; yeniden metin kartından cevap istenir.
- Required soru timeout/skipped ile dependency açılmaz. Optional öneri ancak açık kullanıcı Sen seç/Önerinle devam et kararıyla assumption olur; otomatik timeout recommended etiketi text cevabı sayılmaz. Yeni timeout sayısı uydurma; mevcut turn deadline/konfigürasyon kullanılır.
- `UserAsker` str→typed migration adapter'ı tek yerde; TUI/plain prompter'lar ve test fake'leri uyarlanır. ApprovalAnswer bool legacy uyumu tek normalize fonksiyonunda; UNAVAILABLE gerçek DENY'ye çevrilmez.

## AuthorizationScope ve revocation

- Tool name ayrıştırması tek başına remote target/account kapsamı olamaz. MCP adapter zaten server ve ability context'ini bilir; Tool'a optional typed scope resolver/metadata eklenir ve `ApprovalRequest` bunu taşır. Server/connector identity, account/profile, action/ability, normalized target/resource set kullanılır. Ham args JSON veya credential hash'i scope key'e girmez.
- Scope çözülemeyen remote write yalnız once alabilir; session-wide yetki uydurulmaz. Provider/adapter normalizer hedef canonicalization'ını bilir; engine key adlarıyla hesabı tahmin etmez. Geniş session izni kullanıcı seçiyorsa kart gerçek kapsamı açık metinle gösterir.
- Exact shell komut scope'u ve alias canonicalization testleri korunur. Remote destructive her çağrıda yeniden sorulur, session olarak remember edilmez. Mevcut bypass policy davranışı ile repo destructive approval kuralının çelişkisi fixture/release notunda açıkça çözülmeli; blanket bypass otomatik güvence diye gösterilmez.
- ApprovalMemory owner mevcut ReplState'tir. Revoke/revision bu owner'a eklenir; süreç-global bellek yok. Plan mode legacy allow'u yazma iznine çeviremez. Aktif policy snapshot'ı değişirse tool boundary current revision'ı kontrol eder; AppSession→AgentDeps injected authority accessor/owned policy holder kullanılır, engines üst katmanı import etmez.
- Approval beklerken hedef/argüman/remote session değişmişse request fingerprint'i farklıdır; eski once receipt kullanılamaz. Modelden gelen yeni args ayrı call/request'tir. Aynı args nesnesi mutable kaldığından onaya sunulan snapshot frozen/canonical olarak bağlanır; execute aynı snapshot'ı kullanır.
- Resolver exception/timeout BLOCKED reason olarak döner, ALLOW listesine düşmez. Cancellation yeniden raise edilir. Kullanıcı deny turu mevcut denial modülü gibi durdurur; blocked alternatif read/plan yoluna izin verebilir.

## D03 aktif göreve talimat

1. App `send` busy ise explicit mode=steer varsayılan; bağımsız queue ayrı etiket/eylem. Hedef parent task/attempt UI+host kimliğinden gelir; model mesaj sınıflandırması hedef seçmez. Stop mevcut `tur.kes` cancellation'dır; Durum read-only projection ayrı eylemdir.
2. AppSession active turn'e owned SteeringQueue oluşturur, `run_agent_task(... steering=...)` ile geçirir. Additive `tur.yonlendir` route exact active task/turn doğrular; Paket 2 submission ID ile dedup, queued/applied + boundary receipt. İkinci runtime/task yaratılmaz; parent budget/checkpoint sürer.
3. Provider await sürerken gelen talimat queue'ya kaydolur. Yanıt geldikten sonra tool batch yürütülmeden drain edilir. Eski model tool kararları bu talimattan önce üretildiğinden mutating batch yeniden modele değerlendirilir; yalnız talimatı messages'a ekleyip stale tool.execute çağırmak yeterli değildir.
4. Approval pending iken steer pending request'i obsolete yapar; future typed cancelled/invalidated kapanır, eski once cevabı uygulamaz. Yeni hedef için yeni soru gerekir. Yeni policy revision da aynı revalidation boundary'den geçer.
5. In-flight external iş geçmişe dönük iptal sayılmaz. Başlatılmış/tamamlanmış effect receipt görünür; undo mevcut ayrı onaylı workflow. Doğal dil Bunu yapma exact pending target için kısıt, belirsiz hedef için yeni mutation gate + kısa required question; host Stop inference'a bağlı değildir.
6. Yazılı durum sorusu parent görevi tamamlamaz/yenisini başlatmaz. Steering receipt hangi görev/boundary'ye uygulandığını gösterir; mevcut user harness-note history/checkpoint akışı korunur.

## Optional sorular ve karar checkpoint'i

- Tek pending soru singleton'a zorlamayın: App SessionQuestion presentation queue owner olabilir; host PendingQuestions tablosu otorite olarak kalır. Optional question owned task bağımsız read/plan işini bloke etmez; required dependency mevcut ExecutionPlan step/depends_on üzerinden bekler. Genel yeni scheduler yazılmaz.
- `QuestionSpec` required/dependency key ve explicit assumption policy taşır; ask_user tool args bunları verir. Response optional pending ise tool result kullanıcıya cevap uydurmaz; model gerekli bağımsız işe yönlendirilir. Her pending task turn sonunda await/cancel edilir.
- Checkpoint kararları question ID/semantic decision key/revision/source/assumption ile saklar; sensitive free-text raw cevap için existing redaction uygulanır. Ham credential veya onay token saklanmaz. Resume aynı valid kararı tekrar sormaz; yeni user steer revision eski cevabı supersede eder. Tool session izinleri restart'ta kör restore edilmez; typed question preference ile authorization receipt ayrı tutulur.
- Clarify kritik data source/account/target eksikliğini değerlendirir; mevcut project marker + history kararlarını kullanır. Önceden belirtilmiş teknoloji tekrar sorulmaz. Model önerisi izin scope'u genişletmez.

## Dosyalar ve sıra

1. Core: `question.py`, `steering.py`, `checkpoint.py`, `tools.py` typed scope resolver, Paket 2 event correlation types. RED fixture'lar önce.
2. Approval: `engines/agent/approval.py`, loop `_execute_checked/_run_tools/_drive`, `denial.py` existing mapping; typed resolver blocked ve live revision guard.
3. Question: `engine_tools.py`, `clarify.py`, existing TUI/plain UserAsker implementations, `memory/checkpoint_store.py` additive migration.
4. Host: `appserver/bridges.py::PendingQuestions/ProtocolPrompter`, `session.py::resolve_reply/_chrome_answer/_dispatch/_run_turn`, `server.py` legacy reply compatibility, `approval_summary.py` scope/evidence redaction; `cli/session.py` steering injection.
5. App: `protocol/types/client`, `sessions/types/store/useSessions::answer/send`, `dialogs/Approval`, `SessionApplication` both Approval call sites and voice; `voice/bridge/VoiceWindow/VoiceMode`. Onay kimliği key veya explicit reset prop; pending ref immediate guard; focus return question transition'da yeni kartı çalmamalı.
6. Kits `fusion/session.ts::reply`, `fusion/service.ts::answer` mevcut runId/questionId kontrolü korunur; decision receipt sonrası question queue shift. Aynı core host otoritesine voice/text adapters bağlanır; yeni Kits permission engine yok.

## RED→GREEN kabul/testler

- `test_agent_approval.py`, `test_approval_modes.py`: A account scope B'yi kapsamaz; target/action değişiminde yeniden sor; aynı safe scope sonraki tur geçerli; exact shell alias dar kapsam; destructive session hatırlanmaz; revoke/policy plan change; effect resolver timeout/exception executor yok; allowed source evidence redacted.
- Yeni `test_question_lifecycle.py`, `test_appserver_session.py`, bridge/protocol fixture: aynı decision duplicate tek resolve; pending stop→late once executor yok; wrong turn/question/generation stale; answered/cancelled/timeout tek terminal; legacy transcript/client uyumu; lost answer-ack retry aynı receipt.
- `test_agent_loop.py`, existing `test_steering.py/test_steering_wiring.py`: gerçek AppSession→run_agent_task→AgentDeps wiring (mevcut wiring tests yalnız apply_steering helper'ını test ediyor); fake provider barrier steer sonrası stale mutating batch çalışmaz; pending tool/approval steer; in-flight receipt; parent task/budget korunur; independent queue ve status/stop ayrı.
- `test_clarify.py`, `test_checkpoint_store.py`: uzun yeni proje missing data tek soru; existing detailed project gereksiz teknoloji sorusu yok; resume decision tekrar yok; newer steer revision önceki kararı ezer; optional timeout default approval olmaz; bağımsız iş optional soru sırasında sürer, required dependent effect bekler.
- `Approval.test.tsx`: q1 Other text q2'ye taşınmaz; serbestCevap=false numeric Other kapalı; rapid click/keyboard tek answer; failed receipt retry; pending disabled; deny seçeneği olmayan kart Escape metni/action doğru; close focus return; recommended yalnız öneridir.
- Voice bridge/VoiceWindow fake: late evet q2'yi onaylamaz; recognition boyunca soru değişimi stale; UI+voice eşzamanlı tek decision; belirsiz transcript effect yok; emit failure soru korunur; mic denial text card erişilebilir; TTS fail text silinmez; hangup host turn cancellation'a ulaşır.
- App/Kits correlated protocol transcript ve full gates; gerçek mikrofon/native smoke ayrı kayıt. Release notu policy scope/revocation/D03 busy-send davranış değişimini açıklar. Ürün uygulaması başlamadan root gate beklenir; ağır testleri yalnız root sıralar.
