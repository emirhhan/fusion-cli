# Fusion-CLI

Ücretsiz LLM'lerle çalışan, terminalde yaşayan bir kodlama asistanı.

> **Durum: 0.3.0a6 (alpha).** Değişiklikler: [CHANGELOG.md](CHANGELOG.md). Çekirdek akış çalışır durumda ve test kapsamı geniştir;
> arayüzde ve model davranışında bilinen kısıtlar vardır. Açık başlıklar için
> [docs/BACKLOG.md](docs/BACKLOG.md).

## Kurulum

Python 3.11+ gerekir.

### macOS / Linux

```bash
git clone https://github.com/emirhhan/fusion-cli && cd fusion-cli
./setup.sh
```

### Windows (PowerShell)

```powershell
git clone https://github.com/emirhhan/fusion-cli; cd fusion-cli
.\install.ps1
```

Kurulum izole ve **global**dır: `uv` varsa onunla, yoksa `pipx`, o da yoksa
kullanıcı dizininde adanmış bir sanal ortamla kurar. Sistem Python'ın kirlenmez.

### Kurulum sonrası

Herhangi bir proje dizininde:

```bash
fusion
```

Repo klasörüne dönmen, `.venv` yolu yazman ya da `activate` çalıştırman gerekmez.
Kurulum sırasında API anahtarların **sorulur** (yazarken ekranda görünmez) ve 83
küratörlü ders belleğe yüklenir — ilk turundan itibaren eğitilmiş başlarsın.

`fusion` komutu bulunamazsa `fusion doctor` PATH'e ne ekleyeceğini kabuğuna göre
söyler. Kullanıcı dosyalarına habersiz dokunulmaz.

### Geliştirici kurulumu

```bash
git clone https://github.com/emirhhan/fusion-cli && cd fusion-cli
./setup.sh --dev      # Windows: .\install.ps1 -Dev
make check
```

Kullanıcı kurulumundan farkı: repo içinde `.venv`, **editable** kurulum ve proje
bazlı `.env`. Koddaki değişikliği anında görürsün.

### API anahtarları

| Sağlayıcı | Durum | Nereden |
|-----------|-------|---------|
| **OpenRouter** | önerilen taban | <https://openrouter.ai/keys> |
| NVIDIA NIM | opsiyonel, ayrı kota | <https://build.nvidia.com/> |

İkisi de ücretsizdir. Kurulum sihirbazı ikisini de sorar; NIM Enter ile atlanır.

Anahtarlar **tek yerde** tutulur:

- macOS/Linux: `~/.config/fusion-cli/.env`
- Windows: `%APPDATA%\fusion-cli\.env`

Dosya `0600` ile yazılır. Proje kökündeki `.env` yalnızca geliştirici kurulumunda
oluşur ve isteğe bağlı bir override'dır.

Anahtarların okunma önceliği:

1. Gerçek ortam değişkenleri (kabukta verilen)
2. `FUSION_HOME` / proje kökü
3. Kullanıcı yapılandırma dizini

Boş bırakılmış bir satır "bu anahtar yok" demektir; sonraki dosyadaki gerçek
anahtarı gölgelemez.

### Kurulumu denetle

```bash
fusion doctor          # sürüm, dizinler, anahtarlar, roller, PATH — ağa çıkmaz
fusion doctor --json   # betikler için
fusion doctor --live   # sağlayıcılara küçük gerçek çağrı (kota harcar)
```

Her sorun için ne yanlış, neden önemli ve ne yapılacağı yazılır. **API anahtarının
kendisi hiçbir çıktıda gösterilmez** — en fazla "ayarlı".

### Güncelleme ve kaldırma

```bash
fusion update      # kurulum yöntemini tespit edip doğru komutu gösterir
fusion uninstall   # aynı şekilde; yapılandırma ve dersler KORUNUR
fusion uninstall --purge   # anahtarlar ve bellek dahil her şeyi sil
```

### Dosya konumları

| Ne | macOS/Linux | Windows |
|----|-------------|---------|
| Yapılandırma + anahtar | `~/.config/fusion-cli/` | `%APPDATA%\fusion-cli\` |
| Bellek (dersler, indeks) | `~/.local/share/fusion-cli/memory` | `%LOCALAPPDATA%\fusion-cli\memory` |

`FUSION_CONFIG`, `FUSION_HOME` ve `FUSION_MEMORY_DIR` ile taşınabilir.

### Yerel model kullanımı

Bulut sağlayıcı zorunlu değildir. `config.yaml` içinde yerel bir uç tanımlarsan
anahtarsız çalışırsın:

```yaml
agent:
  name: yerel
  model: ollama/qwen2.5-coder:7b
```

vLLM / LM Studio için `openai/<model>` + `OPENAI_API_BASE=http://localhost:8000/v1`.
`fusion doctor` bu durumda da "hazır" der: tanınmayan sağlayıcılar engellenmez.

### Sorun giderme

| Belirti | Ne yapmalı |
|---------|-----------|
| `fusion: command not found` | `fusion doctor` PATH satırını verir |
| "Ücretsiz kota doldu" | `/provider` ile tek sağlayıcıya kilitlen ya da `/level low` |
| "Hiçbir model yanıt veremedi" | `fusion doctor --live` |
| Kurulum yarıda kaldı | Betik durduğu adımı yazar; düzeltip tekrar çalıştır (idempotent) |

### Tarayıcı doğrulaması (opsiyonel)

Web arayüzü üreten görevlerde konsol hatası, yüklenmeyen görsel ve yatay taşma
ölçümü istiyorsan:

```bash
.venv/bin/pip install "fusion-cli[web]" && .venv/bin/playwright install chromium
```

Kurulmazsa o kapı sessizce atlanır; fusion çevrimdışı çalışmaya devam eder.


## Değerlendirme (eval)

Agent'ın gerçekten iş yapıp yapmadığı ölçülür — birim testlerinden ayrı bir şeydir.
Testler kodun doğru olduğunu gösterir; eval agent'ın görevi becerdiğini.

```bash
.venv/bin/python -m evals run evals/suite/starter.yaml
```

Taban ölçüm (2026-07-26, `low` kademesi, NVIDIA NIM, `--repeat 3` = 42 koşu):
**12/14 görev her koşuda geçiyor.** İki görev kararsız — `hello-calisir` 2/3,
`coklu-dosya-degisikligi` 1/3.

```bash
# Tek koşu karar desteklemez: bir ayarın etkisini ölçerken 3-5 tekrar kullan.
.venv/bin/python -m evals run evals/suite/starter.yaml --repeat 3
```

Kararsız görevler özetin sonunda adıyla listelenir. Bu önemli: bir görev bazen
geçip bazen kalıyorsa o yetenek güvenilir değildir ve "geçti" diye raporlamak
yanıltıcı olur. Aynı sebeple `--repeat` olmadan yapılan A/B karşılaştırmaları
(workflow_mode açık/kapalı gibi) gürültüden ayırt edilemez.

Set iki farklı şeyi ölçer ve bunlar tek onay duruşuyla ölçülemez:

- **Yetenek** görevleri (bug fix, pytest çıktısını okuyup düzeltme, çok dosyalı
  değişiklik, regresyon testi yazma) olağan işe evet diyen kullanıcıyı modeller.
- **Güvenlik** görevleri (`approval: strict`) onay VERMEYEN kullanıcıyı modeller:
  ölçülen şey "agent yasak işi onay almadan yapabiliyor mu". Kök dışına yazma ve
  dosyadan gelen prompt injection burada sınanır.

Görevler `setup` ile başlangıç dosyası taşıyabilir; bozuk kodu hazır koymadan bug
fix ölçülemez.

## Kullanım

Argümansız çalıştırınca interaktif oturum açılır:

```bash
.venv/bin/fusion
```

Ekran temizlenir, karşılama tam genişlikte açılır ve giriş alanı ekranın altına iner:

```
╭─ Fusion CLI 0.3.0 ──────────────────────────────────────────────────────────────╮
│                                                                                 │
│  ███████╗██╗   ██╗███████╗██╗ ██████╗ ███╗   ██╗    İpucu                       │
│  ██╔════╝██║   ██║██╔════╝██║██╔═══██╗████╗  ██║    Karmaşık bir görevde        │
│  █████╗  ██║   ██║███████╗██║██║   ██║██╔██╗ ██║    shift-tab ile plan moduna…  │
│  ██╔══╝  ██║   ██║╚════██║██║██║   ██║██║╚██╗██║    ─────────────────────────── │
│  ██║     ╚██████╔╝███████║██║╚██████╔╝██║ ╚████║    Fusion nedir?               │
│  ╚═╝      ╚═════╝ ╚══════╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝    Ücretsiz LLM'lerle çalışan… │
│                                                                                 │
╰─────────────────────────────────────────────────────────────────────────────────╯
  motor agent  ·  onay auto  ·  model nemotron-super  ·  bellek açık · 28 ders



❯ mesajını yaz
```

Model çalışırken canlı bir satır ne olduğunu ve ne kadar sürdüğünü gösterir; tur
bitince tek satırlık özete iner:

```
⠋ hazırlanıyor…  3s · 231 token · nemotron-super     ← çalışırken
✦ 4.1s · 1.2k token · nemotron-super                 ← bitince
```

Alttaki durum çubuğu ekrana sabittir ve onay modu değişince kendiliğinden güncellenir.
İpucu çalışma dizinine göre seçilir: aynı projede hep aynı, farklı projede farklı.
Dar terminalde büyük imza tek satırlık sürümüne iner; hiçbir genişlikte taşma olmaz.

**shift-tab** onay modunu döndürür · **Ctrl-C** çalışan turu durdurur (oturumdan
çıkmaz) · **Ctrl-D** çıkar. Komut listesi için `/help`.

| Grup | Komutlar |
|------|----------|
| Motor | `/agent` `/fusion` |
| Onay | `/auto` `/plan` `/security` |
| Agent | `/reset` `/compact` `/verify` `/undo` |
| Fusion | `/type <tip>` `/all` `/synth` |
| Bellek | `/good` `/bad` `/revise` `/learn <kural>` `/seed` `/reindex` `/stats` `/lessons` |
| Model | `/level [kademe]` `/development` `/provider` |
| Bilgi | `/models` `/model` `/cost` `/help` `/clear` `/exit` |
| Makro | `/goal` `/grill-me` `/bug` `/commit` `/review` `/browser` `/schedule` |

**Güvenlik ve geri alma.** Dosya araçları varsayılan olarak yalnızca proje kökü
altında çalışır; başka bir dizine erişim `--add-dir` ile açıkça verilir. Kabuk
komutlarında yalnızca tanınan ve yan etkisiz olanlar onaysız çalışır, kalan her
şey sorulur. `/undo` son turun dosya değişikliklerini geri alır — yalnızca
agent'ın dokunduğu dosyaları, seninkilere dokunmadan.

**Doğrulama kapısı.** `/verify` projeni tanır (pytest, ruff, mypy, npm scriptleri,
cargo, go, make) ve bulduğu komutları gösterir; onaylarsan her turdan sonra
çalışır. Kapı düşerse hata çıktısı modele geri verilir ve agent düzeltmeyi dener.

Ders çıkarımı **arka planda** çalışır: bir sonraki komutu beklemez, oturum
kapanırken tamamlanması beklenir. Agent modeli oturum açılırken arka planda ısıtılır;
soğuk bir uç ilk turu bekletmez.

**Makrolar** sık yapılan işleri tek komuta indirir:

```
/goal <görev>       hedefe ulaşana kadar pes etme (adım sınırı yükselir)
/grill-me <görev>   kod yazmadan önce gereksinimleri sorularla netleştir
/bug [ipucu]        hatayı bul, kök nedeni tespit et, düzelt, doğrula
/commit [bağlam]    değişiklikleri incele ve conventional commit ile kaydet
/review [odak]      güvenlik ve mimari açısından code review
/browser <konu>     web'de araştır ve kaynaklarıyla özetle
```

**Kademe seçimi** — `/level` tüm motoru tek seçimle bir seviyeye alır. Seçim ekranı
ok tuşlarıyla gezilir ve merdiven logodaki gibi turuncudan pembeye boyanır. Merdivenin
tamamı **ücretsiz** havuzdan kurulur; bir kademe seçmek fatura üretmez.

Merdivenin omurgası **NVIDIA NIM**'dir: OpenRouter'ın ücretsiz kotası günde 50
istekle sınırlıyken NIM'inki çok daha geniş. OpenRouter modelleri yedek olarak
kalır, böylece yalnızca OpenRouter anahtarı olan kullanıcı da çalışır.

| Kademe | Model | Ölçülen | Neden |
|--------|-------|---------|-------|
| `low` | nemotron-3-super-120b-a12b | ~0.5s | varsayılan — en hızlısı |
| `medium` | gpt-oss-120b | ~1s | farklı aile, akıl yürütme |
| `high` | deepseek-v4-flash | ~6s | kodlamada güçlü aile |
| `ultra` | nemotron-3-ultra-550b-a55b | ~6s | 550B/55B, ağır işler |
| `premium` | glm-5.2 | ~40s | 1M bağlam — en yetenekli, ama yavaş |

Süreler gerçek çağrılarla ölçüldü. Modeller katalogdan değil **yoklanarak**
seçildi: NIM kataloğundaki birçok model listelenmesine rağmen `NotFound` dönüyor
ya da zaman aşımına uğruyor.

```
/level                              seçim ekranını aç
/level premium                      ekran açmadan doğrudan uygula
```

**Kaynak seçerek model değişimi** — `/development` önce kaynağı, sonra canlı
katalogdan modeli sorar. Seçilen model agent, hakem ve havuzun tamamına uygulanır.

```
1. OpenRouter modelleri (ücretsiz)
2. NVIDIA modelleri (ücretsiz)     NVIDIA_NIM_API_KEY ister
3. OpenRouter modelleri (ücretli)  seçilirse uyarı verilir
4. Özel model                      istediğin alias'ı gir (ör. ollama/qwen2.5-coder:7b)
```

İki komutun seçimi de `config.yaml`'a **kalıcı** yazılır; dosyadaki diğer ayarlar korunur.

**Tekil model değişimi** oturum içinde yapılabilir:

```
/model                              etkin modelleri listele
/model agent <id>                   agent modelini değiştir
/model cand <ad|no> <id>            bir fusion adayını değiştir
/model add <ad> <id> [etiket…]      havuza aday ekle
/model rm <ad>                      havuzdan aday çıkar
```

### Skill ve agent kütüphanesi

Claude Code ekosistemindeki uzman talimatlar ve ajanlar otomatik bulunur:
`~/.claude/skills/**/SKILL.md`, `~/.claude/agents/*.md` ve projenin `.claude/` dizini.

Agent bunları `find_skill` / `read_skill` / `find_agent` ile **arar** — liste prompta
basılmaz, bağlam boşa harcanmaz. `invoke_agent` ile bir uzmana alt görev devredilir;
uzman kendi talimatı ve (bildirdiyse) kısıtlı araç setiyle çalışır.

Kütüphanede içerik yoksa bu araçlar modele hiç sunulmaz.

### Tek seferlik kullanım

```bash
.venv/bin/fusion run "Python'da bir dosyayı satır satır nasıl okurum?"
.venv/bin/fusion run "bir REST API tasarla" --type code    # görev tipine göre model önceliği
.venv/bin/fusion run "2+2?" --all                          # tüm aday cevaplarını göster
.venv/bin/fusion run "kısa cevapla" --no-synthesis         # hakemin seçtiği cevabı göster
.venv/bin/fusion run "kısa cevapla" --quiet                # ilerleme satırlarını gizle
.venv/bin/fusion run "..." --json                          # olayları JSONL olarak yaz
.venv/bin/fusion models                                    # yapılandırılmış modeller
.venv/bin/fusion models --fetch                            # canlı katalogdan ücretsiz modeller
.venv/bin/fusion config show                               # etkin yapılandırma
.venv/bin/fusion version
```

### Agent modu

```bash
.venv/bin/fusion agent "hesap.py'daki hatayi bul ve duzelt, sonra testleri calistir"
.venv/bin/fusion agent "..." --mode plan       # yalnız planla, hiçbir şeyi değiştirme
.venv/bin/fusion agent "..." --mode security   # her değişikliği tek tek sor
```

Agent dosya okur/yazar, komut çalıştırır, web'de arar, görev listesi tutar, zor
kararlarda çoklu modele danışır (`council`) ve büyük işleri alt-ajana devreder.

**Onay modları:**

| Mod | Davranış |
|-----|----------|
| `auto` (varsayılan) | Değiştirici işlemlere otomatik evet — **ama** yıkıcı komutta (rm -rf, force push) yine sorar |
| `plan` | Hiçbir değişiklik yapılmaz; yalnızca uygulanabilir bir plan üretilir |
| `security` | Her değiştirici işlem diff önizlemesiyle tek tek sorulur |

Onay istenen her işlem için **önce ne olacağı gösterilir**: dosya değişikliklerinde
renkli unified diff, kabuk komutlarında çalıştırılacak komutun kendisi.

Etkileşimsiz ortamda (CI, boru hattı) onay alınamazsa işlem **reddedilir** — sessizce
"evet" varsayılmaz.

### Öğrenen bellek

Sistem kullandıkça iyileşir. Üç ayrı bellek vardır:

```bash
.venv/bin/fusion memory seed        # 28 küratörlü başlangıç dersini yükle
.venv/bin/fusion memory reindex     # kod tabanını anlamsal indeksle (artımlı)
.venv/bin/fusion memory stats       # hangi model hangi görevde iyi
.venv/bin/fusion memory lessons     # agent ne öğrendi
.venv/bin/fusion memory where       # bellek diskte nerede
.venv/bin/fusion feedback general nemotron-super good
```

| Bellek | Ne yapar |
|--------|----------|
| **Performans** | Her fusion turunda adayların puanı/gecikmesi kaydedilir; sonraki turda sıralama buna göre değişir. Ölçüt: ortalama puan − hafif gecikme cezası (ceza 0.1 ile sınırlı, hız kaliteyi ezmez). |
| **Ders** | Agent her görevden somut dersler çıkarır; benzer bir görevde bunlar sistem promptuna geri enjekte edilir. Alakasız dersler mesafe eşiğiyle elenir — prompt gürültüyle zehirlenmez. |
| **Kod indeksi** | `search_codebase` aracını besler. Artımlıdır: parça kimliği içeriği kapsadığı için değişmemiş dosyalar yeniden gömülmez. |

Bellek istenmezse `--no-memory`; erişilemezse uygulama **boş belleğe düşer ve
çalışmaya devam eder**, sessizce öğrenmemek yerine durumu bildirir.

### Fusion nasıl çalışır

1. Görev tüm adaylara **paralel** sorulur. Her adayın kendi yedek zinciri vardır ve
   yedekler birincil ile **aynı anda** denenir; ilk başarılı yanıt kazanır.
2. Yeterli cevap geldiğinde yavaş adaylara kısa bir ek süre tanınır, sonra kesilir.
   İlk cevaptan itibaren mutlak bir üst sınır işler: soğuk bir uç turu kilitleyemez.
3. **Hakem ve sentez paralel çalışır** — ikisi de yalnızca aday cevaplarını okur, biri
   diğerini beklemez. Gecikme ikisinin toplamı değil, uzun olanı kadardır.
4. Hakem yetişemez ya da bozuk çıktı verirse sezgisel kazanan seçilir; sentez cevabı
   yine üretilir. Kullanıcı hiçbir senaryoda beklemede kalmaz.

## Web çıktısı doğrulaması

Agent bir web sayfası ürettiğinde çıktısı mekanik olarak denetlenir ve bulunan somut
ihlaller modele düzeltme talimatı olarak geri verilir. Ölçüldü: model prompt'taki
kuralları sıkça atlıyor, araç sonucuna ise tepki veriyor.

Denetlenenler: kapanmış görsel servisleri, boş bağlantı (`href="#"`), eksik `<main>`,
CSS'te karşılığı olmayan sınıf oranı, sayfada vaat edilen tutarın kodda bulunmaması,
paletin dışından elle yazılmış renk, üretildiği hâlde HTML'den bağlanmamış CSS/JS,
ölçek dışı boşluk değeri. `[web]` ekstrası kuruluysa ayrıca sayfa gerçekten açılıp
ölçülür: konsol hataları, yüklenemeyen kaynaklar, yatay taşma, orantısız ikon, 24×24
altındaki dokunma hedefleri, başlığı olup içi boş bölümler.

Web görevlerinde agent ilk iş olarak `scaffold_web` ile hazır bir iskele yazar:
`tokens.css` (ölçekler ve bileşen stilleri), `format.js` (doğru para/tarih
biçimlendirmesi) ve doğru bölüm sıralı `index.html`. Var olan dosyanın üzerine yazmaz.

Kapılar yalnızca HTML üretilen turlarda çalışır; Python, Node ya da doküman
işlerinde sessizdir. Kapatmak için `runtime.web_verification` ve
`runtime.browser_verification` ayarları `false` yapılır.

## Yapılandırma

Varsayılanların tek kaynağı pakete gömülü `src/fusion_cli/config/defaults.yaml`'dır.
Kendi ayarların bunun **üzerine** birleştirilir; yalnızca değiştirmek istediğin anahtarı
yazman yeterlidir:

```yaml
# config.yaml — çalıştığın dizinde ya da ~/.config/fusion-cli/ altında
runtime:
  max_tokens: 4096
```

Arama sırası: `$FUSION_CONFIG` → `$FUSION_HOME/config.yaml` → `./config.yaml` →
`~/.config/fusion-cli/config.yaml`. Hiçbiri yoksa yalnızca gömülü varsayılanlar geçerlidir.

Bilinmeyen bir anahtar ya da yanlış tip sessizce yok sayılmaz; anlaşılır bir hata verir.

## Mimari

Bağımlılık yönü tek yönlüdür; ok tersine import yapılmaz:

```
cli → ui → engines → { providers, memory, observability } → config → core
```

- **`core`** — tipler, protokoller, olaylar, hatalar. Üçüncü parti bağımlılığı yoktur.
- **`providers`** — LLM adaptörleri. `RetryingProvider` geçici arızada **aynı**
  modeli tekrar dener, `FallbackProvider` o da tükenince **sıradaki** modele geçer,
  `EventingProvider` çağrı yaşam döngüsünü olaya çevirir. Zincir sıralıdır: seçilen
  model, yedeği daha hızlı diye turu kaptırmaz. Yeni bir sağlayıcı eklemek
  dayanıklılık davranışını bedava getirir.
- **`observability.bus`** — olay veriyolu. Motorlar konsolu **hiç tanımaz**; tiplenmiş
  olay yayınlar, veriyolu bunları **sırayla** dinleyicilere dağıtır. Çıktı çakışması
  yapısal olarak imkânsızdır.
- **`engines.fusion`** — paralel adaylar, hakem, sentez. Kullanıcıya gösterilecek METİN
  üretmez: `VerdictSource` gibi semantik kodlar döner, metni `ui` seçer.
- **`core.concurrency`** — zaman bütçeli paralel toplama (straggler kesme + mutlak üst
  sınır). Modelden ve sağlayıcıdan bağımsızdır; sahte gecikmelerle test edilir.
- **`engines.agent`** — tool-calling döngüsü. Refleksiyon (araç hatasında yön verme,
  ek model çağrısı yok), otomatik devam, öz-denetim (denetçi model + tek düzeltici tur)
  ve alt-ajan devri. Onay bir protokolün arkasındadır; motor hangi modda olduğunu bilmez.
- **`memory`** — üç bellek de `core.memory` protokollerinin arkasındadır; motorlar
  ChromaDB'yi tanımaz. `--no-memory` "hiçbir şey yapmayan" bir uygulama vererek
  karşılanır, motor kodunda `if bellek varsa` dalı oluşmaz.
- **`tools`** — kayıt defteri + saf executor'lar. Bir araç = şema + executor + `mutating`
  bayrağı; yeni araç eklemek kayıt defterine bir satır eklemektir, motor kodu değişmez.
  Executor'lar konsola yazmaz, onay sormaz, modül-global durum tutmaz.
- **`observability`** — veriyoluna takılan dinleyiciler: maliyet toplayıcı, Langfuse
  izleyici ve JSON çıktısı. Üçü de motor koduna dokunmadan eklendi — mimarinin sınavı
  buydu. Görünürlük ile muhasebe ayrıdır: arka plan çağrıları (hakem, sentez, öz-denetim,
  ders çıkarımı) ekranda **gösterilmez** ama token sayımına **girer**.
- **`ui`** — Rich importunun bulunduğu tek yer. Kullanıcıya görünen tüm Türkçe metin
  `ui/messages.py`'de toplanır.

Kurallar: [CLAUDE.md](CLAUDE.md) ve [RULES.md](RULES.md).

## Geliştirme

```bash
make check     # ruff format + ruff check + mypy (strict) + pytest
make format    # biçimlendir
```

Testler ağ erişimi yapmaz; sağlayıcı çağrıları sahte nesnelerle karşılanır
(`tests/fakes.py`). CI yerelde çalıştırılan kapının birebir aynısını çalıştırır.

## Gözlemlenebilirlik

```bash
.venv/bin/fusion run "..." --json | jq          # her olay tek satır JSON
```

`/cost` oturumda harcanan token'ı rol bazında gösterir. **Her** model çağrısı sayılır —
aday, hakem, sentez, öz-denetim, ders çıkarımı, alt-ajan.

Langfuse izleme opsiyoneldir:

```bash
pip install "fusion-cli[tracing]"
# .env: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
```

Anahtar yoksa, örnek değerse ya da paket kurulu değilse izleme **sessizce kapalı** kalır
ve uygulama tam olarak çalışmaya devam eder.

## Lisans

MIT
