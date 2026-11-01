# Kancalar (hooks)

Kanca, bir olaya (araç çağrısı, istem gönderimi, tur sonu…) bağlanan kabuk komutu ya da
HTTP adresidir. Fusion olay anında komutu çalıştırır, **stdin'e olayın JSON'unu** yazar ve
**çıkış kodu + stdout JSON'undan** kararı okur (`http` türünde JSON POST edilir, yanıt
gövdesi stdout gibi okunur). Biçim, olay adları ve karar kuralları Claude Code ile aynıdır
(<https://code.claude.com/docs/en/hooks>): `~/.claude/settings.json` kancaları Fusion'da da
çalışır.

## Nerede tanımlanır

| Katman | Dosya | Koşul |
|---|---|---|
| Claude (kullanıcı) | `~/.claude/settings.json` | her zaman (`runtime.claude_hooks: false` ile atlanır) |
| Proje | `.claude/settings.json` | etkileşimli: `fusion trust` + içerik o günden beri aynı; `-p`: her zaman |
| Proje (yerel) | `.claude/settings.local.json` | proje ile aynı |
| Yönetilen | macOS `/Library/Application Support/ClaudeCode/managed-settings.json`, Linux `/etc/claude-code/managed-settings.json` | her zaman |
| Fusion (eski) | `<yapılandırma dizini>/hooks.json` | **kullanımdan kalktı**: bu sürümde okunur, oturumda bir kez uyarılır |

Kanca **kod çalıştırır**. Etkileşimli oturumda (REPL, TUI, masaüstü) indirilen bir deponun
kancaları projeye güvenmeden çalışmaz; listede "atlandı: proje güvenilmiyor" diye görünür.
**`fusion -p` / `fusion agent` (etkileşimsiz) oturumda klasör güvenilir sayılır** (Claude
Code `-p`/SDK kuralı): yazmadığın bir depoda `-p` koşmadan önce `.claude/` ayarlarını
gözden geçir ya da `FUSION_HOOKS=off` kullan.

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash",
        "hooks": [{ "type": "command", "command": "~/bin/komut-denetle", "timeout": 30,
                    "if": "Bash(git *)" }] }
    ],
    "PostToolUse": [
      { "matcher": "Edit|Write",
        "hooks": [{ "type": "command", "command": "node",
                    "args": ["${CLAUDE_PROJECT_DIR}/.claude/hooks/format.js"] }] }
    ],
    "Stop": [
      { "hooks": [{ "type": "command", "command": "./scripts/testler-gecti-mi.sh" }] }
    ]
  }
}
```

## Olaylar

| Olay | Ne zaman | Eşleştirici | Engel (çıkış 2 / `decision: block`) |
|---|---|---|---|
| `PreToolUse` | araç çalışmadan, onaydan önce | `tool_name` | araç çalışmaz, gerekçe modele |
| `PostToolUse` | araç başarıyla bitince | `tool_name` | gerekçe araç sonucunun yanına |
| `PostToolUseFailure` | araç hata verince | `tool_name` | gerekçe araç sonucunun yanına |
| `UserPromptSubmit` | kök tur başında | — | istem düşer, model çağrılmaz |
| `Stop` | ajan cevabını bitirince | — | ajan gerekçeyle sürer (art arda en çok 8) |
| `SubagentStart` | alt ajan modele ilk kez gitmeden önce | ajan türü | alt ajan başlamaz |
| `SubagentStop` | alt ajan, ekip üyesi ya da iş akışı düğümü bitince | ajan türü | alt ajan gerekçeyle sürer |
| `SessionStart` | oturumun ilk turunda (yüzey açılışta tetikleyebilir); bağlam özetlenince | `startup`, `resume`, `clear`, `compact` | — (stdout bağlam olur) |
| `SessionEnd` | oturum kapanınca, `/reset`, `/resume` geçişi | `prompt_input_exit`, `clear`, `resume`, `other` | — |
| `Notification` | izin sorusu ~6 sn yanıtsız kalınca; boşta bekleme | `permission_prompt`, `idle_prompt` | — |
| `PreCompact` | bağlam özetlenmeden önce | `manual` (`/compact`), `auto` | özetleme atlanır |
| `PostCompact` | bağlam özetlendikten sonra | `manual`, `auto` | — |
| `CwdChanged` | `/cd` oturum kökünü değiştirince | — | — |
| `TaskCreated` | ekip görevi panoya eklenmeden önce | — | görev eklenmez, gerekçe ekleyene |
| `TaskCompleted` | ekip üyesi görevi "tamam" yapmadan önce | — | görev üyede kalır, gerekçe üyeye |
| `TeammateIdle` | ekip üyesi boşa düşmeden önce | — | üye gerekçeyle yeniden koşar |

Ekip olaylarının ayrıntısı: [EKIP_VE_IS_AKISLARI.md](EKIP_VE_IS_AKISLARI.md).

**Eşleştirici** (Claude kuralı): boş ya da `*` hepsi; yalnız harf/rakam/`_`/`-`/boşluk/`,`/`|`
içeren metin tam ad ya da ad listesidir (`Bash`, `Edit|Write`, `Edit, Write`); başka bir
karakter içeren metin **çapasız** JavaScript düzenli ifadesidir: `Edit.*` `NotebookEdit`'e de
uyar, tam eşleşme için `^Edit$`. Araç olaylarında yalnız `tool_name` sınanır: `run_shell` →
`Bash`, `write_file` → `Write`, `edit_file` → `Edit`, `read_file` → `Read`, MCP
`sunucu__araç` → `mcp__sunucu__araç`. (`Edit` → bütün yazma araçları genişlemesi yalnız
izin kurallarında geçerlidir.)

## İşleyici alanları

Ortak: `type` (**zorunlu**: `command`, `http`, `mcp_tool`, `prompt`, `agent`), `if` (izin
kuralı sözdizimi, ör. `Bash(git *)`; yalnız araç olaylarında değerlendirilir, öteki
olaylarda `if` taşıyan kanca hiç çalışmaz), `timeout` (sn), `statusMessage`, `once` (yalnız
beceri frontmatter'ında anlamlı).

- **`command`**: `command`; `args` verilirse kabuksuz exec biçimi (her öğe tek argüman,
  `${CLAUDE_PROJECT_DIR}` düz metin olarak yerleşir); `shell` (`bash` | `powershell`);
  `async: true` arka planda çalışır, kararı beklenmez; `asyncRewake: true` çıkış 2'de
  stderr'i (boşsa stdout'u) bir sonraki tura sistem hatırlatması olarak bırakır;
  `onFailure: "block"` başarısızlıkta (başlatılamadı, 0/2 dışı çıkış, zaman aşımı, şema
  hatası) çıkış 2 gibi engeller (Stop/SubagentStop/TaskCompleted/TeammateIdle ve arka plan
  kancalarında etkisiz).
- **`http`**: `url`, `headers`, `allowedEnvVars`, `onFailure`. Olay JSON'u `POST` edilir.
  2xx + boş gövde = karar yok; 2xx + JSON nesnesi = karar alanları; 2xx + başka gövde (düz
  metin), 2xx dışı yanıt, yönlendirme, bağlantı hatası ve zaman aşımı engellemeyen hatadır
  (metin bağlama eklenmez). Başlıktaki `$AD`/`${AD}` yalnız `allowedEnvVars` listesindeki
  ortam değişkeninden dolar. Adres kısıtı yoktur (yerel sunucu dahil); ayar dosyasındaki
  `allowedHttpHookUrls` (joker `*`) tanımlıysa yalnız listedeki adreslere gidilir,
  `httpHookAllowedEnvVars` başlıklara yerleşebilecek adları daraltır.

Olay × tür (Claude tablosu): SessionStart yalnız `command`/`mcp_tool`; gözlem olayları
(Notification, PreCompact, PostCompact, SessionEnd, CwdChanged, SubagentStart) `prompt`/
`agent` desteklemez; desteklenmeyen birleşim gerekçesiyle atlanır.

**Varsayılan süreler:** `command`/`http` 600 sn; `UserPromptSubmit`'te 30 sn; `SessionEnd`
kancaları ortak 1,5 sn bütçeyi paylaşır (yazılı `timeout` bütçeyi en çok 60 sn'ye kadar
yükseltir; `CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS` ile değişir). Üst sınır yoktur.

## Girdi (stdin)

Ortak alanlar: `session_id`, `prompt_id` (kök tur kimliği), `transcript_path`, `cwd`,
`permission_mode` (`default`, `plan`, `acceptEdits`, `auto`, `dontAsk`,
`bypassPermissions`; Fusion'ın güvenlik kipi `default` gelir), `effort` (`{"level": …}`),
`hook_event_name`; alt ajandaki araç olaylarında `agent_id`, `agent_type`.
`scratchpad_dir` yazılmaz: Claude belgesine göre oturumun karalama klasörü yoksa alan
bulunmaz, Fusion oturumlarında böyle bir klasör yoktur.

Araç olaylarında `tool_name` (Claude adı), `tool_use_id`, `tool_input` Claude aracının
şeklinde: Bash `{command, run_in_background}`, Write `{file_path, content}`, Edit
`{file_path, old_string, new_string, replace_all}`, Read `{file_path, offset, limit}`;
dosya araçlarında `file_path` **mutlaktır**. MCP araçlarında `mcp_server: {name}`.
`PostToolUse`'ta `tool_response` (Bash `{stdout, stderr, interrupted, isImage}`, Write
`{type: "create" | "update", filePath, content}`, Edit `{filePath, …}`, Read `{type, file}`)
ve `duration_ms` (aracın çalışma süresi; onay beklemesi dahil değil);
`PostToolUseFailure`'da `error`,
`is_interrupt`. `UserPromptSubmit`: `prompt`. `Stop`: `stop_hook_active`,
`last_assistant_message`, `background_tasks`, `session_crons`; `SubagentStop` ek olarak
`agent_id`, `agent_type`, `agent_transcript_path`. `SessionStart`: `source`,
`session_title` (biliniyorsa). `SessionEnd`: `reason`. `Notification`:
`notification_type`, `message`, `title`. `PreCompact`: `trigger`, `custom_instructions`
(elle `/compact`'ta metin, yoksa ve `auto`'da `null`). `PostCompact`: `trigger`,
`compact_summary`. `CwdChanged`: `old_cwd`, `new_cwd`. Ekip olayları: `team_name`,
`teammate_name`, `task_id`, `task_subject`, `task_description`.

Ortam: Fusion'ınki (MCP sırları ve `OTEL_*` hariç) + `CLAUDE_PROJECT_DIR` /
`FUSION_PROJECT_DIR` (oturumun **başladığı** proje kökü; worktree ve `/cd` ile değişmez) +
`CLAUDE_EFFORT`. `SessionStart` ve `CwdChanged` kancalarına ek olarak `CLAUDE_ENV_FILE`
verilir: kanca bu dosyaya `export AD=değer` satırları ekler (`>>`), oturumdaki her kabuk
komutu (`run_shell`, arka plan dahil) dosyayı komuttan önce kabuk kodu olarak çalıştırır
(`export PATH="$PATH:./node_modules/.bin"` gibi satırlar değerlendirilir).

## Çıktı

- **çıkış 0** — stdout JSON ise alanları uygulanır; `UserPromptSubmit`/`SessionStart`'ta düz
  metin modele bağlam olur.
- **çıkış 2** — engelleyebilen olayda engeller; gerekçe stderr ya da JSON `reason`'ıdır. JSON
  alanları yine okunur ama engeli kaldıramaz.
- **diğer** — şemaya uyan JSON yazdıysa çıkış kodu yok sayılır ve alanlar karar verir; yoksa
  engellemeyen hata: `<Olay>:<eşleşen> hook error` + `Failed with non-blocking status code:
  <stderr'in ilk satırı>`.
- `{` ile başlayıp `}` ile biten ama ayrıştırılamayan çıktı ve `hookEventName`'i eksik ya da
  yanlış `hookSpecificOutput` şema hatasıdır: engellemez, bağlama eklenmez.

JSON alanları: `continue: false` + `stopReason`, `systemMessage`, `terminalSequence`
(izinli OSC 0/1/2/9/99/777 ve BEL; başka dizi alanı geçersiz kılar), `decision: "block"` +
`reason`, `hookSpecificOutput` (`hookEventName` zorunlu) içinde `additionalContext`.
`PreToolUse`: `permissionDecision` (`allow` | `deny` | `ask` | `defer`; öncelik deny > defer >
ask > allow), `permissionDecisionReason` (`ask`'ta onay kartında, `deny`'de modele),
`updatedInput` (girdinin **tamamını** değiştirir; değişmeyen alanlar da yazılır),
`additionalContext` (araç sonucunun yanına). `defer` `fusion -p`'de turu `tool_deferred`
ile bitirir. `PostToolUse`: `updatedToolOutput` / `updatedMCPToolOutput` (metin ya da araç
şeklinde nesne), `classifierContext`. `UserPromptSubmit`: `sessionTitle`,
`suppressOriginalPrompt` (engel mesajı varsayılan olarak `Original prompt: <metin>` ile
biter). `SessionStart`: `sessionTitle`, `initialUserMessage`, `watchPaths`, `reloadSkills`.
`Stop`/`SubagentStop`: `additionalContext` turu hata göstermeden sürdürür ("Stop hook
feedback"). `allow` bir `deny`/`ask` izin kuralını, yıkıcı komut onayını ve plan kipini
**geçemez**.

Olay başına atılan alanlar: Notification, PreCompact, PostCompact, SessionEnd
`systemMessage`/`continue`'yu; CwdChanged ve TaskCreated `continue`'yu atar; SessionEnd
bütün JSON'u atar; Notification çıkış kodunu/stderr'i yok sayar. TaskCompleted görev
aracından geldiğinde `continue: false`'u yok sayar (çıkış 2 yine engeller).

**Modele giden biçim:** engelde `PreToolUse:Bash hook error: [komut]: <gerekçe>` (aracın
hatası olarak); ek bağlam ve düz stdout `<system-reminder>` içinde, kanca adıyla
(`PostToolUse hook additional context: …`) ve metindeki `<system-reminder>` /
`</system-reminder>` etiketlerinin `<`'i `&lt;` olarak. SessionStart bağlamı konuşmanın
başında ilk istemden önce, UserPromptSubmit bağlamı istemin yanında **konuşmada kalır**
(sonraki turlarda kaybolmaz). 10.000 karakteri aşan bağlam/`systemMessage` oturum dizinine
yazılır; modele dosya yolu + ilk 2.000 karakter gider. Stop'ta yalnız `reason` iletilir.

## Ayarlar ve komutlar

`disableAllHooks` ayar önceliğinden sonra kalan değerdir: projedeki `false` kullanıcıdaki
`true`'yu geçersiz kılar; güvenilmeyen depodaki değer yok sayılır ve listede uyarı olarak
görünür. Yönetilen kancaları yalnız yönetilen düzeydeki `disableAllHooks` kapatır;
yönetilen ayardaki `allowManagedHooksOnly: true` yalnız yönetilen kancaları çalıştırır.
`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` art arda Stop sürdürme tavanını (varsayılan 8, ajan araç
çağırınca sıfırlanır) değiştirir.

Fusion'a özgü ekler (Claude'da karşılığı yok, davranışı değiştirmez):

```yaml
runtime:
  hooks_enabled: true    # false = hiçbir kanca çalışmaz
  claude_hooks: true     # false = ~/.claude/settings.json kancalarını atla
  hook_idle_prompt_s: 60 # Notification(idle_prompt) gecikmesi; 0 = kapalı
  # hook_timeout_s, hook_http_allow_private: kullanımdan kalktı, okunmaz
```

`FUSION_HOOKS=off` ortam değişkeni de hepsini kapatır (acil durum ve testler). Eski
`runtime.post_edit_commands` aynen çalışır.

- `fusion hooks list [--json]` — tüm katmanlar, durum ve atlanma nedeni.
- `fusion hooks test PreToolUse --tool Bash --input '{"command": "rm -rf x"}'` (Fusion'a
  özgü) — eşleşen kancaları gerçekten çalıştırır ve kararı gösterir.
- REPL `/hooks` (`/kancalar`) — salt okunur liste.
- Masaüstü: Ayarlar › İzinler › **Kancalar** — liste (`kanca.listele`) ve iki anahtar
  (`hooks_enabled`, `claude_hooks`; `kanca.ayar`).

Tanımlar her kök turun başında yeniden okunur.

## Henüz yok

- `prompt`, `agent`, `mcp_tool` türleri tanınır ama çalıştırılmaz (listede "tür henüz
  desteklenmiyor").
- Olaylar: `Setup`, `UserPromptExpansion`, `PermissionRequest`, `PermissionDenied`,
  `PostToolBatch`, `MessageDisplay`, `StopFailure`, `InstructionsLoaded`, `ConfigChange`,
  `DirectoryAdded`, `FileChanged`, `WorktreeCreate`, `WorktreeRemove`, `PreModelSwitch`,
  `PostModelSwitch`, `Elicitation`, `ElicitationResult` tetiklenmez (listede "Fusion bu
  olayı tetiklemiyor").
- Eklenti `hooks/hooks.json` ve beceri frontmatter kancaları çalıştırılmaz (ajan
  frontmatter kancaları çalışır: alt ajanda `Stop` → `SubagentStop`).
- Ayar dosyası izleyicisi yok (değişiklik bir sonraki kök turda alınır);
  `watchPaths` ile dosya izleme, `initialUserMessage`/`reloadSkills`'in uygulanması,
  `terminalSequence`'in terminale basılması yok (alanlar okunur).
- `CwdChanged` yalnız `/cd` ile tetiklenir (kabuk aracındaki `cd` ile değil).
- `transcript_path` kanca için üretilen ayrı, maskeli JSONL'dir (oturum bitince silinir).
- `/hooks` etkileşimli tarayıcı ("All events") yok; düz liste.
- Etkileşimli oturumda kullanıcı kancaları da klasör güvenine bağlı değildir (Claude güven
  iletişimi kabul edilene kadar bekletir).
