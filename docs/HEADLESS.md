# Headless (betik) kullanım — `fusion -p`

`fusion -p` Claude Code'un `claude -p/--print` kipinin karşılığıdır: istemi etkileşimsiz
çalıştırır, cevabı yazar ve çıkar. Bayrak adları, değerleri ve çıktı alanları Claude
Code'unkilerle aynıdır; Claude için yazılmış betik komut adı değiştirilerek çalışır.

```bash
fusion -p "testleri çalıştır ve kırmızıları düzelt"
cat build-error.txt | fusion -p "kök nedeni kısaca açıkla" > cikti.txt
fusion -p "özetle" --output-format json | jq -r .result
fusion -c -p "kaldığın yerden sürdür"
fusion -r "$session_id" -p "testleri de ekle"
fusion "merhaba"                      # -p yok: etkileşimli oturum bu istemle açılır
fusion -v                             # sürüm
```

## İstem ve stdin

Boru stdin'i istemle birleşir (istem önce, stdin içeriği sonra). Boru girdisi 10 MB ile
sınırlıdır; aşılırsa açık hata ve çıkış kodu 1. stdin okunamazsa stderr'e uyarı yazılır ve
argümandaki istemle sürülür. İstem de stdin de yoksa Claude'un hatasıyla (`Input must be
provided either through stdin or as a prompt argument when using --print`) çıkılır.

`--input-format stream-json` stdin'den `{"type":"user","message":{"role":"user","content":
"..."}}` satırlarını okur; her satır aynı oturumda bir turdur ve her tur kendi `result`
satırını yazar. `--output-format stream-json` gerektirir. `--replay-user-messages` gelen
kullanıcı mesajlarını çıktıya yansıtır.

## Çıktı — `--output-format text|json|stream-json`

| Değer | Davranış |
|-------|----------|
| `text` (varsayılan) | stdout'a yalnız nihai cevap. İlerleme satırları yalnız `--verbose` ile ve stderr'e. |
| `json` | Tek `SDKResultMessage` nesnesi (aşağıda). |
| `stream-json` | Her satır bir SDK mesajı. Claude gibi `--verbose` ister. |

`json` sonuç nesnesi:

```json
{"type": "result", "subtype": "success", "is_error": false, "result": "…",
 "session_id": "8f0c…", "num_turns": 3, "duration_ms": 5120, "duration_api_ms": 4100,
 "total_cost_usd": 0.0012, "stop_reason": null,
 "usage": {"input_tokens": 1200, "output_tokens": 300,
           "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
 "modelUsage": {"openrouter/…": {"inputTokens": 1200, "outputTokens": 300, "costUSD": 0.0012}},
 "permission_denials": [], "uuid": "…", "fusion": {"maliyet_tam": true, "durma_nedeni": null}}
```

`subtype`: `success` | `error_max_turns` | `error_max_budget_usd` | `error_during_execution` |
`error_max_structured_output_retries`. Hata alt türlerinde `result` yerine `errors[]` gelir.
`--json-schema` verildiyse ve cevap uyduysa `structured_output` alanı eklenir. `fusion` alt
nesnesi Fusion'a özgü ektir (`maliyet_tam` false ise maliyet alt sınırdır).

`stream-json` sırası: `{"type":"system","subtype":"init",session_id,cwd,model,permissionMode,
mcp_servers[{name,status}],tools,...}`, ardından `assistant` (metin + `tool_use` blokları;
araç adları Claude adlarıyla: `Bash`, `Read`, `Edit`…) ve `user` (`tool_result`) mesajları,
yeniden denemede `system/api_retry`, reddedilen çağrıda `system/permission_denied`, en sonda
aynı `result` nesnesi. `--include-partial-messages` metin parçalarını `stream_event`
(`content_block_delta`/`text_delta`) olarak ekler.

Koşu başladıktan sonra oluşan hata (bulunamayan oturum, açılamayan çalışma ağacı…) json
kiplerinde `is_error: true` sonuç nesnesi olarak stdout'a yazılır; geçersiz bayrak koşu
başlamadan stderr'e yazılır.

## Oturumlar

`-p` koşusu da bir oturumdur: kimliği `session_id` alanında döner, REPL'in `/resume`
listesinde görünür. `-c/--continue` son oturumu, `-r/--resume <kimlik|ad>` seçileni sürdürür;
`--fork-session` kopyasını yeni kimlikle açar. `--session-id <uuid>` yeni oturuma kimlik
verir (sürdürmeyle yalnız `--fork-session` ile birlikte). `--no-session-persistence` diske
hiç yazmaz. `-n/--name` oturuma ad verir.

## İzinler ve araçlar

| Bayrak | Claude anlamı (Fusion'da da aynı) |
|--------|-----------------------------------|
| `--permission-mode` | `default` (varsayılan) \| `acceptEdits` \| `plan` \| `auto` \| `dontAsk` \| `bypassPermissions` \| `manual`. |
| `--dangerously-skip-permissions` | `bypassPermissions` ile aynı. |
| `--allowedTools` / `--allowed-tools` | Ön-onay kuralları: eşleşen çağrı sorulmadan çalışır. Kural sözdizimi `permissions.allow` ile aynı: `Bash(git diff *)`, `Read(./src/**)`, `mcp__github`. Değerler boşlukla ya da virgülle. |
| `--disallowedTools` / `--disallowed-tools` | Çıplak ad aracı bağlamdan çıkarır (`*` hepsi, `mcp__*` tüm MCP araçları, `mcp__<sunucu>` o sunucu); kapsamlı kural (`Bash(rm *)`) aracı bırakır, yalnız eşleşen çağrıyı reddeder. |
| `--tools` | Yerleşik araç kümesini daraltır: `"Bash,Read"`, `""` (hepsi kapalı), `"default"`. MCP araçlarını etkilemez. |
| `--permission-prompts host\|none` | Kabul edilir; `-p` zaten kimseye sormaz. |
| `--permission-prompt-tool` | Onayları bir MCP aracına sorar (aşağıda). |

`-p` hiçbir zaman terminalde onay sormaz: onay gerektiren ve hiçbir allow kuralı ya da kipin
onaylamadığı çağrı reddedilir, tur sürer (model başka yol dener) ve çağrı
`permission_denials` listesine düşer. Fusion'da karşılığı olmayan Claude araç adı koşuyu
düşürmez; stderr'e uyarı yazılır ve kural yalnız eşleşen çağrıya uygulanır.

## Diğer bayraklar

| Bayrak | Etkisi |
|--------|--------|
| `--max-turns N` | Model çağrısı üst sınırı; verilmezse sınır yok. Sınırda `error_max_turns`. |
| `--max-budget-usd X` | Bilinen maliyet X'e ulaşınca tur durur (`error_max_budget_usd`). |
| `--model <takma ad\|tam kimlik>` / `--fallback-model a,b` | Oturum modeli ve sıralı yedek zinciri. |
| `--effort low\|medium\|high\|…` | Akıl yürütme yoğunluğu. |
| `--system-prompt`, `--system-prompt-file` | Fusion'ın çekirdek sistem metninin yerine geçer. |
| `--append-system-prompt`, `--append-system-prompt-file` | Sisteme eklenir (dosya içeriği önce). |
| `--json-schema '<şema>'\|dosya` | Satır içi JSON ya da dosya; geçersiz şemada `Error: --json-schema is not a valid JSON Schema`. Tam JSON Schema denetimi; uymayan cevap iki kez yeniden denenir. |
| `--settings <dosya\|json>` | Oturumluk ayar: `permissions.allow/ask/deny`, `model`. |
| `--mcp-config <dosya\|json>…` / `--strict-mcp-config` | `.mcp.json` biçiminde ek sunucular; strict'te yalnız bunlar. Bozuk girdi atlanır, init'te `mcp_server_errors`. |
| `--bare` | Kancalar, bellek, MCP, proje talimatı kapalı; araçlar Bash + dosya okuma/düzenleme. |
| `--add-dir <dizin>…` | Ek erişim kökleri; var olan dizin olmalı. |
| `--agent <ad>` / `--agents '<json>'` | Baş ajan ve oturumluk ajan tanımları. |
| `-w/--worktree [ad]` | Çalışma ağacında koş; ad verilmezse üretilir. |
| `--verbose` | `text` kipinde ilerleme satırları (stderr); `stream-json` için zorunlu. |
| `--debug [kategoriler]` / `--debug-file <yol>` | Ayrıntılı günlük stderr'e ya da dosyaya; `"api,hooks"`, `"!statsig"` süzgeci `fusion_cli.*` günlükçü adlarına uygulanır. |
| `--disable-slash-commands` | İstemdeki `/ad` genişletilmez. |
| `--from-pr <N\|URL>` | Bu PR'a bağlı en son oturumu sürdürür (GitHub/GitLab/Bitbucket adresi ya da numara). |
| `--bg` | `-p` ile birleştirilemez (Claude'un hatası). `fusion --bg "görev"` arka plan görevi başlatır. |

Kabul edilip Fusion'da henüz etkisi olmayan bayraklar (`--include-hook-events`,
`--forward-subagent-text`, `--prompt-suggestions`, `--plugin-dir`,
`--betas`, `--exclude-dynamic-system-prompt-sections`, `--setting-sources`)
stderr'e "etkisiz" uyarısı yazar; sessizce düşmez.

`--permission-prompt-tool mcp__<sunucu>__<araç>` onay gereken her çağrıyı o MCP aracına
`{tool_name, input, tool_use_id}` ile sorar; araç `{"behavior":"allow"}` dönerse çağrı
çalışır, `deny`, hata ya da bulunamayan araçta reddedilir (`updatedInput` uygulanmaz).

İstem `/ad` ile başlıyorsa beceri/özel komut koşudan önce genişletilir (gövde sistem
bağlamına, argüman göreve; `allowed-tools`/`disallowed-tools` turu daraltır). Etkileşimli
arayüze özgü komutlar (`/clear`, `/resume`…) Claude'daki gibi `/<ad> isn't available in this
environment.` cevabını verir. `--disable-slash-commands` genişletmeyi kapatır.

Fusion ekleri (Claude'da yok): `--set bölüm.alan=değer`, `--profile <kademe>`,
`--no-memory` (belleği kapatır; Claude'da bellek `--bare` ya da ayarla kapanır).

Kök komut (etkileşimli oturum) da `--model`, `--fallback-model`, `-c/-r/--fork-session`,
`-n`, `-w`, `--add-dir`, `--agent`, `--agents` ve konumsal istemi (`fusion "istem"`) alır.

## Arka plan işi

Tur bittikten sonra `-p`, turun başlattığı arka plan alt ajanlarını bekler; 5 sn sonra
stderr'e `Waiting for background work to finish` yazar. Tavan
`CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` (varsayılan 600000 ms); dolunca kalan iş durdurulur.
Arka plan kabuk süreçleri (`run_shell` arka planı) henüz beklenmez.

## Çıkış kodları

- `0` — `success`.
- `1` — hata alt türleri, geçersiz bayrak ya da boş cevap.
- `2` — Typer bayrak ayrıştırma hatası (ör. var olmayan `--add-dir`).
- `143` — SIGTERM (kapanış kancaları çalışır).

---

# Eski yüzey — `fusion agent` (kullanımdan kalkıyor)

`fusion agent` bir sürüm boyunca eski davranışıyla çalışmaya devam eder (varsayılan kip
`auto`, Türkçe alanlı sonuç, `--allowed-tools` = araç daraltma, `--permission-channel`
onay protokolü). Yeni betikler `fusion -p` kullanmalı; aşağıdaki bölümler eski yüzeyi
belgeler.

### Görev kaynağı

```bash
fusion agent "testleri çalıştır ve kırmızıları düzelt"     # argüman
echo "dosyaları listele" | fusion agent -                  # stdin (`-`)
echo "dosyaları listele" | fusion agent                    # boru hattında boş görev = stdin
```

Terminalde boş görev hata verir (`Görev metni boş olamaz.`); stdin yalnız boru hattında
okunur.

### Çıktı biçimi — `--output-format`

| Değer | Davranış |
|-------|----------|
| `text` (varsayılan) | İnsan için renkli çıktı; `--quiet` ilerleme satırlarını gizler. |
| `json` | Tek satır: nihai sonuç nesnesi (aşağıda). İlerleme satırı basılmaz. |
| `stream-json` | Her olay bir satır (JSONL). İlk satır `SystemInit`. `--json` bunun kısaltmasıdır. |

#### `json` sonuç nesnesi

```json
{"type": "result", "ok": true, "durum": "completed", "sonuc": "…",
 "yapisal": null, "yapisal_hatalar": [], "durma_nedeni": null, "model_cagri": 3,
 "kullanim": {"girdi_token": 1200, "cikti_token": 300, "maliyet_usd": 0.0012,
              "maliyet_tam": true, "cagri": 3}}
```

`durum`: `completed` | `budget` (tur bütçe/tavan sebebiyle kesildi) | `failed`.
`maliyet_tam` false ise toplam alt sınırdır (ölçülmemiş ya da iptal edilmiş çağrı var).

#### `stream-json` olayları

Her satır `{"event": "<OlayAdı>", ...alanlar}` biçimindedir; alanlar `core/events.py`
içindeki olay dataclass'larının alanlarıdır ve sırlar maskelenir. Betiklerin en çok
kullandığı olaylar:

| Olay | Anlamı (Claude Code karşılığı) |
|------|--------------------------------|
| `SystemInit` | İlk satır: `surum`, `model`, `kip`, `cwd`, `izin_kanali`, `mcp_sunuculari` (`system/init`). |
| `ModelCallStarted` / `ModelCallFinished` | Model çağrısı (token/maliyet `result.usage` içinde). |
| `ToolStarted` / `ToolExecuted` | Araç çağrısı ve sonucu (`tool_use` / `tool_result`). |
| `ApprovalRequested` / `ApprovalResolved` | Onay kanalı açıkken izin isteği ve karar (`permission_denied` karşılığı: `karar: "deny"`). |
| `QuestionAsked` | Model kullanıcıya soru sordu (onay kanalı açıkken). |
| `TurnBudgetExhausted` | Tur bütçe sebebiyle kesildi; `reason` alanı (`cost_limit`, `model_calls`, …). |
| `TurnAnswered` / `TurnFinished` | Nihai cevap ve tur sonu (`result`). |

### Sınırlar

| Bayrak | Etkisi |
|--------|--------|
| `--max-turns N` | Bu tur için model çağrısı üst sınırı (`runtime.agent_max_steps`'i geçersiz kılar). |
| `--max-budget-usd X` | Turun **bilinen** maliyeti X'e ulaşınca tur `cost_limit` ile kapanır (`runtime.agent_max_cost_usd`). Ücretsiz ya da maliyeti bilinmeyen model tavanı doldurmaz. |

İkisi de `config.yaml`'dan kalıcı olarak verilebilir:

```yaml
runtime:
  agent_max_steps: 40
  agent_max_cost_usd: 2.0     # null = tavan yok
```

### Araç listeleri

```bash
fusion agent "…" --allowed-tools read_file,grep,run_shell   # modele YALNIZ bunlar sunulur
fusion agent "…" --disallowed-tools run_shell                # çağrılırsa sorulmadan engellenir
```

Yasak listedeki araç modele **hiç sunulmaz** (salt-okunur araçlar dahil: `read_file`,
`web_search`, `gh`…); adı uydurulup çağrılırsa karar `BLOCKED`tır, kullanıcıya sorulmaz, tur
durmaz (model "bu yol kapalı" bilgisini alır). Kabuk takma adları (`run_shell`/`bash`) tek
aile sayılır.

Claude Code farkı: orada `--allowedTools` "bu araçları sormadan onayla" demektir; Fusion'da
`--allowed-tools` "modele yalnız bunları sun" demektir (onay kipi `--mode` ile ayrı seçilir).
Araç adları Fusion adlarıdır (`read_file`, `edit_file`, `run_shell`, `search_code`). Claude
Code'dan kopyalanan adlar çevrilir: `Read` → `read_file`/`view_file`, `Edit` →
`edit_file`/`multi_edit`, `Bash(git diff:*)` → `run_shell` (alt komut deseni Fusion'da yok;
aracın tamamına uygulanır), `mcp__github__get_issue` → `github__get_issue`. Bu oturumda
bulunmayan bir ad (yazım hatası, bağlanmamış MCP sunucusu) verilirse model hiç çağrılmadan
çıkış kodu 1 ile durulur ve en yakın adlar önerilir:

```text
Bilinmeyen araç adı: raed_file. Şunu mu demek istediniz: read_file?
```

### Sistem istemi ve ajan tanımı

```bash
fusion agent "…" --append-system-prompt "Yalnız Türkçe yaz."
fusion agent "…" --agent gozden-gecirici     # .claude/agents/gozden-gecirici.md
```

`--agent` tanımının gövdesi sistem istemine eklenir; `tools:` alanı varsa izin listesi
onunla kesişir (`--allowed-tools` da verildiyse ikisinin kesişimi).

### `--bare`

Bellek, MCP sunucuları, barındırılan bağlayıcılar ve proje talimatı (AGENTS.md/CLAUDE.md,
dış araç bellekleri) yüklenmez; tur yalnız yerleşik araçlarla çalışır
(`runtime.project_instructions: false` + boş `mcp_servers`). CI'da tekrarlanabilir
koşular için.

### Yapısal çıktı — `--json-schema`

```bash
fusion agent "bu depodaki açık TODO'ları say" \
  --json-schema sema.json --output-format json
```

Şema modele sistem eki olarak gider ("son cevabın yalnız bu şemaya uyan tek JSON
nesnesi olsun"); nihai cevaptan JSON ayıklanır (kod çiti sökülür) ve denetlenir. Uyumsuzsa
`yapisal_hatalar` dolar ve çıkış kodu 1 olur. Desteklenen JSON Schema alt kümesi:
`type` (tek ad ya da liste), `required`, `properties`, `items`, `enum`,
`additionalProperties: false`. Diğer anahtarlar denetlenmez.

### Dış onay kanalı — `--permission-channel stdin`

Etkileşimsiz oturumda onay istemi normalde `UNAVAILABLE` sayılır (sorulamadı, tur sürer).
Kanal açıkken istekler yazılır, kararlar stdin'den JSON-Lines olarak okunur. İsteklerin
yazıldığı yer çıktı biçimine bağlıdır: `stream-json`'da stdout (diğer olaylarla aynı akış),
`json` ve `text`'te **stderr** (stdout tek satırlık sonuç/cevap için ayrılmıştır):

```text
stdout → {"event": "ApprovalRequested", "istek_id": "1", "arac": "run_shell", "args": {...}, "tehlike": null, "etki": "..."}
stdin  ← {"istek_id": "1", "karar": "onayla"}          # onayla|oturum|reddet (allow|session|deny)
stdout → {"event": "ApprovalResolved", "istek_id": "1", "karar": "once"}
stdout → {"event": "QuestionAsked", "istek_id": "2", "soru": "...", "secenekler": [...], "onerilen": null}
stdin  ← {"istek_id": "2", "cevap": "..."}
```

Eşleşmeyen kimlik, bozuk satır, EOF ya da zaman aşımı insan reddi DEĞİLDİR: `UNAVAILABLE`
döner. Cevap `--permission-timeout` saniye (varsayılan 300) içinde gelmezse istek
"sorulamadı" sayılır; bu sürede tur ve zamanlayıcılar çalışmaya devam eder. Zaman aşımına
uğramış isteğe geç gelen cevap atlanır, sonraki isteğe sayılmaz.
Görev stdin'den okunurken kanal da stdin olamaz; görevi argüman olarak ver (bu çakışma
stdin okunmadan bildirilir).

```bash
fusion agent "testleri düzelt" --permission-channel stdin --permission-timeout 60 \
  --output-format json 2> istekler.jsonl
```

### Çıkış kodları

- `0` — tur tamamlandı, nihai metin dolu, şema (varsa) uyumlu.
- `1` — boş cevap, hata, bütçe/tavan kesintisi ya da şemaya uymayan cevap.
- `2` — bayrak hatası (Typer).

### Arka planda koşturma — `--bg`

`fusion agent --bg [--name ad] "görev"` görevi ayrı bir süreçte başlatır ve kimliği yazıp
hemen döner; olaylar aynı JSON-Lines biçiminde `<bellek>/arka-plan/<kimlik>/olaylar.jsonl`
dosyasına gider, onay istekleri `fusion agents cevapla` ile cevaplanır. İzleme ve yönetim:
`fusion agents` (bkz. [ARKA_PLAN_GOREVLERI.md](ARKA_PLAN_GOREVLERI.md)).

Kısıt bayrakları işçiye taşınır: `--allowed-tools`, `--disallowed-tools`, `--max-budget-usd`,
`--max-turns`, `--add-dir`, `--append-system-prompt`, `--no-memory`, `--bare`, `--worktree`
ve global `--set`/`--profile`. `--output-format`/`--json`, `--json-schema` ve
`--permission-channel` `--bg` ile açık hatayla (çıkış kodu 2) reddedilir.

