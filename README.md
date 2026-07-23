# Fusion-CLI

Ücretsiz LLM'lerle çalışan, terminalde yaşayan bir kodlama asistanı.

> **Durum: yeniden yazım sürüyor.** Bu depo, önceki sürümün katmanlı ve test edilebilir
> bir yapıya taşınmasıdır. Şu an çalışan: yapılandırma, sağlayıcı katmanı, **fusion
> motoru** (paralel adaylar + hakem + sentez) ve **araç katmanı** (15 araç, tehlike
> tespiti, diff önizlemesi). Agent motoru, bellek ve REPL henüz taşınmadı — kalanlar
> için [docs/BACKLOG.md](docs/BACKLOG.md).

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

```bash
.venv/bin/fusion run "Python'da bir dosyayı satır satır nasıl okurum?"
.venv/bin/fusion run "bir REST API tasarla" --type code    # görev tipine göre model önceliği
.venv/bin/fusion run "2+2?" --all                          # tüm aday cevaplarını göster
.venv/bin/fusion run "kısa cevapla" --no-synthesis         # hakemin seçtiği cevabı göster
.venv/bin/fusion run "kısa cevapla" --quiet                # ilerleme satırlarını gizle
.venv/bin/fusion config show                               # etkin yapılandırma
.venv/bin/fusion version
```

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
