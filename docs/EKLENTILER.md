# Eklentiler, pazar yerleri ve içe aktarma

Fusion, Claude Code'un eklenti biçimini (`.claude-plugin/plugin.json`) ve pazar yeri biçimini
(`.claude-plugin/marketplace.json`) doğrudan okur. Bir eklenti beceri, komut, alt ajan, çıktı
stili, kanca ve MCP sunucusunu tek paket olarak getirir. Başka bir ajanın (Claude Code, Codex,
Gemini CLI, Cursor) yapılandırması `/import` ile taşınır.

## Eklenti klasörü

```
benim-eklentim/
  .claude-plugin/plugin.json   {"name": "benim-eklentim", "version": "1.0.0", "description": "…"}
  skills/<ad>/SKILL.md         → /benim-eklentim:<ad>
  commands/<ad>.md             → /benim-eklentim:<ad>
  agents/<ad>.md               → benim-eklentim:<ad> (alt ajan)
  output-styles/<ad>.md        → /output-style benim-eklentim:<ad>
  hooks/hooks.json             kancalar (Fusion dışında komut çalıştırır)
  .mcp.json                    MCP sunucuları (süreç başlatır)
```

- `plugin.json` `commands`, `agents`, `skills`, `outputStyles` alanlarıyla ek yol verebilir (varsayılanı
  tamamlar); `hooks` ve `mcpServers` dosya yolu ya da satır içi nesne olabilir. Yollar eklenti kökü
  dışına çıkamaz. `.fusion-plugin/plugin.json` de okunur. Tanınmayan alanlar (ör. `lspServers`)
  uyarı olur.
- Komut ve kanca metinlerinde `${CLAUDE_PLUGIN_ROOT}` (ya da `${FUSION_PLUGIN_ROOT}`) eklentinin
  kurulu klasörüne çözülür.
- Bütün adlar eklenti adıyla öneklenir: üçüncü taraf bir eklenti kendi `ozet` becerini gölgeleyemez.
  Eklenti becerilerinde `` !`komut` `` bağlamı çalıştırılmaz.
- MCP sunucuları `plugin_<eklenti>_<sunucu>` adıyla, `unreviewed` güvenle eklenir; araç çağrıları
  onay ister ve hiçbir ayar dosyasına yazılmaz (`fusion mcp remove` yerine eklentiyi kapat).
- Kanca blokları `config/plugin_store.plugin_hook_blocks()` ile kanca yükleyicisine verilir
  (kaynak adı `eklenti:<ad>`).

## Komutlar

```
fusion eklenti kur ./benim-eklentim            # yerel klasör
fusion eklenti kur sahip/repo                  # GitHub (sığ klon, betik çalışmaz)
fusion eklenti kur https://git.ornek.com/x.git # genel https git adresi
fusion eklenti kur rapor@ekip [--yes]          # kayıtlı pazardan
fusion eklenti kur <kaynak> --dry-run          # yalnız doğrula ve özetle
fusion eklenti listele | dogrula <yol|ad>
fusion eklenti ac|kapat <ad>  ·  fusion eklenti kapat --hepsi
fusion eklenti kaldir <ad>                     # Fusion çöpüne (fusion cop geri-al)
fusion eklenti guven <ad>                      # değişmiş eklentiyi yeniden onayla
fusion eklenti kesfet [pazar]
fusion eklenti pazar ekle <yol|sahip/repo|https…|resmi>  ·  pazar liste  ·  pazar kaldir <ad>
```

Claude Code adları gizli takma ad olarak çalışır: `fusion plugin install|list|validate|enable|disable|
uninstall|marketplace add`. REPL'de `/plugin` (`/plugins`, `/eklenti`) aynı alt komutları alır; kanca
ya da MCP içeren eklenti önce önizlenir, `--yes` ile kurulur. Masaüstünde Beceriler ekranındaki
**Eklentiler** düğmesi Kurulu · Keşfet · Pazarlar sekmelerini açar (RPC: `eklenti.*`).

`resmi` kısa adı `https://github.com/anthropics/claude-plugins-official` pazarıdır. Keşfet ağa
çıkmaz; git pazarları ekleme anındaki klondan okunur (güncellemek için pazarı kaldırıp yeniden ekle).

## Güven ve bütünlük

- Kurulumda klasörün sha256 içerik karması kaydedilir (`<veri>/eklentiler/kayit.json`). Dosyalar
  sonradan değişirse eklenti **değişmiş** görünür ve hiçbir bileşeni yüklenmez; `fusion eklenti guven`
  güncel içeriği gösterip yeniden onay ister.
- Pazar girdisi `sha` bildiriyorsa klonun commit'i ona eşit olmalıdır; değilse kurulmaz.
- Kanca/MCP içeren eklenti açık onay olmadan kurulmaz (CLI `--yes` ya da TTY sorusu, masaüstü
  "Onaylıyorum, kur"). Git adresleri yalnız genel https sunucularıdır (iç ağ, kimlik bilgili adres yok).
- Hepsini kapatma: `fusion eklenti kapat --hepsi` ya da `FUSION_PLUGINS=off`.

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

Kurallar: sır gibi görünen ortam değerleri, argümanlar (`--token x`, `--api-key=x`,
`Authorization: Bearer x`), adres sorgu değerleri (`?api_key=x`) ve `Authorization: Bearer`
başlıkları şifreli depoya gider; `config.yaml`'a yerine `${FUSION_MCP_ENV_<SUNUCU>__<AD>}` başvurusu
yazılır, önizlemede değer görünmez. Kasa adı sunucuya özeldir: iki sunucunun `OPENAI_API_KEY`'i
birbirini ya da Fusion'ın kendi sağlayıcı anahtarını ezmez; alt süreç yine `OPENAI_API_KEY` adıyla
alır. Kullanıcı adı/parolalı ya da yolunda sır taşıyan adres atlanır. Var olan dosyanın üzerine
yazılmaz, aynı adlı MCP/kural "zaten var" olur. Proje dosyalarındaki izin kuralları taşınmaz (depo
genel izin dosyana `Bash(*)` yazdıramaz). SSE taşıması ve Authorization dışındaki başlıklar
gerekçesiyle atlanır. Codex `approval_policy`/`sandbox_mode` bilgi satırıdır (karşılığı onay kipi).

## Sürüm notları

`/release-notes [sürüm|liste]`, `fusion release-notes`, Ayarlar › Güncellemeler › Sürüm notları
(RPC `surum.notlari`). Kaynak deponun `CHANGELOG.md`'sidir; dosyanın bulunmadığı kurulumda
GitHub Releases sayfası gösterilir.
