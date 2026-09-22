# Faz 4 — Öğretmen Protokolü Sonuç Raporu (22 Eylül 2026)

Kaynak: 17 Eylül denetimi (A3, A5, A6, A11, C7, C8), plan
`plans/2026-09-22-ogretmen-protokolu.md`. Aralık: `0657d3f..c8b6045` (10
commit — 5 kod + 5 plan güncellemesi), dal `fusion-runtime-hardening-20260827-022831`,
push yok.

## Görev 1-5: hepsi TAMAM

| Görev | Sonuç | Commit |
|---|---|---|
| G1 brief derleyici + `ask_teacher` aracı | `teacher_brief.compile_brief` (25k karakter, gerçek `touched`/`fully_read` verisi), `council`'dan ayrı araç, tekrar-hata notu öğretmen önerir | `0657d3f`, `b877119` |
| G2 dosya yükleme + kırpma geri düşüşü | Gemini web'de canlı doğrulandı (105.032 karakter, model doğru okudu), ChatGPT headless Cloudflare'a takılır (bilinen sorun, yeniden doğrulandı) | `4cc72f3` |
| G3 ders defteri + öğretmensiz kip | `.fusion/ogretmen.md` her zaman yazılır; `ChromaLessonMemory` senkronizasyonu açılır/kapanır + çakışma algılama; `teacherless` kipi + `fusion config` komutları | `e9c885b` |
| G4 kademe düşme bildirimi + saatlik bütçe | `TierDegraded` olayı (yalnız açıkça seçilen kademede), 60/saat bütçe (`ConversationPacer` ölçümünden türetildi) | `c8b6045` |
| G5 gerçek koşuyla doğrulama | Aşağıda | — |

## Görev 5 canlı doğrulama kanıtları

Kullanıcının GERÇEK, giriş yapılmış Gemini web hesabıyla (izole `FUSION_CONFIG`,
`~/.config/fusion-cli/config.yaml`'a dokunulmadı), gerçek üretim yolundan
(`build_agent_registry` + `ToolRegistry.execute`) uçtan uca koşuldu:

1. **Brief gerçekten gitti, gerçek cevap döndü.** Soru: "ModuleNotFoundError:
   No module named foobarbaz123" için hangi pip paketi gerekli. Gemini doğru
   cevap verdi: paket gerçek değil, uydurulmuş bir isim. `served_by="Flash-Lite"`
   — hesabın O ANKİ gerçek kademesi.
2. **Defter ve bütçe gerçekten yazıldı.** `.fusion/ogretmen.md`'ye soru+cevap
   eklendi; `.fusion/ogretmen-butce.json`'daki sayaç arttı.
3. **Kademe düşme bildirimi canlı tetiklendi.** `teacher.model` kasıtlı olarak
   `gemini_web/main/pro` yapıldı (hesap gerçekte Flash-Lite'ta); gerçek bir
   turda `TierDegraded(expected_tier="pro", served_by="Flash-Lite")` yayınlandı
   ve tur yine `ok=True` bitti — bildirim BİLGİLENDİRDİ, turu DÜŞÜRMEDİ.
4. **Dosya yükleme** zaten G2'de ayrı bir canlı oturumda doğrulanmıştı
   (105.032 karakter, gerçek yükleme, model içeriği birebir okudu).
5. **Ağ gerektirmeyen davranışlar** sahte sağlayıcıyla kilitlendi:
   `teacherless` kipte `ask_teacher` hiç sunulmuyor, `council` etkilenmiyor;
   bütçe dolunca sağlayıcı hiç çağrılmıyor.

## Doğrulama sırasında çıkan yan bulgular

- **`_deliver_turn`'ün RAW prompt akışı** (`format_browser_prompt(...,
  trim=False)`) yalnızca ASK_TEACHER'ın 25k karakterlik briefini değil, TÜM
  web-sağlayıcı trafiğini etkiler — mevcut `test_prompt_butcesi.py` +
  `test_web_conversation.py` testleri bunun bozulmadığını zaten doğruluyor,
  ama bu G2'nin blast radius'unun yalnızca `ask_teacher` ile sınırlı
  OLMADIĞINI not etmek gerekiyor (her web-sağlayıcı çağrısı artık önce
  yükleme dener, MAX_WEB_PROMPT_CHARS'ı aşarsa).
- **İzole test config'lerinde `web_sessions:` unutmak** "web oturumu yok"
  hatasına yol açıyor (yaşandı, düzeltildi) — `teacher:` rolü tek başına
  yeterli değil, eşleşen `web_sessions` girişi de gerekiyor. Bu davranış
  DOĞRU (Config field docstring'i zaten bunu söylüyor) ama gelecekte benzer
  bir canlı test kuracak biri için bir tuzak.

## Genel durum

Faz 4'ün beş görevi de tamamlandı, kalite kapısı her adımda temiz tutuldu,
tüm ağ gerektiren maddeler kullanıcının gerçek hesabıyla canlı doğrulandı
(uydurma yok). Commit'ler `main`'e push edilmedi. Sırada denetim
raporundaki Faz 5-7 var (arayüz paritesi, bağlayıcılar, 74 turluk ölçüm
seti) — bkz. `docs/superpowers/plans/2026-09-17-claude-paritesi.md`.
