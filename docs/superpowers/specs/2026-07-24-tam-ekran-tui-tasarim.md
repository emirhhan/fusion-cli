# Tam-ekran TUI'ye Geçiş — Tasarım

Tarih: 2026-07-24
Durum: Tasarım onaylandı, planlama bekliyor.

## Bağlam ve Sorun

Fusion REPL şu an **normal terminal tamponunda** çalışıyor: giriş satırı prompt_toolkit,
konuşma çıktısı Rich ile stdout'a akıyor. Bu modelin iki kullanıcı-görünür sorunu var:

1. **Resize'da `❯` / metin çoğalması.** Terminal (macOS Terminal.app gibi geçmiş tamponunu
   yeniden saran emülatörler) yeniden boyutlandırıldığında prompt_toolkit'in bayat imleç
   modeliyle yaptığı silme ıskalıyor; giriş işareti kopyaları birikiyor. Alt durum çubuğu
   (`bottom_toolbar`) etkiyi büyütüyordu. Normal-tampon modelinde temiz bir çözümü yok.
2. **Scrollback'e kaçış.** Yukarı kaydırınca uygulamanın üstündeki eski shell çıktısı
   görünüyor; konuşma uygulama tarafından yönetilmiyor. Claude Code / Hermes gibi araçlarda
   bu olmaz çünkü onlar ekranı tümüyle yönetir.

İkisinin de kök nedeni aynı: uygulama ekranı sahiplenmiyor. Çözüm, **alternatif ekran
tamponunda tam-ekran bir TUI**'ye geçmek.

## Doğrulanmış Teknik Reçete (spike ile kanıtlandı)

Atılabilir spike'lar (`scratchpad/fullscreen_spike*.py`) gerçek Terminal.app'te şunları
ölçtü. Bu reçete tasarımın temelidir:

1. `Application(full_screen=True)` → alternatif ekran. Resize temiz, scrollback izole.
2. `mouse_support=False`. prompt_toolkit'in fare desteği agresif "tüm hareket" takibini
   (`ESC[?1003h`) açıyor; bu Terminal.app'te resize'ı bozuyor. Kapalı tutulur.
3. **`output.reset_cursor_key_mode` override edilir**: prompt_toolkit imleç modunu bir kez
   `?1l` (normal) yapacağına, biz `\x1b[?1h\x1b=` (uygulama imleç + keypad) yaydırırız.
   Terminal.app bu modda fare tekerleğini **ok tuşuna çevirip uygulamaya** yollar; böylece
   kaydırma çalışır ve tekerlek scrollback'e kaçmaz. `less`/`vim`'in yaptığı budur.
   **Kritik:** bu tek seferlik olmalı; her render'da yeniden yaymak Terminal.app'te metin
   patlamasına yol açıyor (bkz. spike geçmişi).
4. Konuşma alanı = kaydırılabilir, salt-okunur. Kaydırma **imleci hareket ettirerek**
   yapılır (pencere kendi içeriğinin imlecini görünür tutar); `vertical_scroll` doğrudan
   sürülürse imleç sondayken her render'da en alta çekilir.
5. Akış = arka plan görevi (`create_background_task`), her parçada `invalidate()`.
6. Çıkışta `\x1b[?1l\x1b>` ile normal moda dönülür.

## Mimari

### Değişmeyen (dokunulmaz)
Motor katmanının tamamı: `engines/`, `providers/`, `memory/`, `core/`, `observability/`,
`config/`, `tools/`. Olay veriyolu (`EventBus`) ve olay tipleri. `renderer.py`'nin Rich
render **mantığı** (markdown, tablo, diff renklendirme, kanal ayrımı) neredeyse aynen kalır.

### Değişen (UI kabuğu)
`cli/repl/` ve `ui/` katmanı. Yeni bir prompt_toolkit `full_screen` Application ekranı
sahiplenir. Doğrulanmış reçete uygulanır.

### ANSI Köprüsü (ana entegrasyon)
`ConsoleRenderer`'ın yazdığı Rich `Console`, stdout yerine bir tampona
(`Console(file=StringIO, force_terminal=True)`) render eder → ANSI üretir. Üretilen ANSI,
konuşma alanının içeriğine eklenir ve prompt_toolkit'in `ANSI` sınıfıyla formatlı metne
çözülür. Böylece tüm Rich biçimlendirmesi (markdown, kod renklendirme, tablolar, renkli
diff) korunur ve render mantığı yeniden yazılmaz.

Akış: `TokenReceived` gibi olaylar `ConsoleRenderer`'a gelir → Rich tampona yazar → köprü
yeni ANSI'yi konuşma buffer'ına ekler → `app.invalidate()`.

### Yerleşim (Layout)
`HSplit`:
- **Banner** (üst; ilk açılışta tam, sonra konuşmanın parçası).
- **Konuşma alanı** — kaydırılabilir, salt-okunur, ANSI. Olaylar buraya akar.
- **Çalışma satırı** — "hazırlanıyor… 3s · token · model". Rich `Live` yerine layout satırı;
  `WorkIndicator`'ın durumundan beslenir, olaylarla güncellenir.
- **Giriş kutusu** — çizgili (Frame). Mevcut `ReplInput` mantığı (geçmiş, tamamlama,
  shift-tab mod döngüsü, yapıştırma katlaması) buraya taşınır.

### Onay/Soru (prompter) — Modal
Motor, `Prompter`/`UserAsker` protokolleri üzerinden kullanıcıya sorar. Full-screen'de
terminal devralınamaz; bunun yerine **modal diyalog** (prompt_toolkit float):
- **Onay:** diff/komut önizlemesi (Rich→ANSI) + evet/hayır. Protokol imzası (`confirm`)
  korunur; içeride modal açılıp cevap `Future` ile döner.
- **Soru:** metin girişli modal. `ask` imzası korunur.
Motor tarafı hiç değişmez; yalnızca `ConsolePrompter`'ın full-screen implementasyonu eklenir.

### REPL Döngüsü
`run_repl` artık "prompt al → tur çalıştır → bas" değil; **event-driven full-screen app**.
Giriş kutusunun `accept_handler`'ı turu arka plan görevi olarak başlatır; çıktı konuşmaya
akar. Ctrl-C çalışan turu keser (mevcut davranış korunur). Öğrenme işleri arka planda sürer.

## Fazlar

Her faz sonunda kalite kapısı (`ruff` + `mypy` + `pytest`) ve commit. Faz yarım bırakılmaz.

1. **Kabuk iskeleti.** full_screen Application + doğrulanmış reçete + banner + boş konuşma
   alanı + giriş kutusu + çalışma satırı. Basit bir "eko" tur uçtan uca. Testler:
   reçete dizilerinin (mouse kapalı, `?1h`, alt-screen) yayıldığı; layout kurulumu.
2. **ANSI köprüsü + akış.** `ConsoleRenderer`'ı tampona yönlendir; olayları konuşmaya akıt;
   gerçek agent turu akarak çalışır. Çalışma göstergesi layout satırına bağlanır.
   Testler: köprünün ANSI'yi doğru eklediği; olay→içerik eşlemesi (saf, konsolsuz).
3. **Onay/soru modalları.** `confirm`/`ask` full-screen implementasyonu; diff önizleme.
   Testler: modal akışı, etkileşimsiz ortam davranışı korunur.
4. **Cila.** Kaydırma "takip modu" (kullanıcı alttaysa yeni içerik takip eder, yukarı
   kaydırdıysa yerinde kalır), resize, yapıştırma katlaması, kısayollar, durum bilgisi.
5. **Geçiş.** Eski normal-tampon REPL yolunu değiştir; ölü Rich-Live/prompter yollarını
   temizle; `app.py` yeni kabuğu çağırır. Tam süit yeşil.

## Sınırlar (Non-goals)
- Motor davranışını değiştirmek (birebir korunur).
- iTerm2/VS Code/Warp için özel yollar — önce Terminal.app'te doğru çalışsın; reçete
  standart dizilere dayandığı için diğerlerinde de çalışması beklenir ama hedef bu spike'ta
  Terminal.app.
- Fare ile metin seçme/kopyalama iyileştirmeleri (alternatif ekranda ayrı bir konu).

## Riskler ve Karşılıklar
- **Uzun oturumda ANSI tamponu büyümesi.** Konuşma içeriği sınırlanır/kırpılır (ör. son N
  satır tutulur, üstü "…" ile). Faz 4'te ele alınır; erken fazda basit tutulur.
- **Modal diff önizlemesi.** Rich diff → ANSI, modal içinde. Faz 3.
- **Reçete kırılganlığı.** `reset_cursor_key_mode` override'ı prompt_toolkit iç davranışına
  bağlı; sürüm sabitlenir (3.0.52) ve testle işaretlenir. Kırılırsa tek noktada düzeltilir.
- **Test edilebilirlik.** Full-screen etkileşim headless test edilemez; mantık (köprü,
  olay→içerik, prompter kararları) saf fonksiyonlara ayrılıp konsolsuz test edilir. Görsel
  doğrulama gerçek terminalde elle yapılır (spike harness'leri referans).

## Test Stratejisi
- Saf birim testler: ANSI köprüsü (olay→ANSI→içerik), çalışma göstergesi durumu, prompter
  karar mantığı, yapıştırma katlaması (mevcut testler taşınır).
- Reçete dizisi testleri: pty ile başlangıç escape dizilerinin doğruluğu (mouse kapalı,
  `?1h`, `?1049h`) — spike harness'lerindeki yöntem.
- Görsel/etkileşim: gerçek Terminal.app'te elle (resize, kaydırma, akış, modal).

## Referanslar
- Doğrulama spike'ları: `scratchpad/fullscreen_spike4.py` (nihai), `*_spike[1-3].py` (evrim).
- Reçete escape dizileri ve pty ölçüm yöntemi spike sürücülerinde.
