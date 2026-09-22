# Faz 3 — Çırak Katmanı Sonuç Raporu (22 Eylül 2026)

Kaynak: 17 Eylül denetimi (C4, C5, C6, C9, C10), plan `plans/2026-09-22-cirak-katmani.md`.
Aralık: `c7740f1..4f5ae95` (6 commit), dal `fusion-runtime-hardening-20260827-022831`, push yok.

## Görev 0-4: TAMAM

| Görev | Sonuç | Commit |
|---|---|---|
| G1 ölçülmüş kademe geçişli zengin yedek zinciri (C6) | `nemotron-3-ultra-550b-a55b` gerçek ölçümle zincire eklendi | `dfdd050` |
| G2 kurulumda ücretsiz katman birinci sınıf çırak (C5, C9) | `apprentice_active` + "çırağa dön" RPC/CLI/panel | `3194f35`, `a2ab36b` |
| G3 görsel çırak — gerçek yetenek (C4) | `goz-cirak` (agent+vision) canlı ölçümle eklendi | `4f5ae95` |
| G4 toplu sayma/filtreleme araç kanıtına bağlı (C10) | Türkçe sayma dili → `requires_tool_evidence` | `33a356b` |

## Görev 5: Gerçek koşuyla doğrulama — TAMAM

**Kalite kapısı:** `ruff check .` (temiz), `mypy` (351 dosya, hata yok), `pytest -q`
(tüm testler yeşil, 4 skip) — hepsi 22 Eylül'de bu depoda tekrar koşuldu.

**Ağ gerektiren üç senaryo, gerçek NIM/OpenRouter anahtarlarıyla, izole bir
`FUSION_CONFIG` altında (kullanıcının gerçek `~/.config/fusion-cli/config.yaml`
dosyasına dokunulmadı) ve gerçek üretim yolundan (`run_agent_task`,
CLI'nin kendisinin çağırdığı fonksiyon) koşuldu:**

1. **429/arıza zincirinin devretmesi.** `nemotron-super` adayının birincil modeli
   kasıtlı olarak geçersiz kılındı. Gerçek bir turda zincir art arda ÜÇ gerçek
   arızayı atlattı: `nvidia_nim/...invalid-model-xyz` → 404 → `nvidia_nim/openai/gpt-oss-120b`
   → 410 Gone (bkz. aşağıdaki bulgu) → `openrouter/...nemotron-3-super:free` →
   503 aşırı yüklenme → `nvidia_nim/...nemotron-3-ultra-550b-a55b` → BAŞARILI,
   doğru araç çağrısı (`run_shell wc -l`) ve doğru nihai cevap (2331 satır).
   `ModelFallbackActivated` olayları her adımda görünür.
2. **Gerçek görsel ekli mesaj.** 200×200 düz kırmızı PNG, `images=` parametresiyle
   gerçek bir tura eklendi. Görev otomatik olarak `goz-cirak` (agent+vision)
   adayına yönlendirildi; birincil NIM modeli gerçek bir hız sınırına çarptı
   (`ResourceExhausted 16/16`), zincir OpenRouter eşdeğerine düştü ve doğru
   cevabı verdi: **"kırmızı"**. `ConfigError` ile ölme (eski C4 hatası) artık
   oluşmuyor.
3. **200+ satırlık dosyada sayma görevi.** `loop.py` (2331 satır) için "kaç tane
   `def` var" soruldu. Model metni gözle taramadı; `search_code` ile dört kez
   denedi (`^def` → 38, dar; `def` → 70, geniş; `^[[:space:]]*def` → 0, motor
   desteklemiyor; `^\s*def\s+` → 40) ve son sonucu bildirdi. Bağımsız `grep -cE
   "^\s*def\s+"` doğrulaması da **40** verdi — birebir eşleşiyor.

**Ağ gerektirmeyen madde:** `reset_apprentice_default`
(`appserver/control.py:239`) yalnızca kullanıcının panelde düğmeye/CLI'de
komuta basmasıyla çağrılıyor; kod okuması ve docstring bunu doğruluyor,
hiçbir arka plan yolu tetiklemiyor. Bu makinedeki gerçek `config.yaml`
(`chatgpt_web/main/auto`) test boyunca değişmedi.

## Doğrulama sırasında çıkan yan bulgular (bu fazın kapsamı dışında, BACKLOG'a düşürüldü)

- **`hakem` varsayılan modeli EOL.** `nvidia_nim/openai/gpt-oss-120b`
  ("openai/gpt-oss-120b") NIM'de 2026-09-03'te kullanımdan kaldırılmış (410
  Gone). Hem `judge:` rolünün birincili hem `nemotron-super` adayının ilk
  yedeği bu model — her devretmede bir başarısız deneme boşa gidiyor. Ölçülen
  gerçek hata: `"The model 'openai/gpt-oss-120b' has reached its end of life
  on 2026-09-03T08:00:00Z and is no longer available."` `defaults.yaml`'da bu
  modelin canlı ölçümle güncellenmesi gerekiyor — ayrı, küçük bir görev.
- **Depo kökünde `fusion agent` çalıştırmak pratik değil.** Bu depo (kendisi)
  14 GB ve 136K+ dosya içeriyor (`app/node_modules`, `.worktrees` 37K dosya,
  gitignore'da olmayan `video/` klasörü 18517 dosya). `fusion agent`'ı bu
  kökte çalıştırmak, repo haritası/talimat taraması nedeniyle 25+ dakika
  boyunca ilk model çağrısına bile ulaşamadı; aynı görev temiz bir çalışma
  dizininde 1.3-6.8 saniyede tamamlandı. Gerçek kullanıcı projeleri bu kadar
  büyük olmayacaktır, ama `video/` ve `app/node_modules` gibi klasörlerin
  `.gitignore`'a eklenmesi hem depo hijyeni hem olası bir tarama sınırı testi
  için makul bir küçük iyileştirme.

## Genel durum

Faz 3'ün beş görevi de tamamlandı, kalite kapısı temiz, üç ağ senaryosu da
gerçek anahtarlarla ve gerçek arızalarla (uydurma değil) doğrulandı. Commit'ler
`main`'e push edilmedi (kullanıcı onayı bekleniyor). Sırada denetim
raporundaki Faz 4-7 var (öğretmen protokolü, bağlayıcılar, 74 turluk ölçüm
seti) — bkz. `docs/superpowers/plans/2026-09-17-claude-paritesi.md`.
