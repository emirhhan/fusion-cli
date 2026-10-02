# Ajan ekibi, görsel hattı, Chrome güvenilirliği ve silme güvenliği — sonuç

Dal: `ajan-ekibi` (main 2e29105 üstüne). Onaylanan faz listesinin 1-7. fazları ve 8. fazdan
düzenleme kancaları; kalıcı geri sarma, Lighthouse/axe ve sandbox yapılmadı.

## Faz 1 — Rate limit ve kalıcı tur
- `providers/rate_ledger.py`: süreçler arası SQLite hız defteri (soğuma + dakikalık kova).
- `providers/rate_gate.py`: model/anahtar başına önden yavaşlatma; 429 bütün sekmelerle paylaşılır.
  NIM 40/dk (ölçülmüş, `retrying.py`). Bozuk defter turu düşürmez.
- Masaüstü ve tek atışlık `fusion agent` turları `health` geçirmiyordu → circuit breaker yalnız
  REPL'de yaşıyordu. `providers/health_setup.build_health` tek kurulum yeri.
- Çoklu anahtar dönüşü artık masaüstünde de (eskiden yalnız gateway).
- `memory/turn_journal.py`: her araç turundan sonra konuşma diske; süreç tur ortasında
  kapanırsa sekme açılınca geri yüklenir ve bir kez bildirilir.

## Faz 2-3 — Kişilikli, paralel alt ajanlar
- Olay kökünde `agent_id` (yalnız anahtar sözcükle); `ScopedPublisher` alt ajan olaylarını damgalar.
- `engines/agent/team.py`: `spawn_agents` (dalga zamanlayıcı: salt okuyan + ayrık yazma alanı
  birlikte, alanı belirsiz yazan tek başına), `runtime.max_parallel_agents` (4, TAHMİN — ölçülecek).
- `ToolContext.write_scope` + `tools.files.writable_path`: paralel ajan alanı dışına yazamaz.
- Yerleşik ekip `config/roster/*.md` (8 üye); kullanıcı aynı adla `.claude/agents` yazarsa o kazanır.
- Masaüstü: `app/src/team/` — olaylar ajan kartlarına yönlenir, avatar SVG'leri, kişilik renkleri
  `tokens.css`'te (iki temada ≥5,3:1 kontrast). Görsel testler: `e2e/team.visual.ts`.

## Faz 4 — Görsel üretimi
- Çekirdek `providers/image_generation.py`'ye indi (masaüstü sayfası ve ajan aynı yol).
- `generate_image` (NIM FLUX önce, `flux_size_for` ile ~1 MP kova → kapla+kırp → WebP/AVIF + srcset),
  `optimize_image`. NIM kare dışı üretimi 1024×1024 diye bildiriyordu → düzeltildi.
- Bağımlılık: `pillow>=11.3,<13`.

## Faz 5 — Tarama ve varlık toplama
- `site_crawl` (aynı alan adı, robots.txt, `CRAWL_DELAY_S`, SSRF denetimi) ve `chrome_action`
  `assets` eylemi. `site_crawl`/`optimize_image` motor düzeyinde kayıtlı (`engines/agent/web_tools.py`):
  temel araç istemi bütçesi (10.500) korunur.

## Faz 6 — Chrome güvenilirliği
- Eklenti: shadow DOM + aynı kaynaklı iframe tarama, yazma geri-okuma doğrulaması (+ tuş tuş
  ikinci yol), tıklama öncesi/sonrası imza (`changed`), dosya yükleme (`MAX_UPLOAD_BYTES` 10 MB,
  ölçülmedi). Otomatik ikinci tıklama BİLEREK yok.
- `tests/test_chrome_page_action.py`: `pageAction` gerçek Chromium'da 8 senaryo.

## Silme güvenliği (1 Ekim olayı)
- `tools/safe_delete.py`: sade `rm` (joker dahil) → Fusion çöpüne (30 gün); yalnız `/` ve ev
  dizini silinemez, Masaüstü/çok projeli klasör kartta DİKKAT ile sorulur (2 Ekim: kesin ret
  kaldırıldı). `fusion cop liste|geri-al`.
- `make_tool` araçları silme/taşıma/süreç/dinamik kod kullanamaz (otomatik kipte onaysız
  `shutil.rmtree` açığı).
- `observability/audit.py`: kalıcı araç denetim günlüğü (`memory/audit/<sohbet>.jsonl`).

## Faz 7 — Repolar
- `read_skill(name, file=...)`: skill ek dosyaları (kaçış engelli).
- `fusion yetenek kur|liste|kaldir` (yalnız CLI; model kendi başına kod KURAMAZ): repo commit'e sabitlenir,
  betik çalıştırılmaz. stickman-video-director canlı kuruldu, skill + 4 referans okundu.
- `fusion paperclip`: Paperclip process adaptörü heartbeat'i. Gerçek Paperclip ile DENENMEDİ.

## Faz 8 (kısmen) — Düzenleme kancaları
- `runtime.post_edit_commands` (ör. `npx prettier --write {path}`): dosya değişince çalışır,
  başarısızsa çıktısı modele döner (`engines/agent/edit_hooks.py`).

## Bilinen, bu daldan bağımsız kırıklar
- `test_packaging::test_temiz_wheel_ortaminda_cli_calisir`, yerel HTTP MCP fikstürü ve
  `test_masaustunde_shell_reddi_ucuncu_model_cagrisi_yapmadan_turu_durdurur` temiz main'de de düşüyor.
- Playwright görsel testlerinin bir kısmı (control, capabilities, talk, terminal, history,
  visual-shell) temiz main'de de bu makinede düşüyor (yazı tipi/OS farkı).

## Açık işler
- Faz 8 kalanı: kalıcı geri sarma, Lighthouse/axe denetimi, macOS sandbox kipi.
- Stickman'in Yönetmen ajanıyla uçtan uca canlı koşusu; Gemini web video üretimi ölçülmedi.
- `max_parallel_agents` canlı ölçüm; Paperclip gerçek kurulumla deneme.
- Eklenti `chrome://extensions`'ta yeniden yüklenmeli (yeni işlemler).
