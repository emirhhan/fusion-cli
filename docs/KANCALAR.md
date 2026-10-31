# Kancalar (hooks)

Kanca, bir olaya (araç çağrısı, istem gönderimi, tur sonu…) bağlanan kabuk komutudur.
Fusion olay anında komutu çalıştırır, **stdin'e olayın JSON'unu** yazar ve **çıkış kodu +
stdout JSON'undan** kararı okur. Biçim ve olay adları Claude Code ile aynıdır:
`~/.claude/settings.json` içindeki kancalar Fusion'da da çalışır.

## Nerede tanımlanır

| Katman | Dosya | Koşul |
|---|---|---|
| Fusion (kullanıcı) | `<yapılandırma dizini>/hooks.json` (`fusion hooks list` yolu gösterir) | her zaman |
| Claude (kullanıcı) | `~/.claude/settings.json` | `runtime.claude_hooks: true` |
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
| `SubagentStop` | alt ajan bitince | ajan türü | alt ajan gerekçeyle sürer |
| `SessionStart` | oturumun ilk turunda | `startup` | — (stdout bağlam olur) |
| `SessionEnd` | oturum kapanınca | `prompt_input_exit`, `other` | — |
| `Notification` | izin sorusundan hemen önce | `permission_prompt` | — |
| `PreCompact` | bağlam özetlenmeden önce | `manual` (`/compact`), `auto` | — |

Claude Code'un diğer olayları (`PermissionRequest`, `WorktreeCreate`…) listede "Fusion bu
olayı tetiklemiyor" diye görünür; hata değildir. Yalnız `type: "command"` desteklenir;
`http`, `prompt`, `agent`, `mcp_tool` listede "tür desteklenmiyor" olarak atlanır.

**Eşleştirici:** boş ya da `*` hepsi; `Bash`, `Edit|Write` ad listesi; aksi halde düzenli
ifade (adın tamamı: `mcp__github__.*`). Fusion araçları Claude adlarıyla da eşleşir
(`run_shell` → `Bash`, `write_file` → `Write`/`Edit`, `read_file` → `Read`, MCP
`sunucu__araç` → `mcp__sunucu__araç`).

## Girdi (stdin)

Ortak alanlar: `session_id`, `cwd`, `hook_event_name`, `permission_mode`. Araç olaylarında
`tool_name` (Claude adı, ör. `Bash`), `fusion_tool_name`, `tool_input` (Fusion argümanları +
dosya araçlarında Claude'un `file_path` takma adı); `PostToolUse`'ta `tool_response`,
`PostToolUseFailure`'da `error`. `UserPromptSubmit`: `prompt`. `Stop`: `stop_hook_active`,
`last_assistant_message`. Kanca süreci proje kökünde çalışır; `FUSION_PROJECT_DIR` ve
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
  claude_hooks: true     # false = yalnız Fusion'ın hooks.json'ı
  hook_timeout_s: 60     # süresi yazılmamış kanca; tek kanca en çok 600 sn
```

`"disableAllHooks": true` Fusion/Claude kullanıcı dosyasında ya da **güvenilen** proje
dosyasında hepsini kapatır; kapatma oturumda bir kez "Kancalar bu oturumda kapalı" diye
bildirilir. Güvenilmeyen depodaki `disableAllHooks` yok sayılır (depo senin koruyucu
kancalarını kapatamaz) ve listede uyarı olarak görünür. `FUSION_HOOKS=off` ortam değişkeni
de hepsini kapatır (acil durum ve testler). Eski `runtime.post_edit_commands` aynen çalışır.

- `fusion hooks list [--json]` — tüm katmanlar, durum ve atlanma nedeni.
- `fusion hooks test PreToolUse --tool Bash --input '{"command": "rm -rf x"}'` — eşleşen
  kancaları gerçekten çalıştırır ve kararı gösterir (engelde çıkış 2).
- REPL `/hooks` (`/kancalar`) — salt okunur liste.
- Masaüstü: Ayarlar › İzinler › **Kancalar** (`kanca.listele` RPC).

Tanımlar her kök turun başında yeniden okunur; tur ortasında değişmez.

## Claude Code'dan bilinçli farklar

- Yalnız `command` türü; olay kataloğu 10 olay (yukarıdaki tablo).
- `Stop` sürdürmesi tur başına en çok 3 kez (betik `stop_hook_active`'e bakmasa da sonsuz döngü olmaz).
- `SessionStart` ilk kök turda tetiklenir (oturum açılışında değil); bağlamı o tura eklenir.
- `updatedInput` özgün argümanın üstüne birleşir (Claude tamamen değiştirir).
