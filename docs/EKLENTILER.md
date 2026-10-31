# İçe aktarma ve sürüm notları

Başka bir ajanın (Claude Code, Codex, Gemini CLI, Cursor) yapılandırması `/import` ile taşınır.

## İçe aktarma (`/import`)

```
fusion import <claude|codex|gemini|cursor> [--dry-run] [--yes]
/import codex            # önizleme
/import codex --yes      # uygula
```

Masaüstü: Ayarlar › Kişiselleştirme › **Başka araçtan içe aktar** (RPC `ice_aktar.onizle|uygula`).

| Kaynak | Taşınan | Zaten doğrudan okunan |
|--------|---------|-----------------------|
| Claude Code | `~/.claude.json` MCP (kullanıcı + bu projenin yerel kapsamı) | `~/.claude/settings.json` izin/kanca, CLAUDE.md, skills/agents/commands, `.mcp.json` |
| Codex | `config.toml` `[mcp_servers]`, `~/.codex/rules/*.rules` `prefix_rule` → `Bash(…)`, `~/.codex/prompts` → `~/.fusion/commands` | AGENTS.md, `~/.codex/skills`, `~/.agents/skills` |
| Gemini CLI | `settings.json` MCP (`httpUrl`), `tools.allowed/exclude` → izin, `~/.gemini/GEMINI.md` → `~/.fusion/TALIMAT.md` içine `@` başvurusu, `commands/*.toml` → komut | proje GEMINI.md |
| Cursor | `mcp.json` (proje dosyası projenin `.mcp.json`'ına), `cli-config.json` izinleri, `.cursor/rules/*.mdc` (`alwaysApply`/`globs`) → `.fusion/rules`, `commands/*.md` | `.cursorrules`, AGENTS.md |

Kurallar: sır gibi görünen ortam değerleri ve `Authorization: Bearer` token'ları şifreli depoya
gider, `config.yaml`'a yalnız adı yazılır; önizlemede değer görünmez. Var olan dosyanın üzerine
yazılmaz, aynı adlı MCP/kural "zaten var" olur. Proje dosyalarındaki izin kuralları taşınmaz (depo
genel izin dosyana `Bash(*)` yazdıramaz). SSE taşıması ve Authorization dışındaki başlıklar
gerekçesiyle atlanır. Codex `approval_policy`/`sandbox_mode` bilgi satırıdır (karşılığı onay kipi).

## Sürüm notları

`/release-notes [sürüm|liste]`, `fusion release-notes`, Ayarlar › Güncellemeler › Sürüm notları
(RPC `surum.notlari`). Kaynak deponun `CHANGELOG.md`'sidir; dosyanın bulunmadığı kurulumda
GitHub Releases sayfası gösterilir.
