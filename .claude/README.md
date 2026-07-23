# .claude/

Bu dizin projenin yapay zekâ ile geliştirme katmanını tutar. İçerik git'e girer; kişisel
ayarlar girmez.

| Dosya / dizin | Git | Amaç |
|---------------|-----|------|
| `settings.json` | commit edilir | Proje geneli izinler (allow/ask/deny) ve commit attribution ayarı. Ekipteki herkes için ortak. |
| `settings.local.json` | commit EDİLMEZ | Kişisel izin eklemeleri. `.gitignore`'dadır. |
| `agents/` | commit edilir | Projeye özel uzman agent tanımları (`*.md`, frontmatter: `name`, `description`, `tools`). |
| `skills/` | commit edilir | Projeye özel skill tanımları (`<ad>/SKILL.md`). |

## Kurallar

- `settings.json` içindeki `allow` listesine yalnızca **salt-okunur ve geri alınabilir**
  komutlar eklenir; yazan/yayınlayan komutlar `ask` listesine girer.
- `deny` listesi güvenlik sınırıdır: sır dosyaları okunmaz, geri alınamaz git komutları
  çalıştırılmaz. Bu liste daraltılmaz.
- Yeni bir izin eklenmesi gerekiyorsa önce burada gerekçesi konuşulur; sessizce
  `settings.local.json`'a yazılıp geçilmez.
- Davranış kuralları bu dizinde değil, kök dizindeki [CLAUDE.md](../CLAUDE.md) ve
  [RULES.md](../RULES.md) dosyalarındadır.
