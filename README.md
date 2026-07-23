# Fusion-CLI

Ücretsiz LLM'lerle çalışan, terminalde yaşayan bir kodlama asistanı.

> **Durum: taşıma tamamlandı.** Bu depo, önceki sürümün katmanlı ve test edilebilir bir
> yapıya yeniden yazılmasıdır. Açık kalan başlıklar ve alınacak kararlar için
> [docs/BACKLOG.md](docs/BACKLOG.md).

## Kurulum

Python 3.11+ gerekir.

```bash
git clone <depo-adresi> && cd fusion-cli
./setup.sh
```

Bu kadar. Betik uygun Python sürümünü bulur, `.venv` oluşturur, paketi kurar,
`.env` dosyanı hazırlar ve kurulumu doğrular. Tekrar çalıştırmak güvenlidir:
var olan `.venv` ve `.env`'e dokunmaz, eksik olanı tamamlar.

Geliştirme araçlarını da (ruff, mypy, pytest) istiyorsan `./setup.sh --dev`.

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

Ekran temizlenir, karşılama tam genişlikte açılır ve giriş alanı ekranın altına iner:

```
╭─ Fusion CLI 0.2.0 ──────────────────────────────────────────────────────────────╮
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
 ⏵ auto · agent · general · nemotron-super · shift-tab mod · /help
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
| Agent | `/reset` `/compact` |
| Fusion | `/type <tip>` `/all` `/synth` |
| Bellek | `/good` `/bad` `/revise` `/learn <kural>` `/seed` `/reindex` `/stats` `/lessons` |
| Bilgi | `/models` `/model` `/cost` `/help` `/clear` `/exit` |
| Makro | `/goal` `/grill-me` `/bug` `/commit` `/review` `/browser` `/schedule` |

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

**Model değişimi** oturum içinde yapılabilir (kalıcı olması için `config.yaml`'a yaz):

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
