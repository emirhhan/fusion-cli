# Faz 2 — ANSI Köprüsü + Gerçek Akış Tasarımı

> Bu doküman, tam-ekran TUI geçişinin Faz 2'sini tanımlar. Genel tasarım ve
> reçete için bkz. [2026-07-24-tam-ekran-tui-tasarim.md](2026-07-24-tam-ekran-tui-tasarim.md).
> Faz 1 (kabuk iskeleti) tamamlandı ve gerçek Terminal.app'te elle doğrulandı.

## Amaç

Gerçek motor turlarını (fusion + agent) tam-ekran kabuğa akıtmak. Rich
biçimlendirmesi (markdown, kod renklendirme, tablo, renkli diff) bir **ANSI
köprüsü** ile korunur: `ConsoleRenderer`'ın Rich render mantığı yeniden
yazılmaz, çıktısı bir tampona yönlendirilip üretilen ANSI konuşma alanına akıtılır.

Kabuk hâlâ gizli `FUSION_FULLSCREEN=1` bayrağı arkasındadır; mevcut normal-tampon
REPL davranışı DEĞİŞMEZ (geçiş Faz 5).

## Kararlar (brainstorm çıktısı)

- **ANSI kontrolü Faz 2 içinde çözülür** (ayrı ön-spike yapılmaz).
- **Her iki motor akar** (fusion + agent).
- **Onay/soru:** Faz 2'de prompter etkileşimsiz fallback davranışını kullanır
  (`confirm → False`, `ask → cevap yok`). Gerçek modallar Faz 3.
- **Çalışma satırı olay-beslemelidir** (canlı: süre · token · model); Rich `Live`
  devre dışı bırakılır.

## Global Kısıtlar

- Kod içi her şey Türkçe: docstring, yorum, log, hata ve kullanıcıya görünen
  metinler. Tanımlayıcılar İngilizce + PEP 8.
- Motor/çekirdek katmanına DOKUNULMAZ: `engines/`, `providers/`, `memory/`,
  `core/`, `config/`, `tools/`, `observability/`. Olay veriyolu (`EventBus`) ve
  olay tipleri değişmez. `ui/renderer.py`'nin Rich render **mantığı** korunur.
- Mevcut normal-tampon REPL yolu (`FUSION_FULLSCREEN` bayrağı YOKken) DEĞİŞMEZ.
- prompt_toolkit 3.0.52'ye sabit; reçete bu sürümün iç davranışına dayanır.
- Her birim sonunda kalite kapısı: `ruff check` + `mypy` + `pytest` üçü de temiz
  olmadan commit yok. Commit mesajları conventional commit, Türkçe açıklama,
  faz/adım numarası GEÇMEZ, author/co-author eklenmez.

## Mimari

### Entegrasyon yüzeyi (mevcut, değişmez)

- `ConsoleRenderer` (`ui/renderer.py`) bir sink/subscriber'dır: `handle(event)`
  ile olayları alır ve bir Rich `Console`'a yazar. Kurucusuna `console` verilebilir.
- Fusion turu: `run_task(..., sinks=(renderer, cost, tracer))`.
- Agent turu: `EventBus()` üzerinden `bus.subscribe(renderer)`; `ConsolePrompter`
  onay/soru için kullanılır.
- `ConsolePrompter` (`cli/prompter.py`) etkileşimsizken (`sys.stdin.isatty()`
  False) `confirm → False`, `ask → cevap yok` döndürür; etkileşimliyken Rich
  `Prompt.ask`/`Confirm` ile stdin okur.

### Birimler

Her birim tek sorumluluk taşır, iyi tanımlı bir arayüzle konuşur ve bağımsız
test edilir.

#### 1. `AnsiBridge` — ANSI köprüsü (saf çekirdek)

- **Ne yapar:** İçinde bir `Console(file=StringIO, force_terminal=True)` tutar.
  Bu console `ConsoleRenderer`'a verilir. Her olay işlendikten sonra StringIO'nun
  **yeni delta'sını** (o ana kadar okunmamış kısmı) okuyup biriken ANSI metnine
  (`text`) ekler.
- **Arayüz:**
  - `AnsiBridge()` — köprüyü ve tamponlu console'u kurar.
  - `console -> Console` — `ConsoleRenderer`'a verilecek tamponlu console.
  - `drain() -> str` — StringIO'da biriken yeni delta'yı döndürür ve `text`'e ekler.
  - `text -> str` — o ana kadar birikmiş tüm ANSI.
- **Bağımlılık:** Rich `Console`, `io.StringIO`. Terminal/gerçek konsol GEREKMEZ.
- **Test:** Saf birim. Bir `ConsoleRenderer(bridge.console)` kurulur, sahte/gerçek
  bir olay `handle` edilir, `drain()` sonrası `text` beklenen ANSI'yi içerir.

#### 2. ANSI konuşma kontrolü + kaydırma

- **Ne yapar:** `FusionScreen._conversation`, düz `TextArea` yerine
  `FormattedTextControl(lambda: ANSI(bridge.text))` sarılı, salt-okunur,
  kaydırılabilir bir `Window` olur.
- **Kaydırma modeli değişir:** ANSI `FormattedTextControl`'ün düzenlenebilir bir
  buffer'ı/imleci yoktur; Faz 1'in imleç-tabanlı `scroll_lines`'ı yerine
  doğrudan `window.vertical_scroll` sürülür (imleç olmayınca prompt_toolkit
  vertical_scroll'u her çizimde sıfırlamaz, değer stabildir).
- **Temel takip modu:** Kullanıcı en alttaysa (`vertical_scroll` maksimumdaysa)
  yeni içerik geldikçe alta yapışır; kullanıcı yukarı kaydırdıysa yerinde kalır.
  Gelişmiş takip/kırpma Faz 4.
- **Arayüz (screen.py):**
  - `scroll_window(window, delta)` — `window.vertical_scroll`'u `delta` satır
    taşır, `[0, max]` içinde sınırlar.
  - `follow_bottom(window, content_height, viewport_height)` — kullanıcı alttaysa
    en alta çeker.
- **Bağımlılık:** prompt_toolkit `Window`, `FormattedTextControl`, `ANSI`.
- **Test:** `scroll_window` clamp (üst/alt sınır) ve `follow_bottom` mantığı saf
  test edilir (sahte window durumu). Görsel doğrulama gerçek terminalde.
- **Risk:** Bu birim planın işaret ettiği risk noktasıdır; kendi elle görsel
  doğrulamasını alır. Kırılırsa tek noktada düzeltilir.

#### 3. Çalışma satırı — olay beslemeli

- **Ne yapar:** Bridged renderer'da Rich `Live` **devre dışı** bırakılır (yoksa
  spinner/imleç kaçış dizileri konuşma tamponuna sızar). İş olayları
  (başladı / token / bitti) `WorkIndicator` durumundan çalışma satırı
  `FormattedTextControl`'ünü günceller: "hazırlanıyor… Ns · token · model".
- **Arayüz:** `FusionScreen` bir `set_work(text: str)` / `clear_work()` sunar;
  köprü/renderer iş durumundan bu satırı besler ve `app.invalidate()` çağırır.
- **Bağımlılık:** `WorkIndicator` durumu (Live davranışı değil, sayaç/etiket
  verisi). Renderer'ın Live'ı kapatan bir bayrağı/yolu gerekir.
- **Test:** İş durumu → çalışma satırı metni eşlemesi saf test edilir.

#### 4. Turu kabuğa bağlama

- **Ne yapar:** Giriş kutusunun `accept_handler`'ı, turu bir arka plan görevi
  (`asyncio.ensure_future`) olarak başlatır. `_dispatch` mantığı (fusion→sinks /
  agent→EventBus) bridged renderer ile çalışır; çıktı köprü üzerinden konuşmaya
  akar. Her olaydan sonra `drain()` + `app.invalidate()`.
- **Onay:** `ConsolePrompter` etkileşimsiz fallback ile kullanılır (Faz 2'de
  full-screen'de stdin okunamaz). Manuel onay isteyen araçlar geçici olarak
  reddedilir; gerçek modal Faz 3.
- **İptal:** Ctrl-C çalışan turu keser (mevcut davranış korunur).
- **Arayüz:** `FusionScreen.on_submit`, turu başlatan bir koşucuya bağlanır.
- **Test:** Sahte motor/olay üreticisiyle dispatch bağlanması; olayların
  konuşmaya aktığı ve çalışma satırının güncellendiği doğrulanır (konsolsuz).

#### 5. Çalıştırıcı

- **Ne yapar:** `run_screen_demo` eko yerine gerçek turu çalıştıran akışa
  dönüşür (ya da yeni bir `run_screen_repl` eklenir). Hâlâ `FUSION_FULLSCREEN=1`
  arkasında; `run_repl`'in mevcut yolu değişmez.
- **Test:** Çalışan event loop içinde await edilebilirlik korunur (Faz 1
  regresyon testi deseni); gerçek `app.run_async()` mock'lanır.

### Veri akışı

```
kullanıcı girişi (accept_handler)
  → tur arka plan görevi başlar (ensure_future)
  → motor olayları → ConsoleRenderer (bridge.console'a Rich yazar)
  → AnsiBridge.drain() → konuşma ANSI metni büyür
  → iş olayları → çalışma satırı güncellenir
  → app.invalidate() → FormattedTextControl(ANSI(...)) yeniden çizilir
  → takip modu: kullanıcı alttaysa en alta yapışır
```

## Test Stratejisi

- **Saf birim testleri:** ANSI köprüsü (olay→delta→birikmiş metin, StringIO ile),
  çalışma satırı durum eşlemesi, `scroll_window` clamp + `follow_bottom`, dispatch
  bağlanması (sahte motor). Konsol/terminal gerektirmez.
- **Elle (gerçek Terminal.app):** renkli markdown/kod/diff akışı, kaydırma ve
  takip modu, resize sırasında bozulma olmaması, Ctrl-C ile tur kesme, Ctrl-Q ile
  temiz çıkış.
- Her birim sonunda kalite kapısı (`ruff` + `mypy` + `pytest`).

## Kapsam Dışı (Non-goals)

- Onay/soru modalları (Faz 3).
- Uzun oturumda konuşma içeriğinin kırpılması / son-N-satır (Faz 4).
- Gelişmiş takip modu ve kaydırma cilası (Faz 4).
- Eski normal-tampon REPL yolunun kaldırılması ve ölü Rich-Live / prompter
  yollarının temizliği (Faz 5).
- Motor davranışını değiştirmek (birebir korunur).
- iTerm2/VS Code/Warp özel yolları (hedef Terminal.app).

## Riskler ve Karşılıklar

- **ANSI kontrolü + kaydırma davranışı** yalnızca gerçek terminalde tam doğrulanır
  (Faz 1 reçetesi gibi). Birim 2 kendi elle doğrulamasını alır; kırılırsa tek
  noktada düzeltilir.
- **Rich `Live` sızması:** Bridged renderer'da Live devre dışı bırakılarak
  spinner/imleç dizilerinin konuşma tamponuna girmesi engellenir. Live'ı kapatan
  yol, motor katmanına değil yalnızca UI köprüsüne dokunur.
- **Uzun oturumda ANSI tamponu büyümesi:** Faz 2'de basit tutulur (tüm metin
  birikir); kırpma Faz 4'te ele alınır.
- **Onay boşluğu:** Faz 2'de manuel onay isteyen araçlar reddedilir; bu geçici
  ve dokümante bir davranıştır, Faz 3'te gerçek modalla giderilir.
