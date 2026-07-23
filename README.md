# Fusion-CLI

Ücretsiz LLM'lerle çalışan, terminalde yaşayan bir kodlama asistanı.

> **Durum: yeniden yazım sürüyor.** Bu depo, önceki sürümün katmanlı ve test edilebilir
> bir yapıya taşınmasıdır. Şu an çalışan: yapılandırma, sağlayıcı katmanı, **fusion
> motoru** (paralel adaylar + hakem + sentez), **araç katmanı** (18 araç) ve **agent
> motoru** (tool-calling, onay modları, öz-denetim, alt-ajan), **bellek**
> (öz-öğrenme, ders belleği, anlamsal kod indeksi) ve **REPL**. Kalan işler için
> [docs/BACKLOG.md](docs/BACKLOG.md).

## Kurulum

Python 3.11+ gerekir.

```bash
make venv        # .venv oluşturur (python3.12)
make install     # paketi ve geliştirme bağımlılıklarını kurar
cp .env.example .env
```

`.env` içine en az bir sağlayıcı anahtarı gir:

- **NVIDIA NIM** (ücretsiz): <https://build.nvidia.com/>
- **OpenRouter** (ücretsiz katman): <https://openrouter.ai/keys>

İkisi de tanımlıysa yedek zinciri farklı sağlayıcılara yayılır ve tur tek bir
sağlayıcının hız sınırına takılmaz.

## Kullanım

Argümansız çalıştırınca interaktif oturum açılır:

```bash
.venv/bin/fusion
```

```
███████╗██╗   ██╗███████╗██╗ ██████╗ ███╗   ██╗
██╔════╝██║   ██║██╔════╝██║██╔═══██╗████╗  ██║
█████╗  ██║   ██║███████╗██║██║   ██║██╔██╗ ██║
██╔══╝  ██║   ██║╚════██║██║██║   ██║██║╚██╗██║
██║     ╚██████╔╝███████║██║╚██████╔╝██║ ╚████║
╚═╝      ╚═════╝ ╚══════╝╚═╝ ╚═════╝ ╚═╝  ╚═══╝
ücretsiz LLM füzyonu · araçlar · öz-öğrenen bellek

motor: agent │ onay: auto │ görev: general │ model: nemotron-super
fusion ❯
```

**shift-tab** onay modunu döndürür · **Ctrl-C** çalışan turu durdurur (oturumdan
çıkmaz) · **Ctrl-D** çıkar. Komut listesi için `/help`.

| Grup | Komutlar |
|------|----------|
| Motor | `/agent` `/fusion` |
| Onay | `/auto` `/plan` `/security` |
| Agent | `/reset` `/compact` |
| Fusion | `/type <tip>` `/all` `/synth` |
| Bellek | `/good` `/bad` `/revise` `/learn <kural>` `/seed` `/reindex` `/stats` `/lessons` |
| Bilgi | `/models` `/help` `/clear` `/exit` |

Ders çıkarımı **arka planda** çalışır: bir sonraki komutu beklemez, oturum
kapanırken tamamlanması beklenir.

### Tek seferlik kullanım

```bash
.venv/bin/fusion run "Python'da bir dosyayı satır satır nasıl okurum?"
.venv/bin/fusion run "bir REST API tasarla" --type code    # görev tipine göre model önceliği
.venv/bin/fusion run "2+2?" --all                          # tüm aday cevaplarını göster
.venv/bin/fusion run "kısa cevapla" --no-synthesis         # hakemin seçtiği cevabı göster
.venv/bin/fusion run "kısa cevapla" --quiet                # ilerleme satırlarını gizle
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
- **`providers`** — LLM adaptörleri. `HedgedProvider` birden çok modeli yarıştırır
  (ilk başarılı kazanır), `EventingProvider` çağrı yaşam döngüsünü olaya çevirir.
  Yeni bir sağlayıcı eklemek dayanıklılık davranışını bedava getirir.
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

## Lisans

MIT
