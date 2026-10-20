# RULES.md

## Genel Tasarım

- Yeni bir yapı eklenirken (sağlayıcı, araç, depolama, bildirim vb.) daima generic ve tekrar kullanılabilir tasarlanır; tek kullanımlık özel çözümler yazılmaz.
- Magic string ve magic number kullanılmaz; sabitler `core/constants.py` gibi merkezi modüllerden veya yapılandırmadan gelir.
- Ortak davranışlar inline tekrar edilmez; yardımcı fonksiyon, base sınıf, dekoratör veya generic soyutlama üzerinden yönetilir.
- Bu ilke over-engineering'e kaçmadan uygulanır; tek implementasyonu olan bir şey için soyutlama katmanı eklenmez.
- Aynı işi yapan ikinci bir yol açılmaz; mevcut yapı ihtiyacı karşılamıyorsa mevcut yapı genişletilir.
- Bir dosya tek bir sorumluluk taşır. 400 satırı aşan modül bölünür; 60 satırı aşan fonksiyon parçalanır.

## Katman Sınırları

- Paket düzeni ve bağımlılık yönü aşağıdaki gibidir; ok yönünün tersine import yapılmaz.

```
cli → ui → engines → { tools, providers, memory, observability } → config → core
```

| Katman | Sorumluluk | Bağımlılığı |
|--------|------------|-------------|
| `core` | Saf tipler, protokoller, hata sınıfları, sabitler | **Hiçbir şey** — stdlib dışında import etmez |
| `config` | Yapılandırma yükleme, doğrulama, tiplenmiş nesne üretme | `core` |
| `providers` | LLM sağlayıcı adaptörleri (LiteLLM vb.) | `core`, `config` |
| `memory` | Kalıcı depolama adaptörleri (vektör DB, indeks) | `core`, `config` |
| `tools` | Araç kayıt defteri ve executor'lar | `core`, `config` |
| `observability` | Log, tracing, maliyet takibi | `core`, `config` |
| `engines` | Agent döngüsü ve fusion motoru — iş mantığının tamamı | Üstteki tüm alt katmanlar |
| `ui` | Rich / prompt_toolkit sunumu | `core`, `engines` (yalnız tip için) |
| `cli` | Typer giriş noktası, komut yönlendirme | `ui`, `engines`, `config` |

- `core` hiçbir üçüncü parti kütüphaneye bağımlı olmaz; `litellm`, `chromadb`, `rich`, `typer` importları oraya girmez.
- Bir alt katman üst katmanı import etmez; ihtiyaç varsa protokol `core`'a taşınır ve bağımlılık tersine çevrilir.
- Katmanlar arası veri taşıması dataclass'larla yapılır; dict dolaştırılmaz.

## Bağımlılık ve Soyutlama

- Dış dünyaya bakan her şey (LLM sağlayıcı, vektör deposu, dosya sistemi, saat, ağ) `core` içinde bir `Protocol` arkasında tanımlanır; concrete sınıf doğrudan iş mantığına gömülmez.
- Bağımlılıklar constructor üzerinden geçirilir; modül seviyesinde global singleton, gizli global state ve `global` anahtar sözcüğü kullanılmaz.
- Fonksiyon içinde ortam değişkeni okunmaz; tüm ortam erişimi `config` katmanındadır.
- Zaman `datetime.now()` ile alınmaz; `Clock` protokolü (veya `time.monotonic` tabanlı bir soyutlama) üzerinden alınır — testlerde sahte zaman verilebilmelidir.
- Rastgelelik ve UUID üretimi de aynı şekilde enjekte edilebilir olur.

## Dil

- Docstring, yorum, log mesajı, hata mesajı, prompt metni ve kullanıcıya görünen tüm CLI çıktıları **Türkçe** yazılır.
- Tanımlayıcılar (paket, modül, sınıf, fonksiyon, değişken, sabit adları) **İngilizce** ve PEP 8'e uygun yazılır.
- Kullanıcıya görünen metinler kod içine dağıtılmaz; ilgili modülün metin sabitlerinde veya `ui` katmanında toplanır.
- Uzun prompt metinleri koda gömülmez; ayrı `.txt` / `.md` dosyasında tutulur ve paket verisi olarak yüklenir.

## Casing

- Modül ve paket adı: `snake_case`, kısa ve tekil (`router`, `memory`, `code_index`).
- Sınıf ve `Protocol`: `PascalCase`.
- Fonksiyon, metot, değişken, parametre: `snake_case`.
- Sabit: `UPPER_SNAKE_CASE`.
- Modül-içi (private) yardımcı: tek alt çizgi öneki (`_parse_judge`).
- Tip değişkeni: tek büyük harf veya `PascalCase` + `T` (`T`, `ResultT`).
- Kısaltmalar sınıf adında PascalCase yazılır (`HttpClient`, `LlmProvider`), fonksiyon adında küçük (`http_client`).

## İsimlendirme

- `x`, `y`, `d`, `tmp`, `data`, `obj`, `res` gibi anlamsız isimler kullanılmaz; ne tuttuğu adından anlaşılır.
- Koleksiyon değişkenleri çoğul adlandırılır (`candidates`, `lessons`, `tool_calls`).
- Boolean değişken ve fonksiyonlar `is_`, `has_`, `can_`, `should_` önekiyle başlar (`is_dangerous`, `has_pending_todos`).
- Sonuç nesneleri yapılan işi yansıtır: `FusionResult`, `AgentResult`, `ModelResult`.
- Protokol adları yetenek anlatır: `LlmProvider`, `LessonStore`, `Tracer`; `IFoo` öneki kullanılmaz.
- Dosya adı içindeki modül adı, içindeki ana sınıfın adıyla uyumlu olur.

## Tip İpuçları

- Her public fonksiyon ve metot tam tiplenir; parametre ve dönüş tipi yazılmadan bırakılmaz.
- Her modül `from __future__ import annotations` ile başlar.
- `Any` kullanılmaz; kaçınılmazsa satırın üstüne gerekçesi yorumla yazılır.
- Dönüş tipi `dict`/`tuple` yerine `dataclass` veya `NamedTuple` olur; anlamı olan veri isimlendirilir.
- Değer nesneleri `@dataclass(frozen=True)` olur; mutasyon yerine `dataclasses.replace` kullanılır.
- Opsiyonel değer `X | None` ile yazılır; sessiz varsayılan uydurulmaz.

## Dil Kuralları

- Modül seviyesinde iş yapılmaz; import anında yalnızca tanım yapılır, ağ/dosya/DB erişimi olmaz.
- Yıldız import (`from x import *`) yasaktır.
- Fonksiyon varsayılan argümanı mutable olmaz (`list`, `dict`, `set` varsayılan verilmez).
- Karşılaştırmalarda `is` yalnızca `None`/singleton için kullanılır.
- `print` kullanılmaz; kullanıcıya çıktı `ui` katmanından, teşhis çıktısı logger'dan verilir.
- Ağır import'lar (chromadb, litellm) gerçekten gerektiği yerde tembel (fonksiyon içi) yapılır ve gerekçesi yorumla belirtilir.

## Async

- I/O yapan tüm fonksiyonlar `async` olur; senkron ve asenkron iki ayrı yol açılmaz.
- Asenkron fonksiyon adına `_async` eki eklenmez; `await` edilebilirlik imzadan anlaşılır.
- Event loop içinde bloklayan çağrı yapılmaz; kaçınılmazsa `asyncio.to_thread` ile ayrılır.
- Oluşturulan her task'ın sahibi vardır: iptal edilir ya da beklenir; `create_task` sonucu göz ardı edilmez.
- `asyncio.CancelledError` yutulmaz; temizlik yapılır ve yeniden fırlatılır.
- Ağa çıkan her çağrı timeout ile yapılır; timeout değeri koda gömülmez, yapılandırmadan gelir.
- Arka plan işleri (ders çıkarımı, ısıtma) fire-and-forget çalışsa bile hataları yutulmaz, log'lanır.

## Hata Yönetimi

- Tüm proje hataları `core/errors.py` içindeki tek bir kök hatadan (`FusionError`) türer.
- `except Exception` ile geniş yakalama yapılmaz; yakalanan hata tipi açıkça yazılır. Sınır katmanlarında (CLI giriş noktası, arka plan thread'i) genel yakalama yapılabilir, ancak hata **mutlaka log'lanır**, sessizce yutulmaz.
- `except: pass` yasaktır.
- Beklenen başarısızlıklar (sağlayıcı 429 verdi, model yanıt vermedi) exception ile değil sonuç nesnesiyle (`ok=False` + `error`) taşınır; akış kontrolü için exception fırlatılmaz.
- Beklenmeyen hatalar CLI sınırında yakalanır, kullanıcıya Türkçe ve anlaşılır mesaj gösterilir; stack trace kullanıcıya basılmaz, log'a yazılır.
- Hata mesajları eyleme dönüştürülebilir olur: ne oldu, neden, kullanıcı ne yapabilir.

## Yapılandırma

- Yapılandırma tek bir yerden yüklenir ve tiplenmiş `frozen` dataclass olarak dolaştırılır; ham `dict` katmanlara sızmaz.
- Yapılandırma dosyası **tek kaynaktan** yönetilir; aynı içeriğin ikinci bir kopyası tutulmaz (pakete gömülü varsayılan, elle senkronlanan ikinci dosya değil, tek dosyadan üretilir).
- Kod içindeki varsayılan değerler ile yapılandırma dosyasındaki değerler **birbiriyle tutarlı** olur; ikisi ayrışırsa test kırılır.
- Bilinmeyen/geçersiz yapılandırma anahtarı sessizce yok sayılmaz; yükleme sırasında doğrulanır ve anlaşılır hata verilir.
- Model kimlikleri, timeout'lar, eşikler ve limitler koda gömülmez; yapılandırmadan okunur.

## Loglama ve Gözlemlenebilirlik

- Log çıktısı yapılandırılmış (structured) olur; string birleştirme yerine alanlar kullanılır.
- Log'a API anahtarı, token, prompt içeriğinin tamamı veya kişisel veri yazılmaz.
- Kullanıcıya gösterilen çıktı ile teşhis log'u karıştırılmaz: biri `ui`, diğeri `observability` sorumluluğudur.
- Tracing ve maliyet takibi opsiyoneldir; kapalıyken veya erişilemezken uygulama **tam çalışır**, no-op'a düşer.
- Maliyet/token takibi tek bir yerden beslenir; her çağrı yolu (streaming, tek seferlik, hakem, arka plan) aynı kayıt fonksiyonundan geçer — bir yol atlanmaz.

## Sağlayıcı ve Dış Servisler

- LLM çağrıları yalnızca `providers` katmanı üzerinden yapılır; `engines` içinden doğrudan sağlayıcı SDK'sı çağrılmaz.
- Her dış çağrı timeout, retry ve fallback ile yapılır; bir sağlayıcı hata verdiğinde uygulama çökmez.
- Sağlayıcı yanıtları normalize edilerek proje tipine (`ModelResult`) çevrilir; SDK nesneleri üst katmanlara sızmaz.
- Anahtarsız/ücretsiz çalışma yolu daima korunur: anahtar yoksa ilgili özellik devre dışı kalır, uygulama açılmaya devam eder.
- Ağ erişimi gerektiren hiçbir kod import anında çalışmaz.

## Araçlar (Agent Tool'ları)

- Her araç üç parçadan oluşur: JSON şeması, saf executor fonksiyonu ve `mutating` bayrağı. Üçü tek yerde, kayıt defterinde birleşir.
- Executor saf tutulur: yan etkisi dosya sistemi/shell dışına taşmaz, doğrudan konsola yazmaz, kullanıcıya sormaz.
- Onay, önizleme ve gösterim araç kodunun dışındadır; araç kendi onayını sormaz.
- Değiştirici her araç için değişiklik önizlemesi (diff / komut satırı) üretilebilir olur.
- Araç sonuçları metin döner ve hata durumunda tutarlı bir önekle başlar; hata tespiti string aramasıyla dağınık şekilde yapılmaz, tek bir yardımcı fonksiyondan geçer.
- Araç çıktıları sınırlandırılır (bayt/satır/eşleşme tavanı); sınırlar sabit olarak merkezi tanımlanır.
- Yeni araç eklemek kayıt defterine bir giriş eklemekle sınırlı olur; motor kodu değiştirmek gerekmez.
- Paylaşılan araç durumu (todo listesi vb.) modül-global tutulmaz; çağrı bağlamına (session/context) bağlanır.

## Bellek ve Depolama

- Depolama erişimi `memory` katmanındaki adaptörlerin arkasındadır; `engines` doğrudan veritabanı istemcisi kullanmaz.
- Yazma işlemleri eşzamanlılığa karşı korunur; birden çok thread'den yazılabilen her depo kilit altında çalışır.
- Kalıcı veri yolları yapılandırmadan gelir; koda gömülü mutlak yol yazılmaz.
- Şema/boyut değişikliğine yol açan seçimler (embedding sağlayıcısı gibi) koleksiyon adında ayrıştırılır; farklı boyutlu veriler aynı koleksiyona karışmaz.
- Depo erişilemezse özellik devre dışı kalır ve kullanıcıya bildirilir; uygulama çökmez.

## UI ve CLI

- İş mantığı `cli` ve `ui` katmanlarında bulunmaz; komutlar yalnızca girdi çözer, motoru çağırır ve sonucu sunar.
- Bir komut fonksiyonu 40 satırı aşmaz; aşıyorsa mantık aşağı katmana taşınır.
- Komutlar tek bir kayıt defterinden yönlendirilir; uzun `elif` zinciri yazılmaz.
- Rich ve prompt_toolkit importları yalnızca `ui` katmanında bulunur; motor kodu terminal kütüphanesi tanımaz.
- Renk, ikon ve stil değerleri tema modülünde tek yerde tanımlanır; kod içine hex/markup gömülmez.
- Kullanıcı girdisi (onay, soru) tek bir soyutlama üzerinden alınır; senkron ve asenkron iki ayrı onay yolu yaşatılmaz.
- TTY olmayan ortamda (pipe, CI, test) tüm komutlar çalışmaya devam eder.

## Güvenlik

- Yıkıcı/geri alınamaz işlemler için onay zorunludur; otomatik onay modu bile bu kontrolü baypas etmez.
- Tehlikeli komut desenleri tek bir merkezi listede tanımlanır ve testle doğrulanır; koda dağıtılmaz.
- Kullanıcı girdisi ve model çıktısı güvenilir kabul edilmez; dosya yolu, komut ve URL kullanılmadan önce doğrulanır.
- Shell komutları çalıştırılırken kullanıcıya ne çalışacağı birebir gösterilir.
- Sır yönetimi: anahtar, token ve connection string asla koda, teste, log'a veya git'e girmez; yalnızca ortam değişkeninden okunur.

## Test

- Testler ağ erişimi yapmaz; sağlayıcı çağrıları sahte (fake/monkeypatch) ile karşılanır.
- Testler diske yalnızca `tmp_path` altında yazar; kullanıcı dizinine veya proje köküne dokunmaz.
- Saf mantık (parçalama, karar matrisi, ayrıştırma, tehlike tespiti, isimlendirme) doğrudan test edilir; ağır bağımlılık yüklenmeden çalışır.
- Test adı davranışı anlatır: `test_<konu>_<beklenen davranış>`.
- Her hata düzeltmesi, hatayı gösteren bir testle birlikte gelir.
- Testler birbirinden bağımsız ve sırasızdır; global state paylaşmaz.
- Sınıf/dosya başına değil, davranış başına test yazılır; kapsam için değil güven için test yazılır.

## Kalite Kapısı

- Commit öncesi şu üçü temiz olmak zorundadır: `ruff check` (lint + format), `mypy` (tip denetimi), `pytest` (testler).
- Lint/format/tip yapılandırması `pyproject.toml` içinde tek yerde tutulur; editör ayarına bırakılmaz.
- Uyarı bastırma (`# noqa`, `# type: ignore`) gerekçesiz kullanılmaz; kullanılıyorsa yanına nedeni yazılır.
- CI, kalite kapısının aynısını çalıştırır; lokalde geçip CI'da kalan bir kural bırakılmaz.
- Bağımlılıklar `pyproject.toml` içinde alt **ve** üst sınırlı belirtilir; sürüm sabitleme lock dosyasıyla yapılır.

## Ölü Kod

- Kullanılmayan fonksiyon, import, parametre ve "legacy" bırakılmış gövde repoda tutulmaz; silinir (geçmiş git'tedir).
- "Şimdilik kullanılmıyor" diye kod bırakılmaz; ihtiyaç doğduğunda yazılır.
- Yorum satırına alınmış kod bloğu commit edilmez.
- `TODO`/`FIXME` yorumları repoda bırakılmaz; iş `docs/BACKLOG.md` dosyasına yazılır.
