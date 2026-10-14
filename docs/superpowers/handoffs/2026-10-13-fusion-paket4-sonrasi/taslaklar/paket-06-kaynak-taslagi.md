# Paket 6 uygulama taslağı — MCP güveni ve dayanıklılık

Kaynak: Paket 6/E01–E08/R17–R19/A17–A19, karar D02. CLAUDE.md/RULES.md okundu. Ürün/test/credential okuması yok. Legacy `ClientSession.initialize()` ve SDK taşıması korunur; yeni 2026 protokol adapter/handshake matrisi Paket 15'tir.

## Mevcut kaynak / minimal değişiklik

| Dosya / sembol | Kaynak bulgusu | Değişiklik |
|---|---|---|
| `config/models.py::McpServerConfig` | name/command/args/transport/url/OAuth scopes/env-name/token-env; trust/budget yok | Additive trust provenance + server budget alanları; secrets değerleri girmez |
| `config/loader.py::_build_mcp_servers`, `writer.py::write_mcp_servers` | Dataclass loader; writer explicit field listesi | Yeni metadata doğrulama/roundtrip; eski kayıt legacy/unreviewed; yeni local/HTTP unreviewed |
| `mcp_bridge/identity.py::connection_identity` | Duplicate eşlemesi URL normalize / npx flags / @latest normalize ediyor | Dedup kimliği korunur; güven parmak izi stricter source/revision kimliği, credential içermez |
| `tool_effect.py::effect_from_annotations` | readOnlyHint önce; destructive=true çelişkisinde REMOTE_READ | Destructive önce; trusted/explicit-scope olmadan read hint yalnız claim |
| `ability_effects.py::effect_from_ability_meta` | readonly önce; resolver cache ability name only; exception None fallback | Aynı ihtiyatlı effect helper; trust cap resolver sonucuna da uygulanır; schema/effect revision cache key |
| `client.py::RemoteTool/register_into` | server/name/schema/effect; namespaced tool; schema fingerprint yok | Canonical schema/effect signatures ve source identity; Tool approval scope Paket 5 sözleşmesinden |
| `McpClient::_connect_server` | Tek 10sn connect timeout; OAuth waiting deadline pause; SDK initialize mevcut | Config server connect budget; browser kullanıcı beklemesi mevcut ayrı üst sınırla korunur |
| `McpClient::list_tools` | Sayfalı list await unbounded; repeated cursor kontrolü var | Toplam discovery deadline tüm sayfaları kapsar; single page timeout ile sonsuz pagination yok |
| `McpClient::call` | call_tool unbounded; normalize_call_result isError korunuyor | Call deadline; timeout ambiguous effect olarak görünür; automatic retry write yok |
| `McpClient::__aexit__`, `_close_failed_stack` | Stack close unbounded | Supervisor'ın kendi task'ında bounded cleanup; failed-connect cleanup aynı budget |
| `pool.py::McpToolPool` | Sunucu başına supervisor, parallel opens, lock, draining set zaten var | Mevcut havuz genişletilir; ikinci pool/runtime yok |
| `_Parked`, `_is_parked`, `forget` | Permanent failure park; transient her sonraki tur tekrar | Server retry record + fake clock/jitter + bounded backoff; explicit reconnect reset |
| `ensure_mcp_tools` | Client'lar sequential register; exception diğerini koruyor; hanging list diğerlerini geciktirir | Discovery server bazlı bounded parallel; publish hazır araçlar partial başarıyla korunur |
| `_await_task/aclose` | Supervisor await/gather unbounded; repr(error) log var | Close deadline+cancel/drain own task; yalnız safe error kind/name log |
| `service.py::McpConnectionService` | Login task singleflight name bazlı; own statuses pool üstüne sürekli yazılıyor | Status observation zamanı/generation; eski probe yeni pool failure'ı maskelemez |
| `service::_probe_server` | Connect success sonrası list çağrısı; list fail await dışarı yükseliyor | Stage-specific status: connected transport/discovery failed/degraded; exception request'i topluca düşürmez |
| `oauth.py::oauth_provider_for` | Her factory SDK OAuthClientProvider ve KeyringTokenStorage(config.url) oluşturuyor; refresh repo içinde değil | Refresh transaction SDK auth-flow sınırında shared owner/coordinator ile korunur |
| `tokens.py::KeyringTokenStorage` | Keyring sync backend async metot içinde bloklar; token read/write ayrı; locks yok | Thread'e al, typed storage failure; coordinated compare/reload/write; secrets logging yok |
| `appserver/connectors.py::status_payload/_row_status/list_connectors` | state/tool_count/latency/message/kind projection; trust/auth/park nedeni yok | Additive typed health/trust/auth/provenance/retry-at projection |
| `ConnectorsScreen.tsx::ConnectorRow/STATE_LABELS` | Bound/login/timeout/error; bilinmeyen durum label undefined; parked/degraded/trust yok | Independent badges, retry/logout/trust/revoke; unknown safe label; tek satır fail bütün listeyi silmez |

## D02 güven migration ve kimlik

1. Trust üç durum: unreviewed/trusted/revoked; source legacy/new + reviewed identity/revision optional. Config mevcut diye trusted olmaz; STDIO/localhost özel muafiyet değildir. Login/connected/trusted ayrı alanlardır.
2. Duplicate `connection_identity` authorization kimliği değildir: @latest normalize ederek duplicate önlenebilir ama executable paket revision/source değişince güven yeniden incelenmelidir. Trust identity normalize URL origin+path (secret query temizlenmiş), command executable canonical source, package pinned source/revision ve provider/account içerir. Secret taşıyabilen args/header/token/URL credential query hash'i trust record'a kopyalanmaz.
3. Explicit user dar read allow kaydı Paket 5 AuthorizationScope üzerinden normalize edilip korunur. Bu depoda `config/permissions.py` mevcut kalıcı allow yalnız shell komutlarıdır; yeni MCP scope uydurularak legacy config allow sayılmaz. Var olan gerçekten explicit kayıt yoksa migration grant yaratmaz. OAuth `scopes` provider consent'tir, Fusion tool execution grant'i değildir.
4. Trust kullanıcıya server identity/origin/executable source ve capabilities açıklanıp açık eylemle verilir. Trust write permit değildir; tüm calls mevcut ApprovalPolicy'ye gider. Revoked/unreviewed read hint alone REMOTE_READ exemption açamaz. Onay fırtınası tek açık server+read scope grant ile çözülür; otomatik this-turn once grant yok.
5. Description metni değişmesi bütün izinleri silmez. InputSchema canonical signature ve effect contract signature değişimi targeted revision yaratır; source identity/account/origin değişiminde ilgili trust+allow yeniden gözden geçer. Schema validation ToolRegistry mevcut validator'ıyla yapılır; yeni JSON schema validator açılmaz.
6. `Tool` Paket 5 metadata/scope resolver ile server/effect/signature taşır. Trust effect gating keşifte ve dynamic ability resolver sonunda TEK helper'dan geçer; cache eski trusted decision'a dönemez. readOnly=true+destructive=true REMOTE_DESTRUCTIVE; absent/malformed hints conservative unknown/write. Bu Fusion ürün politikasıdır; standart veya Codex ihlali iddiası değildir.
7. Remote skill origin/version/trust R19 metadata'sı Paket 7 skill loader'ına taşınır; burada ikinci skill loader yapılmaz. Uzak allowed-tools metni execution authority olmaz.

## Bütçe, backoff ve teardown

- Frozen server budgets connect/list/call/close; Config default tek kaynaktan. Var olan connect 10sn davranışı referanstır; yeni call/close değerleri gerekçeli mevcut config/turn-deadline sınırından seçilir, taslak yeni magic sayı vermez. Her operation turn remaining ile bounded; interactive OAuth user wait network budget'den ayrı.
- List total deadline + repeated cursor mevcut guard + resource limit merkezi config. Discovery farklı sunucular arasında bağımsız; caller cancellation children'a geçer, sağlıklı registry kaydı rollback edilmez. Partial errors status'e yazılır.
- Tool çağrısı timeout/cancel sonrası remote side-effect olmuş olabilir; status ambiguous/degraded + Paket 2/D01 recovery OBSERVE_FIRST. Bounded backoff connect/list transient readiness içindir; unsafe call tekrarını otomatik retry'ye dönüştürmez.
- Pool `_Parked` permanent hata için kalır; transient retry record server identity+loop generation/failure-count/next-retry-at tutar. Clock/jitter injected; nominal backoff/ceiling config. Endpoint config değişimi ve explicit reconnect ilgili kaydı temizler. Tüm MCP'yi yeniden başlatma yok.
- Stack açan supervisor kapatır: asyncio.wait_for ile başka task'ta `stack.aclose()` çalıştırmak AnyIO cancel-scope sahipliğini bozabilir. Deadline context supervisor task'ında tutulur; stop event → graceful close → kendi scope'unda cancel/drain. `_draining` cleanup task owner olarak korunur; externally cancelled caller cleanup'ı sahipsiz bırakmaz.
- Close timeout bütün app shutdown'u sonsuz tutmaz; transport-owned STDIO process terminate/kill/reap SDK mevcut lifecycle'ıyla doğrulanır. Timeout döndü diye leak yok iddiası yapılmaz; fixture gerçek child PID/returncode kanıtı gerekir. Callback socket aynı owner cleanup hattında kapatılır.
- Existing global `_POOL/_HOSTED` mevcut otorite; yeni global refresh singleton eklemeyin. Bu pakette alakasız geniş pool/global refactor yapmayın. Shared refresh coordinator mevcut session/pool/service owner'dan constructor injection ile gelir; public facade uyumu korunur.

## OAuth singleflight ve keyring

- Storage get/set'e tek tek Lock koymak yeterli değildir: iki SDK provider expired token'ı okuyup aynı rotating refresh token'ı kullanabilir. Aynı profile/server/account/client registration generation için refresh transaction (reload expired→refresh HTTP→persist→publish) tek owned task olur; waiters aynı sonucu alır.
- Repo refresh transport'u SDK `OAuthClientProvider` içinde; uygulamadan önce installed SDK'nin resmi public extension/auth-flow mekanizması okunmalı. Private `_refresh_*` monkeypatch/subclass uydurma yapılmaz. Public refresh hook yoksa aynı identity için OAuth provider/auth-flow owner reuse ve auth handshake serialization ile SDK akışı tek authority olur. Native SDK OAuth validation/PKCE/registration kaldırılmaz.
- Waiter cancel shared refresh task'ını iptal etmez; owner shutdown/logout iptal eder ve await eder. Shared task asyncio.shield ile beklenebilir; task'a owner ve failure propagation gerekir. Logout/revoke generation bump; late refresh eski credential'ı geri yazamaz. Ten concurrent expired reads tek refresh; farklı accounts/client IDs birbirini kilitlemez.
- URL-only `KeyringTokenStorage(config.url)` mevcut namespace compatibility'si korunur. Profile/account/client registration bilgisi gerekirse safe namespace v2 ve explicit migration; mevcut token tüm accounts'a kopyalanmaz. `registration_is_stale` callback redirect değişimindeki mevcut temizleme semantiği korunur; stale registration migration testleri genişler.
- Keyring sync I/O asyncio.to_thread; JSON/schema corruption typed auth/storage required state; raw token/client secret/header/provider response/UI log'a girmez. Safe structured error kind, server metadata yeterli. Existing debug_identity yalnız hash namespace gösterir.

## UI sağlık ve araç kataloğu

- Health projection transport connected, auth state, readiness (ready/degraded/parked/backoff), trust state, last checked/next retry optional ve stage connect/list/call/close taşır. `bagli` tek başına araç ready veya trusted değildir. Son başarılı count cache kaldıysa stale etiketi; gerçek unavailable unknown sayılır.
- McpConnectionService own/pool snapshot merge observation time+generation ile yapılır. Eski Test et başarı snapshot'ı yeni login-required/closed olayını örtmez. Server health events `core/events.py` Paket 2 korelasyonuyla optional publish; global bus yok.
- ConnectorsScreen Paket 3 AsyncState/result adapter kullanır; per-row action pending/error/retry. Permanent parked ne yapılacağını söyler; transient backoff zamanı/retry düğmesi ayrı. UI trust review/revoke server kimliğiyle host typed request; browser state doğrudan allow vermez.
- R18 tool catalogue RemoteTool mevcut schema/description/effect/provenance verisinden human summary verir; schema advanced detail'da. Same name farklı origin namespaces korunur; gerçek routing seçim kaydı yoksa neden seçildi iddiası gösterilmez. Hassas description/sample dış kaynak sayılır ve credential içeren values render/log'a kopyalanmaz.
- HTTP token/OAuth login ve hosted connector provider-verified farklı kaynaklar; hosted path `Fusion bu sunucuya MCP konuşmaz` mevcut sözleşmesini korur. Hosted verified markasını doğrudan trusted'a normalize etmeyin.

## RED→GREEN / testler / sıra

1. Core/config trust/budget/evidence types + loader/writer fixtures: old configured legacy/unreviewed; new local/HTTP unreviewed; explicit existing scope preserved; OAuth scopes grant olmaz; origin/executable/account change review; text-only description change tüm grant'i silmez.
2. `test_mcp_tool_effect.py`, `test_mcp.py`, approval/ability fixture: annotation conflict destructive; untrusted readonly blocked/ask; trusted read; explicit narrow read allow; unknown malformed hints; ability resolver aynı trust cap; revoke ve schema revision old allow geçersiz. Shell izinleri korunur.
3. `test_mcp_pool.py`, `test_mcp_connect_failures.py`, `test_mcp_service.py`: hanging list A/healthy B; separate stage deadlines; total paginated list bounded; call timeout ambiguous no automatic side-effect replay; transient backoff fake clock/jitter; explicit reconnect; permanent parked; stale probe merge; one-server partial failure.
4. Close fixtures supervisor owner task, cancelled open, cancelled close, hanging callback/socket/stdio cleanup; `draining` boş ve process reaped kanıtı. SDK legacy initialize hâlâ çağrılır; new protocol handshake assertion bu pakete girmez.
5. `test_mcp_oauth.py`, `test_mcp_bearer_token.py`, fixed-port/stale-registration fixtures: 10 concurrent expiry one refresh; cancelled waiter diğerini bozmaz; logout/revoke late write reject; different namespace separate; keyring exception/corruption typed; sentinel token/headers stdout/log/UI/status içinde yok.
6. `ConnectorsScreen.test.tsx`, `test_appserver_connectors.py`: connected/auth/trusted badges ayrı; parked/degraded/backoff unknown-safe label; per-row retry; failed row diğerini korur; scope review/revoke; catalogue provenance and details.
7. Yerel isolated STDIO + localhost HTTP fixture connect/list/read/cancel/close transcript; fake auth endpoints. Bu ürünün tüm remote connector'ları test edildi iddiası değildir. Offline hedefli tests→App typecheck/build→root full gates; yeni protocol SDK matrix Paket 15'e kayıt.

Build order: Paket 5 scope ve Paket 2/3 adapters kontrolü → RED → config/trust/effect helper → client discovery/schema/budgets → pool backoff/cleanup → SDK-compatible OAuth refresh owner/keyring → service/UI projection → local fixture/gates/release note. Policy değişikliği ihtiyatlı Fusion kararı olarak açıklanır; diğer ürün davranışı hakkında standard violation hükmü verilmez.
