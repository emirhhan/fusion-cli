# Geçmiş İçe Aktarma Tasarımı

**Tarih:** 2026-08-28

> Not: Önceki spec'ler İngilizce yazılmıştı. Bu spec Türkçe yazıldı; RULES.md "Dil"
> maddesi insan tarafından okunan metinlerde Türkçeyi esas alıyor ve bu belgenin
> birincil okuyucusu proje sahibi.

## Amaç

Fusion, kullanıcının başka araçlarda biriktirdiği geçmişi okuyabilsin: Claude Code,
Codex/ChatGPT uygulaması ve Hermes. Üç davranış hedefleniyor:

1. **Devralma** — bir oturumu seçip işi oradan sürdürmek.
2. **Açılışta liste** — çalışılan klasöre ait son oturumları göstermek.
3. **Bellek dosyaları** — diğer araçların bellek/talimat dosyalarını sistem promptuna almak.

Bu yetenek CLI'a özel değildir. Mantık arayüzden bağımsız katmanda yaşar; slash
komutları ve açılış listesi yalnızca birer sunum yüzeyidir. Planlanan masaüstü
uygulaması aynı katmanı yeniden kullanır, davranış iki kez yazılmaz.

## Kapsam dışı

- **Arama ve indeksleme.** "Bunu daha önce nasıl çözmüştük" sorgusu bu spec'te yok.
  219 MB'lık külliyatta arama ayrı bir indeks tasarımı ister.
- **Cursor geçmişi.** `state.vscdb` şeması belgelenmemiş ve sürümle değişiyor;
  bakım yükü bugünkü değerinden büyük.
- **Sır maskeleme.** Aşağıda "Sırlar" bölümünde gerekçesiyle açıklandı.
- **Ayrı bir ilk-kurulum göç adımı.** Açılış listesi geçmişi zaten görünür kılıyor;
  tek seferlik bir göç aynı işi ikinci kez yapmak olurdu.
- **Model çağrısıyla oturum özeti.** Deterministik künye yeterli görülüyor; yetersiz
  kalırsa ayrı bir değişiklikle eklenir.

## Veri Kaynakları

Ölçülen gerçek durum (2026-08-28, geliştirme makinesi):

| Kaynak | Konum | Biçim | Hacim |
|---|---|---|---|
| Claude Code | `~/.claude/projects/<slug>/<oturum>.jsonl` | Satır başına bir JSON kaydı | 8 proje, 106 oturum, 264 MB |
| Codex / ChatGPT | `~/.codex/thread_history_1.sqlite` | `thread_items`, `item_json` alanı tip başına farklı şema | ~4,6 MB |
| Hermes | `~/.hermes/state.db` | `sessions` + `messages` tabloları, FTS indeksi mevcut | 9,4 MB |

Oturum boyutu dağılımı (Claude, 47 oturum): medyan 1,31 MB, en büyük 42,3 MB.
Medyan bir oturum bile bağlama sığmaz. Tasarım bu gerçeğin üzerine kuruludur.

## Mimari

### Kaynak adapter'ı

Her araç için bir adapter, ortak protokol:

```
list(root)               -> tuple[SessionRef, ...]
read(session_id, cursor, limit) -> tuple[Turn, ...]
```

`SessionRef` alanları: kimlik, başlık, son değişiklik zamanı, tur sayısı, kaynak
etiketi. `read` imleçlidir; çağıran ne kadar isterse o kadar çeker.

Adapter'lar ev dizinini parametre olarak alır (`CapabilityLibrary(home, root)`
deseninin aynısı). Testler gerçek `~` dizinine bağımlı olmaz, fixture ile çalışır.

Yeni bir araç desteği eklemek tek dosya eklemektir; kayıt defteri, komutlar ve
açılış listesi değişmez.

### Kurulu araç tespiti

Bir kaynak yalnızca izi varsa etkinleşir:

- Claude → `~/.claude/projects/` dizini
- Codex → `~/.codex/thread_history_1.sqlite`
- Hermes → `~/.hermes/state.db`

Tespit yalnızca varlık kontrolüdür; dosya açılmaz, sorgu çalıştırılmaz.

### Dinamik komutlar

`/resumeclaude`, `/resumecodex`, `/resumehermes` — yalnızca kurulu kaynaklar için
kaydedilir. Hermes kurulu değilse komut hiç var olmaz: tamamlama listesinde
çıkmaz, `/help` içinde görünmez.

Bugün `_COMMANDS` sabit bir demet ve `build_registry()` yalnızca onu okuyor. Bu
yüzden kayıt defteri çalışma anında komut kabul edecek biçimde genişletilir.
Tamamlama sözcükleri ve yardım grupları mevcut mekanizmayla kendiliğinden
güncellenir; ek bir yere dokunulmaz.

Komutlar "Geçmiş" grubunda toplanır.

## Başlık Çözümü

Ölçüm: 47 Claude oturumunun yalnızca 13'ünde `{"type":"ai-title","aiTitle":…}`
kaydı var; fusion-cli klasöründeki oturumların hiçbirinde yok. Liste tek başına
başlığa dayanamaz.

Sıra:

1. Kaynağın kendi başlığı (Claude `aiTitle`, Codex `thread.title`, Hermes `sessions`).
2. İlk kullanıcı mesajının ilk satırı, kırpılmış.
3. Tarih + boyut.

## Devralma Akışı

`/resumeclaude` çalıştırılınca kurulu kaynağın oturumları listelenir; kullanıcı
birini seçer. Ardından iki şey olur:

**1. Künye üretilir.** Deterministiktir, model çağrısı içermez, bu yüzden bedavadır:
kaynak, tarih, tur sayısı, kullanıcı mesajlarının tek satırlık listesi ve dokunulan
dosyalar. Künye bağlama girer ve ajanın nereye bakacağını söyler.

**2. `read_session(session_id, cursor, limit)` aracı sunulur.** Ajan gereken yeri
kendisi çeker. Oturumun tamamı hiçbir zaman bağlama yüklenmez.

Bu ikili, gözlemlenen çalışan yöntemin doğrudan karşılığıdır: önce ucuz bir
triyaj listesi, sonra yalnızca gereken turların tam okunması.

## Sırlar

Taranan 47 Claude oturumunda 17 API-anahtarı biçimli dizgi, 2 `Bearer` token,
`*_KEY=`/`*_TOKEN=`/`*_SECRET=`/`*_PASSWORD=` biçiminde 83 atama ve 1 özel anahtar
bloğu bulundu; 9 oturum etkilenmiş durumda.

**Karar: maskeleme yapılmaz.** İçerik modele olduğu gibi gider. Bu, proje sahibinin
açık kararıdır ve gerekçesi kullanılabilirliktir: maskeleme, devralınan bağlamı
sessizce bozabilir.

**Bildirim yapılır.** Künye üretilirken anahtar deseni sayılır ve kullanıcıya
"bu oturumda N token var, değiştirmeni öneririm" denir. Bildirim modele giden
içeriği etkilemez; yalnızca kullanıcıyı bilgilendirir.

Bilinen kalan risk: ücretsiz web sağlayıcıları (ör. `gemini_web`) kullanılırken
eski oturumlardaki sırlar dış servise gider. Bu risk kabul edilmiştir.

Not: `CLAUDE.md`'deki "`.env` okunmaz" maddesi bu kararla çelişmez. O madde
fusion-cli'ı **geliştiren** ajanı bağlar (sırlar repoya ve git geçmişine girmesin);
Fusion'ın son kullanıcıya karşı davranışını kısıtlamaz.

## Bellek Dosyaları

`project_instructions.py` bugün hedef projenin kökündeki `CLAUDE.md`, `AGENTS.md`,
`GEMINI.md` veya `.cursorrules` dosyasını sistem promptuna garantili ekliyor. Aynı
katman diğer araçların bellek dosyalarını da kapsayacak biçimde genişletilir:

- `~/.claude/projects/<slug>/memory/MEMORY.md`
- `~/.hermes/memories/MEMORY.md` ve `~/.hermes/memories/USER.md`

Slug eşlemesi Claude'un kuralını izler: çalışma dizini yolundaki `/` karakterleri
`-` ile değiştirilir.

Mevcut modülün "sığ tarama" ilkesi korunur: dosya varsa okunur, yoksa sessizce
atlanır; derin arama yapılmaz.

## Açılışta Liste

Banner'ın altında, çalışılan klasöre ait **en son 5 oturum** kaynak etiketiyle
karışık ve zamana göre sıralı gösterilir. Amaç geçmişi hatırlatmaktır, tam bir
tarayıcı sunmak değil; tam liste `/resume<kaynak>` ile açılır. Klasöre ait hiç
oturum yoksa hiçbir şey basılmaz — boş bir başlık gürültüdür.

## Hata Durumları

- Kaynak dosyası bozuksa o kaynak sessizce devre dışı kalır; diğerleri çalışır.
- Bir oturum kaydı ayrıştırılamıyorsa o kayıt atlanır, oturum yine listelenir.
- `read_session` geçersiz kimlikle çağrılırsa araç hata döndürür, tur düşmez.
- Kaynak dizini var ama okunamıyorsa (izin hatası) kullanıcıya sebep bildirilir.

Hiçbir durumda tek bir bozuk dosya tüm keşfi düşürmez. Bu, `capabilities.py`'deki
frontmatter ayrıştırma kararının aynı gerekçesidir.

## Test

- Her adapter için fixture tabanlı okuma testleri; gerçek ev dizinine bağımlılık yok.
- Kurulu araç tespiti: iz varken komut kayıtlı, yokken hiç yok.
- Başlık çözümü: üç basamağın her biri ayrı test.
- Künye üretimi: sabit girdi, sabit çıktı (deterministik olduğu doğrulanır).
- Sır sayımı: bilinen desenleri içeren fixture'da doğru sayı raporlanır ve
  içeriğin değişmediği doğrulanır.
- Bozuk dosya: keşfin düşmediği doğrulanır.

## Açık Sorular

Yok. Uygulama planına geçilebilir.
