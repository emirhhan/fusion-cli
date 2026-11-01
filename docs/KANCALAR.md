# Kancalar (hooks)

Kanca, bir olaya (araç çağrısı, istem gönderimi, tur sonu…) bağlanan kabuk komutu ya da
HTTP adresidir. Fusion olay anında komutu çalıştırır, **stdin'e olayın JSON'unu** yazar ve
**çıkış kodu + stdout JSON'undan** kararı okur (`http` türünde JSON POST edilir, yanıt
gövdesi stdout gibi okunur). Biçim ve olay adları Claude Code ile aynıdır:
`~/.claude/settings.json` içindeki kancalar `runtime.claude_hooks: true` ile Fusion'da da
çalışır (varsayılan kapalı; aşağıya bakın).

## Nerede tanımlanır

| Katman | Dosya | Koşul |
|---|---|---|
| Fusion (kullanıcı) | `<yapılandırma dizini>/hooks.json` (`fusion hooks list` yolu gösterir) | her zaman |
| Claude (kullanıcı) | `~/.claude/settings.json` | `runtime.claude_hooks: true` (varsayılan false) |
| Proje | `.claude/settings.json` | `fusion trust` + içerik o günden beri aynı |
| Proje (yerel) | `.claude/settings.local.json` | `fusion trust` + içerik o günden beri aynı |

Kanca **kod çalıştırır**: indirilen bir deponun kancaları, projeye güvenmeden çalışmaz;
güvenden sonra dosya değişirse yeniden güvensiz sayılır. Listede "atlandı: proje
güvenilmiyor" diye görünür.

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash",
        "hooks": [{ "type": "command", "command": "~/bin/komut-denetle", "timeout": 30 }] }
    ],
    "PostToolUse": [
      { "matcher": "Edit|Write",
        "hooks": [{ "type": "command", "command": "jq -r .tool_input.file_path | xargs ruff format" }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": "./scripts/testler-gecti-mi.sh" }] }
    ]
  }
}
```

## Olaylar

| Olay | Ne zaman | Eşleştirici | Engel (çıkış 2) |
|---|---|---|---|
| `PreToolUse` | araç çalışmadan, onaydan önce | araç adı | araç çalışmaz, gerekçe modele |
| `PostToolUse` | araç başarıyla bitince | araç adı | gerekçe modele not (araç geri alınmaz) |
| `PostToolUseFailure` | araç hata verince | araç adı | gerekçe modele not |
| `UserPromptSubmit` | kök tur başında | — | istem düşer, model çağrılmaz |
| `Stop` | ajan cevabını bitirince | — | ajan gerekçeyle sürer (en çok 3 kez) |
| `SubagentStart` | alt ajan modele ilk kez gitmeden önce | ajan türü | alt ajan başlamaz, gerekçe üst ajana (stdout bağlamı alt ajana eklenir) |
| `SubagentStop` | alt ajan, ekip üyesi ya da iş akışı düğümü bitince | ajan türü | alt ajan gerekçeyle sürer |
| `SessionStart` | oturumun ilk turunda; bağlam özetlenince | `startup`, `resume`, `clear`, `compact` | — (stdout bağlam olur) |
| `SessionEnd` | oturum kapanınca, `/reset`, sohbet değişince | `prompt_input_exit`, `clear`, `other` | — |
| `Notification` | izin sorusundan önce; girdi bekleyen oturum boşta kalınca | `permission_prompt`, `idle_prompt` | — |
| `PreCompact` | bağlam özetlenmeden önce | `manual` (`/compact`), `auto` | — |
| `CwdChanged` | `/cd` oturum kökünü değiştirince (REPL, TUI, masaüstü) | — | — |
| `InstructionsLoaded` | Bir CLAUDE.md / kural dosyası bağlama ilk kez girince (oturum başı, `@import`, alt dizin erişimi); turu bekletmez | `load_reason` | — |
| `TaskCreated` | ekip görevi panoya eklenmeden önce | — | görev eklenmez, gerekçe ekleyene |
| `TaskCompleted` | ekip üyesi görevi "tamam" yapmadan önce | — | görev üyede kalır, gerekçe üyeye |
| `TeammateIdle` | ekip üyesi boşa düşmeden önce | — | üye gerekçeyle yeniden koşar |

Claude Code'un diğer olayları (`PermissionRequest`, `WorktreeCreate`…) listede "Fusion bu
olayı tetiklemiyor" diye görünür; hata değildir. Ekip olaylarının ayrıntısı:
[EKIP_VE_IS_AKISLARI.md](EKIP_VE_IS_AKISLARI.md).

## Türler: `command` ve `http`

```json
{ "type": "http", "url": "https://kancalar.example.com/fusion",
  "headers": { "Authorization": "Bearer $KANCA_TOKEN" },
  "allowedEnvVars": ["KANCA_TOKEN"], "timeout": 10 }
```

- Olay JSON'u `POST` edilir (`Content-Type: application/json`). **2xx** yanıtın gövdesi
  komut stdout'u gibi okunur (boş = karar yok, JSON = aşağıdaki alanlar); engellemek için
  2xx + `{"decision": "block"}` / `permissionDecision: "deny"` döndürülür. 2xx dışı yanıt,
  yönlendirme (izlenmez), bağlantı hatası ve zaman aşımı engellemeyen "Kanca hatası"dır.
- Başlıktaki `$AD` / `${AD}` yalnız `allowedEnvVars` listesindeki ortam değişkeninden
  dolar; listede olmayan boş kalır (MCP sırları zaten kanca ortamından çıkarılmıştır).
- **İç ağ koruması:** adres bir kez çözülür, bütün IP'leri genel internette değilse istek
  gönderilmez (localhost, 192.168.x, 10.x, 169.254.x, CGNAT; DNS rebinding dahil). Yerel bir
  sunucuya göndermek için `runtime.hook_http_allow_private: true` (güvenilmeyen projenin
  `config.yaml`'ı bunu açamaz). Süre `timeout` (yoksa `hook_timeout_s`), en çok 600 sn.
- `prompt`, `agent`, `mcp_tool` türleri listede "tür desteklenmiyor" diye atlanır: `prompt`
  ve `agent` her olayda ücretli model çağrısı yapar (Fusion bunu kancaya bağlamadı; `/goal`
  değerlendirmesi kendi hakemini kullanır), `mcp_tool` için MCP oturumu kanca katmanına
  taşınmadı. Gerekirse aynı işi bir `command` kancası `fusion -p` ya da MCP istemcisiyle
  yapabilir.

**Eşleştirici:** boş ya da `*` hepsi; `Bash`, `Edit|Write` ad listesi; aksi halde düzenli
ifade (adın tamamı: `mcp__github__.*`). Fusion araçları Claude adlarıyla da eşleşir
(`run_shell` → `Bash`, `write_file` → `Write`/`Edit`, `read_file` → `Read`, MCP
`sunucu__araç` → `mcp__sunucu__araç`).

## Girdi (stdin)

Ortak alanlar: `session_id`, `cwd`, `hook_event_name`, `permission_mode`, `transcript_path`.
Araç olaylarında `tool_name` (Claude adı, ör. `Bash`), `fusion_tool_name`, `tool_use_id`
(PreToolUse ile PostToolUse'u eşler), `tool_input` (Fusion argümanları + dosya araçlarında
Claude'un `file_path` takma adı); `PostToolUse`'ta `tool_response`, `PostToolUseFailure`'da
`error`. `UserPromptSubmit`: `prompt`. `Stop`: `stop_hook_active`, `last_assistant_message`.
`SessionStart`: `source` (`startup`, `resume` — geçmişli sohbet ya da sohbet değişimi,
`clear` — `/reset`, `compact` — bağlam özetlendi). `SessionEnd`: `reason`
(`prompt_input_exit`, `clear`, `other`). `Notification`: `notification_type`, `message`.
`CwdChanged`: `old_cwd`, `new_cwd` (`cwd` yeni dizindir). `InstructionsLoaded`: `file_path`, `memory_type` (`User`/`Project`/`Local`/`Managed`), `load_reason` (`session_start`/`include`/`nested_traversal`), alt dizin yüklemesinde `trigger_file_path`. Ekip olayları: `team_name`,
`teammate_name`; `TaskCreated`/`TaskCompleted`'ta `task_id`, `task_subject`,
`task_description`. `/reset` yeni bir `session_id` verir (sohbet kimliği değişmez).

`transcript_path` Claude biçimli bir JSONL'dir (`{"type": "user"|"assistant", "message":
{"content": [{"type": "text", "text": …}]}}`): istem ve cevaplar, ana ajanın araç çağrıları
(assistant satırında `tool_use`: `id`, `name`, `input`; user satırında `tool_result`:
`tool_use_id`, `content`, `is_error`), sırlar maskeli, girdi/çıktı kırpılmış, dosya 0600; `<bellek dizini>/hook-transcripts/` altında durur ve `SessionEnd` kancalarından
sonra silinir. Tanımlı kanca yoksa hiç yazılmaz. Kanca süreci proje kökünde çalışır; `FUSION_PROJECT_DIR` ve
`CLAUDE_PROJECT_DIR` proje kökünü verir.

## Çıktı

- **çıkış 0** — stdout JSON ise okunur; `UserPromptSubmit`/`SessionStart`'ta düz metin modele bağlam olur.
- **çıkış 2** — engeller; stderr gerekçedir ve modele gider.
- **diğer** — engellemez; stderr kullanıcıya "Kanca hatası" olarak gösterilir. Zaman aşımı da böyle.

JSON alanları: `continue: false` + `stopReason` (tur durur), `systemMessage` (kullanıcıya),
`decision: "block"` + `reason`, `hookSpecificOutput.additionalContext` (modele, en çok
10.000 karakter). `PreToolUse`'ta `hookSpecificOutput.permissionDecision`:
`deny` (engel), `ask` (kip ne olursa olsun sor), `allow` (sormadan) ve `updatedInput`
(argümanları değiştirir; verilmeyen alan korunur). `allow` bir `deny`/`ask` izin kuralını,
yıkıcı komut onayını ve plan kipini **geçemez**. `PostToolUse`'ta `updatedToolOutput`
modele giden çıktıyı değiştirir.

## Ayarlar ve komutlar

```yaml
runtime:
  hooks_enabled: true    # false = hiçbir kanca çalışmaz
  claude_hooks: false    # true = ~/.claude/settings.json kancaları da çalışır
  hook_timeout_s: 60     # süresi yazılmamış kanca; tek kanca en çok 600 sn
  hook_idle_prompt_s: 60 # girdi bekleyen oturum bu kadar boşta kalınca Notification(idle_prompt); 0 = kapalı
  hook_http_allow_private: false  # true = http kancası iç ağ adresine gidebilir
```

**Neden `claude_hooks` varsayılan kapalı:** oradaki betikler (ECC ve benzeri eklentiler)
Claude için yazılmıştır; Fusion'ın her araç çağrısında çalışır (1-2 süreç gecikmesi), araç
girdi/çıktısını görür ve Claude'un kendi durum dosyalarına (`~/.claude`) Fusion oturumlarını
yazabilir. Kapalıyken `fusion hooks list` bu kancaları "atlandı: Claude kullanıcı kancaları
kapalı" diye gösterir; açmak için `fusion config set runtime.claude_hooks true` ya da
masaüstünde Ayarlar › İzinler › Kancalar. Proje `.claude/settings(.local).json` kancaları
bu anahtardan bağımsızdır, `fusion trust` ile açılır.

`"disableAllHooks": true` Fusion/Claude kullanıcı dosyasında ya da **güvenilen** proje
dosyasında hepsini kapatır; kapatma oturumda bir kez "Kancalar bu oturumda kapalı" diye
bildirilir. Güvenilmeyen depodaki `disableAllHooks` yok sayılır (depo senin koruyucu
kancalarını kapatamaz) ve listede uyarı olarak görünür. `FUSION_HOOKS=off` ortam değişkeni
de hepsini kapatır (acil durum ve testler). Eski `runtime.post_edit_commands` aynen çalışır.

- `fusion hooks list [--json]` — tüm katmanlar, durum ve atlanma nedeni.
- `fusion hooks test PreToolUse --tool Bash --input '{"command": "rm -rf x"}'` — eşleşen
  kancaları gerçekten çalıştırır ve kararı gösterir (engelde çıkış 2). Olayın gerçek yükü
  gönderilir; eşleştirici konusu `--subject` ile seçilir (`SessionStart --subject resume`,
  `Notification` varsayılan `permission_prompt`, `Stop --prompt "son cevap"`). `CwdChanged`,
  `TaskCreated`, `TaskCompleted`, `TeammateIdle` örnek alanlarla gönderilir.
- REPL `/hooks` (`/kancalar`) — salt okunur liste.
- Masaüstü: Ayarlar › İzinler › **Kancalar** — liste (`kanca.listele` RPC) ve iki anahtar:
  "Kancaları çalıştır" (`hooks_enabled`), "Claude Code kancalarını da çalıştır" (`claude_hooks`)
  (`kanca.ayar` RPC, kullanıcı `config.yaml`'ına yazar). `/config set runtime.hooks_enabled false`
  gibi değişiklikler açık oturumda bir sonraki turda etkilidir.

Tanımlar her kök turun başında yeniden okunur; tur ortasında değişmez.

## Claude Code'dan bilinçli farklar

- `command` ve `http` türleri; olay kataloğu 14 olay (yukarıdaki tablo).
- `Stop` sürdürmesi tur başına en çok 3 kez (betik `stop_hook_active`'e bakmasa da sonsuz döngü olmaz).
- `SessionStart` ilk kök turda tetiklenir (oturum açılışında değil); bağlamı o tura eklenir.
- `updatedInput` özgün argümanın üstüne birleşir (Claude tamamen değiştirir).
- `continue: false` son cevap olarak "Kanca turu durdurdu (Olay): stopReason" gösterir; durdurulan
  turda (ve bütçe/adım sınırı, model hatası, kullanıcı reddi sonrası) `Stop` çalışmaz. Alt ajanda
  yalnız o alt ajanı durdurur.
- Eşleştirici: düz ad listesi (`Bash`, `Edit|Write`) birebir; aksi halde düzenli ifade adın
  **tamamına** uyar (`fullmatch`): `mcp__github` tek başına `mcp__github__create_issue`'ya uymaz,
  `mcp__github__.*` yazılır.
- `Notification` izin sorusunda (`permission_prompt`) ve boşta beklemede (`idle_prompt`: tur
  bittikten sonra `hook_idle_prompt_s` sn, boşta kalış başına bir kez; hiç tur koşmamış oturumda
  yok) tetiklenir; `auth_success`, `elicitation_dialog` yok. Masaüstünde boşta bildirimi
  kancasının hatası günlüğe yazılır.
- `SessionStart(compact)` tur içi otomatik özetlemede bağlamını sistem mesajına, `/compact`
  sonrasında sonraki tura ekler; oturumu yeniden başlatmaz. Claude'un `/clear`'ının karşılığı
  Fusion'da `/reset`tir (`/clear` yalnız ekranı temizler).
- Ajan tanımındaki `hooks` (`PreToolUse`, `PostToolUse`, `Stop`) yalnız o ajan etkinken çalışır;
  alt ajanda `Stop` → `SubagentStop` olur, `--agent` ana oturum ajanında oturum boyunca geçerlidir.
  Proje ajanında klasör güveni gerekir, eklenti ajanında alan yok sayılır.
- `transcript_path` dökümünde alt ajanların araç çağrıları yoktur (Claude'da ayrı dökümdür);
  oturum bitince silinir.
- `CwdChanged` yalnız `/cd` ile tetiklenir; `/worktree` kök değişimi oturumu yenilemez ve bu
  olayı tetiklemez (tanımlar yeni kökten okunur). `watchPaths`/`CLAUDE_ENV_FILE` çıktıları yok.
- Ekip olaylarında `continue: false` üyenin süren koşusunu kesmez (araç hata döner, üye kısa
  özetle biter, yeniden uyandırılmaz).
- `http` türünde `allowedHttpHookUrls` politika listesi yok; adres kısıtı iç ağ korumasıdır.
