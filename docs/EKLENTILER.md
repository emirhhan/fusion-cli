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
- `${CLAUDE_PLUGIN_ROOT}` (ya da `${FUSION_PLUGIN_ROOT}`) eklentinin kurulu klasörüne çözülür:
  kanca ve MCP tanımlarında, komut/beceri gövdesinde (`/eklenti:komut`, `read_skill`) ve alt ajan
  isteminde.
- Bütün adlar eklenti adıyla öneklenir: üçüncü taraf bir eklenti kendi `ozet` becerini gölgeleyemez.
  **Claude Code'dan sapma:** eklenti beceri/komutlarında `` !`komut` `` bağlamı çalıştırılmaz
  (yerinde "komut çalıştırılmadı" notu kalır).
- MCP sunucuları `plugin_<eklenti>_<sunucu>` adıyla, `unreviewed` güvenle eklenir; araç çağrıları
  onay ister, hiçbir ayar dosyasına yazılmaz ve güven kararı kalıcı tutulmaz (`fusion mcp remove`
  yerine eklentiyi kapat). Eklentiyi kapatmak/kaldırmak sunucuyu çalışan oturumdan da çıkarır
  (masaüstünde canlı bağlantı hemen kapanır). Desteklenmeyen alan taşıyan sunucu (`type: sse`, `cwd`,
  Authorization dışı başlık…) uyarıyla atlanır, eklentinin geri kalanı kurulur;
  `Authorization: Bearer ${VAR}` başlığı desteklenir. İki eklentinin sunucu adı çakışırsa ada göre
  ilk eklenti kazanır.
- **Kancalar bu sürümde çalıştırılmaz.** Kanca blokları onaylanır ve
  `config/plugin_store.plugin_hook_blocks()` ile kanca yükleyicisine (P-009) hazır bekler (kaynak adı
  `eklenti:<ad>`); yükleyici bağlanana dek önizleme ve liste "kancalar tetiklenmez" der
  (`PLUGIN_HOOKS_ACTIVE`).

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
fusion eklenti guncelle <ad> [--yes] [--karma]  # kaydedildiği kaynaktan yeniden çek
fusion eklenti kesfet [pazar]
fusion eklenti pazar ekle <yol|sahip/repo|https…|resmi>  ·  pazar liste  ·  pazar guncelle <ad>
fusion eklenti pazar kaldir <ad>
```

Claude Code adları gizli takma ad olarak çalışır: `fusion plugin install|list|validate|enable|disable|
uninstall|update|marketplace add|update`. REPL'de `/plugin` (`/plugins`, `/eklenti`) aynı alt
komutları alır; kanca ya da MCP içeren eklenti önce önizlenir, `--yes` ile kurulur (araya giren
değişiklik varsa kurulmaz). Masaüstünde Beceriler ekranındaki **Eklentiler** düğmesi Kurulu · Keşfet ·
Pazarlar sekmelerini açar; her eklentide Güncelle/Doğrula, değişmiş eklentide "İncele ve yeniden
onayla" (RPC: `eklenti.*`, `eklenti.guncelle|dogrula|pazar_guncelle`).

`resmi` kısa adı `https://github.com/anthropics/claude-plugins-official` pazarıdır. Keşfet ağa
çıkmaz; git pazarları son ekleme/güncelleme anındaki klondan okunur (`pazar guncelle`). Aynı adlı
başka kaynaklı bir pazar eskisinin yerine geçemez.

**Bilinçli eksikler:** yalnız kullanıcı kapsamı vardır; Claude Code'un proje/yerel eklenti kapsamları,
`settings.json` `enabledPlugins` ve `extraKnownMarketplaces` alanları okunmaz. Kriptografik imza yok:
bütünlük sha256 karma + commit pinidir.

## Güven ve bütünlük

- Kurulumda klasörün sha256 içerik karması kaydedilir (`<veri>/eklentiler/kayit.json`, süreçler arası
  kilitle yazılır). Dosyalar sonradan değişirse eklenti **değişmiş** görünür ve hiçbir bileşeni
  yüklenmez; `fusion eklenti guven` (masaüstü "İncele ve yeniden onayla") güncel içeriği gösterip
  yeniden onay ister. Bildirim adı değişmiş eklenti yeniden onaylanmaz.
- Onay ekranı kanca satırlarını (`Olay [eşleşen]: komut`), MCP sunucularının tam komutunu (sırlar
  maskeli) ve içerik karmasını gösterir. Onay o karmaya bağlıdır: `fusion eklenti kur X --dry-run`
  karmayı basar, `kur X --yes --karma <karma>` içerik değiştiyse kurmaz; masaüstü ve REPL bunu
  kendiliğinden yapar.
- Pazar girdisi `sha` bildiriyorsa en az 7 onaltılık karakter olmalıdır. Tam (40 karakter) sha o
  commit'i doğrudan çeker (dal ucu ilerlese de); kısa sha dal ucuyla eşleşmelidir.
- Kanca/MCP içeren eklenti açık onay olmadan kurulmaz (CLI `--yes` ya da TTY sorusu, masaüstü
  "Onaylıyorum, kur"). Git adresleri yalnız genel https sunucularıdır (iç ağ, kimlik bilgili adres
  yok); klon yönlendirme izlemez, https dışı protokole geçmez ve denetlenen IP'ye sabitlenir.
  Yerel klasör 5 000 dosya / 50 MB sınırını aşıyorsa kopyalanmadan reddedilir.
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
