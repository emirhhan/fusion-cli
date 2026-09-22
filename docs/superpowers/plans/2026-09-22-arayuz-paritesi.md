# Faz 5 — Arayüz Paritesi: Uygulama Planı

> Kaynak denetim dosyası (`fusion-denetim.html`, H1-H13) depoda YOK — kullanıcı
> onayıyla roadmap'teki (`docs/superpowers/plans/2026-09-17-claude-paritesi.md`
> §Faz 5) tek satırlık özetten devam edilir: "Akış, düşünme bloğu, görev
> listesi, onayda diff önizlemesi, Esc ile kesme, `@` ile dosya anma, bağlam/
> maliyet göstergesi, takip önerileri, başlık üretimi, tek kutu (kip
> ayrımının kaldırılması), arka plan işleri, alt ajan kartları."
>
> Keşif ajanı (22 Eylül) bunun **6 maddesinin zaten bitmiş** olduğunu
> doğruladı (Faz 1/2): akış/Esc/görev listesi (D3, `ui/renderer.py`
> `_write_stream`), onayda diff (H3, `app/src/dialogs/Approval.tsx`), bağlam
> göstergesi (H6, `app/src/screens/ContextGauge.tsx`), başlık üretimi (H9,
> `app/src/sessions/title.ts`). **7 madde gerçekten eksik/kısmi** — bu planın
> kapsamı bunlar.

**Dal:** `fusion-runtime-hardening-20260827-022831`, push yok.

---

## 1. Kalan 7 madde — mevcut durum (keşif ajanı, 22 Eylül)

1. **Düşünme bloğu** — CLI'da ÇALIŞIYOR ama iki ayrı mekanizma var: modelin
   metne gömdüğü `<think>` etiketi (`ui/text.py::segment/strip_thinking`,
   `ui/renderer.py:441-472`, `--show-thinking` ile açılır) GERÇEKTEN
   kullanılıyor; `ModelResult.reasoning` alanı (`litellm_provider.py`'de
   dolduruluyor) hiçbir yerde OKUNMUYOR — ölü veri. Masaüstünde HİÇ yok.
2. **`@` ile dosya anma** — YOK. `Composer.tsx`'te yalnız sürükle-bırak/ataç
   düğmesi var.
3. **Maliyet göstergesi** — keşif ajanının bulgusu YANLIŞTI, kendim
   doğruladım: CLI'de zaten HER turun sonunda basılıyor
   (`cli/app.py::_print_usage` → `ui/tables.py::cost_summary`, "toplam: N
   çağrı · N token · $X.XXXX"). Masaüstünde de `settings/UsagePanel.tsx`
   (`kullanim.durum` RPC) oturum ömürlü maliyeti tam olarak gösteriyor —
   yalnızca Ayarlar panelinde, `ContextGauge` gibi composer'ın YANINDA
   SÜREKLİ görünür değil. Gerçek eksik yalnız BU: composer'ın yanında küçük,
   sürekli görünür bir rakam yok — panel zaten var, veri zaten var.
4. **Takip önerileri** — YOK. `EmptyState.tsx`'teki `suggestions` sohbet
   BAŞLAMADAN ÖNceki öneriler, tur-sonrası değil.
5. **Tek kutu** — YOK. `Composer.tsx:12-25` iki ayrı manuel kip butonu
   ("Sohbet"/"Kod") gösteriyor. Backend zaten OTOMATİK yönlendiriyor
   (`execution_route.py::choose_execution_route`, kullanıcıya SORMADAN karar
   veriyor) — sorun yalnız UI'da, kullanıcı hâlâ elle seçiyor.
6. **Arka plan işleri** — YOK, KASITLI GİZLİ. `BackgroundTasks.pending`
   (`core/concurrency.py`) hiç okunmuyor; `renderer.py`'de arka plan model
   çağrıları `if not event.background` ile BASTIRILIYOR (gürültü azaltmak
   için, bilinçli tasarım — bu değişmeyecek, yalnız bekleyen iş SAYISI eklenir).
7. **Alt ajan kartları** — YOK. `Channel.SUBAGENT` bugün ayrı bir kart değil,
   "alt-ajan" etiketli metin olarak aynı akışa karışıyor (hem CLI hem masaüstü).

---

## Genel kısıtlar

- Masaüstü uygulaması (`app/`, Tauri+React) canlı görsel doğrulama için
  `tauri dev` gerektirir (salt `vite` IPC'siz çalışmaz) — bu ortamda
  pratik değil. Doğrulama `npm test` (vitest, `title.test.ts` deseni) ile
  bileşen testleriyle yapılır; TAM görsel/manuel QA kullanıcıya kalır, bu
  açıkça söylenir.
- CLI tarafı (`ui/renderer.py`) her zaman gerçek koşuyla da doğrulanabilir
  (Rich `Console` + `io.StringIO`, mevcut `test_renderer.py` deseni).
- Yeni bir model çağrısı EKLENMEZ (RULES: maliyet artışı gerekçesiz
  yapılmaz). Takip önerileri bu yüzden HEURİSTİK üretilir (bkz. Görev 3),
  ekstra bir LLM turu açmaz — bu benim seçtiğim varsayılan; itiraz olursa
  değişir.

## Görev bağımlılıkları ve paralellik

Yedisi büyük ölçüde BAĞIMSIZ (ayrı dosyalar/bileşenler dokunuyor). Öncelik
sırası risk/kapsam'a göre: önce saf/düşük riskli (maliyet göstergesi, arka
plan sayacı), sonra orta (alt ajan kartı, düşünme birleştirme), sonra en
büyük yeniden tasarım (tek kutu), en sona etkileşimli/karmaşık olanlar
(`@` anma, takip önerileri — ikisi de kullanıcı girdisi akışına dokunuyor).

---

### Görev 1: Maliyet göstergesi — küçültülmüş kapsam — TAMAM

**Dosyalar:** `app/src/screens/ContextGauge.tsx` (yanına küçük bir rozet),
`app/src/settings/UsagePanel.tsx` (veri kaynağı olarak REUSE edilir).

CLI TARAFI ZATEN TAM — dokunulmaz. Yalnız masaüstünde composer'ın yanında
`UsagePanel`'in ZATEN çektiği `kullanim.durum` verisinden küçük, sürekli
görünür bir "$X.XX" rozeti eklenir (ikinci bir RPC/veri yolu İCAT EDİLMEZ,
var olan `client.request("kullanim.durum", {})` çağrısı paylaşılır). Sıfır/
ölçülemeyen durumda (ücretsiz modeller çoğunlukla `$0.0000`) `ContextGauge`
ile AYNI ilke: gösterge gürültüye çevrilmez, `$0` ise ya hiç basılmaz ya da
sönük gösterilir (uygulama sırasında karar verilir, ikisi de makul).

### Görev 2: Arka plan işleri sayacı — TAMAM

**Dosyalar:** `cli/repl/loop.py` (`_sync_status_bar`), `tests/test_repl.py`.

- [x] Tasarım KORUNDU: arka plan model çağrılarının CANLI ilerlemesi hâlâ
      basılmaz. Yalnız `BackgroundTasks.pending` (zaten vardı) REPL durum
      çubuğuna "N arka plan işi" olarak eklendi; tur bitince ve slash-komut
      sonrası tazelenir. **Kapsam düzeltmesi:** `background=` yalnız
      İNTERAKTİF REPL'de kuruluyor (`cli/repl/loop.py:122`) — tek-atış
      `fusion agent` ve masaüstü (`appserver/session.py`) hiç kullanmıyor;
      onlarda öğrenme işi zaten INLINE çalışıyor, gösterilecek bir "arka
      plan" kavramı yok. Masaüstüne bunu eklemek YENİ bir altyapı (backend'i
      `background=` ile çağırmaya başlamak) gerektirir — kapsam dışı bırakıldı.

### Görev 3: Alt ajan kartları — BÜYÜK ÖLÇÜDE ZATEN VARDI (düzeltme)

Keşif ajanının "aynı akışa metin olarak karışıyor" bulgusu YANLIŞTI: CLI'de
zaten bir görsel ayraç var — `ui/renderer.py::_channel_header` alt-ajan
kanalı her başladığında `┌ alt-ajan` başlığını AYRI RENKTE (`ACCENT_ALT`)
basıyor ve `test_renderer.py`'de bu doğrulanmış (satır 61-65). Tam bir
kutulu "kart" (Rich `Panel`) değil ama akışı gerçekten ayırıyor. Masaüstü
tarafı (`app/src`) gerçekten karşılıksız — ama bu, ayrı bir IPC şeması
gerektiren daha büyük bir iş; BACKLOG'a düşürüldü, bu turda yapılmadı.

### Görev 4: Düşünme bloğu birleştirme — TAMAM (CLI)

**Dosyalar:** `ui/renderer.py`, `tests/test_renderer.py`.

- [x] Kod okunup karar verildi: `ModelResult.reasoning` (litellm'in
      `reasoning_content` alanından) ile metne gömülü `<think>` etiketi
      GERÇEKTEN farklı kanallar — bazı sağlayıcılar biri, bazıları öteki
      yoldan döndürüyor. Bu yüzden SİLİNMEDİ, `--show-thinking` AÇIKKEN
      `<think>` bloğuyla AYNI sönük stille (`_print_structured_reasoning`,
      `_emit_thinking` ile aynı görsel dil) basılacak şekilde bağlandı.
      `show_call_details`'tan bağımsız — düşünme bir ayrıntı seviyesi değil.
- [ ] Masaüstüne taşıma: BACKLOG'a düşürüldü (kapsam yalnızca CLI ile
      sınırlandı, zaman/risk gerekçesiyle — bkz. Genel Durum).

### Görev 5: Tek kutu — kip ayrımının kaldırılması — TAMAM

**Dosyalar:** `app/src/screens/Composer.tsx`, `app/src/SessionApplication.tsx`,
`appserver/session.py`, testler.

- [x] **Karar (kullanıcıyla netleşti):** "Sohbet"/"Kod" düğmesi kozmetik
      DEĞİLDİ — backend'de `_workspace_mode` doğrudan `chat_mode` bayrağını
      kontrol ediyordu (sohbette dosya yazma TAMAMEN KAPALI). Otomatik bir
      metin sınıflandırıcısı İCAT EDİLMEDİ (ölçülmemiş, riskli); bunun yerine
      backend varsayılanı kalıcı olarak **`kod`** (tam yetenek) yapıldı,
      düğmeler ve ilgili state/RPC çağrısı kaldırıldı. Mekanizmanın kendisi
      (`_apply_workspace_mode`) SİLİNMEDİ, yalnız varsayılan değişti.
- [x] **Bilinen değiş tokuş:** eski "sohbet" varsayılanının gerekçesi
      ("merhaba"da proje taranmasın) artık geçerli değil — her tur, basit bir
      selamda bile proje köküne bağlanıyor. Kullanıcının kendi kararı.
- [x] Testler: `Composer.test.tsx`, `App.test.tsx`, `test_appserver_session.py`
      güncellendi; kip düğmelerinin DOM'da olmadığı ve varsayılan `kip`in
      `kod` olduğu kilitlendi.

### Görev 6: `@` ile dosya anma — BACKLOG (yapılmadı)

Gerçekten eksik (kendi taramamla doğrulandı, `Composer.tsx`'te hiçbir `@`
işleyicisi yok). Kapsamı (tetikleyici, dosya listesi kaynağı, seçim UX'i)
netti ama bu turda zaman/risk bütçesi kalmadı — ayrı, küçük bir görev olarak
açılmalı.

### Görev 7: Takip önerileri — BACKLOG (yapılmadı)

Gerçekten eksik. Heuristik tasarım kararı (§ Genel kısıtlar — yeni model
çağrısı açılmaz) hâlâ geçerli, ama uygulanmadı — ayrı bir görev olarak
açılmalı.

### Görev 8: Gerçek koşuyla doğrulama — KISMEN (yapılanlar için)

- [x] Kalite kapısı: `ruff check . && mypy && pytest -q` (backend) +
      `npm test`/`tsc --noEmit` (masaüstü) — Görev 1, 2, 4, 5 için tam yeşil.
- [ ] Masaüstü: `tauri dev` bu ortamda pratik olmadığından TAM görsel QA
      kullanıcıya bırakılır — açıkça belirtilir, "test ettim" denmez.
