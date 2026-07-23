# Fusion-CLI

Ücretsiz LLM'lerle çalışan, terminalde yaşayan bir kodlama asistanı.

> **Durum: yeniden yazım sürüyor.** Bu depo, önceki sürümün katmanlı ve test edilebilir
> bir yapıya faz faz taşınmasıdır. Şu an **Faz 1** tamamlanmıştır: yapılandırma, sağlayıcı
> katmanı ve tek modelle çalışan `run` komutu. Fusion motoru, araçlar, bellek ve REPL
> sonraki fazlarda gelir — yol haritası için [docs/BACKLOG.md](docs/BACKLOG.md).

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
.venv/bin/fusion run "kısa bir cevap ver" --quiet   # ilerleme satırlarını gizle
.venv/bin/fusion config show                        # etkin yapılandırma
.venv/bin/fusion version
```

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
