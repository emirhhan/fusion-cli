"""Araç katmanının sayısal sınırları — tek yerde tanımlıdır.

Bu değerler koda dağıtılmaz: bir sınırı değiştirmek tek satır değiştirmektir ve
"acaba başka nerede geçiyordu?" sorusu hiç doğmaz.

Sınırların amacı bağlamı korumaktır: model bir aracın çıktısını okuyacaktır, binlerce
satırlık bir dökümü bağlama boca etmek hem pahalı hem de sinyali gürültüde boğar.
"""

from __future__ import annotations

#: "Dosya yok" hatasının değişmez öneki.
#
# Motor katmanı bu işarete bakarak "yanlış çalışma dizini" hipotezini kurar;
# metin iki yerde ayrı ayrı yazılırsa sessizce ayrışır.
FILE_MISSING_PREFIX = "Dosya yok:"

#: Bir dosyadan okunacak en fazla bayt.
MAX_READ_BYTES = 100_000
#: `download_file` ile indirilebilecek en fazla bayt.
#
# 32 MiB iken gerçek asset paketleri sınıra takılıyordu. Ölçüldü (13 Eylül, Godot
# koşusu): model aradı, GitHub üzerinde gerçek bir 2D asset paketi buldu ve
# indirme "32 MiB sınırını aşıyor" ile düştü; oyun yine assetsiz kaldı. Yayınlanan
# ücretsiz paketler (Kenney, OpenGameArt derlemeleri) onlarca ila birkaç yüz MB
# arasındadır.
#
# 256 MiB, arşiv açma sınırıyla (512 MiB, bkz. `tools.archive`) uyumludur: en
# büyük kabul edilen arşiv açıldığında da sınır içinde kalır. Sınır KALDIRILMAZ;
# indirme kullanıcının diskine ve süresine yazılır.
MAX_DOWNLOAD_BYTES = 256 * 1024 * 1024
#: Tek bir read_file çağrısında döndürülecek en fazla satır.
#
# Sınır bayt değil SATIR cinsindendir çünkü modelin devam edeceği birim satırdır.
# 800 satır, bir modülü anlamaya yeter ve web taşımasında tarayıcı kutusuna
# yapıştırılabilir bir boyutta kalır: 1388 satırlık bir dosyanın tamamı (52 KB)
# tek seferde gönderildiğinde model onu takip edemiyor, "kaldığım yerden devam
# ediyorum" deyip aynı çağrıyı tekrarlıyordu (ölçüldü).
MAX_READ_LINES = 800
#: Bir araç çıktısının modele verilecek en fazla karakteri.
MAX_OUTPUT_CHARS = 20_000
#: Metin/regex aramasında döndürülecek en fazla eşleşme.
MAX_SEARCH_HITS = 100
#: Bir eşleşme satırından gösterilecek en fazla karakter.
MAX_MATCH_LINE_CHARS = 160
#: Desenle bulunacak en fazla dosya.
MAX_GLOB_MATCHES = 200
#: Bir dizinde listelenecek en fazla giriş.
MAX_DIR_ENTRIES = 200
#: Aranırken atlanacak en büyük dosya boyutu (bayt).
MAX_SEARCHABLE_FILE_BYTES = 1_000_000
#: Yeni dosya önizlemesinde gösterilecek en fazla satır.
MAX_PREVIEW_LINES = 40
#: Checkpoint'e yazılacak tek araç/komut çıktısının en fazla karakteri.
#
# Devam kaydı bir arşiv değildir: kanıt olarak komutun gerçekten çalıştığı ve ne
# döndürdüğü yeterlidir. Sınır, doğrulayıcının bellekte tuttuğu kanıt kesitiyle
# (8.000 karakter) aynıdır; büyütmek diskteki kaydı `read_file` çıktısı kadar
# şişirir, küçültmek aynı kanıtın bellekte geçip diskte kaybolmasına yol açar.
MAX_CHECKPOINT_OUTPUT_CHARS = 8_000

#: Kabuk komutu için zaman aşımı (saniye).
SHELL_TIMEOUT_S = 120.0
#: `cp`/`mv`/`>` ile ezilecek dosyanın geri alma için bellekte tutulacağı en büyük boyut.
SHELL_BACKUP_MAX_BYTES = 20 * 1024 * 1024
#: Arka plan işinin durumunu sorarken tek çağrıda beklenebilecek en uzun süre (saniye).
#: Remotion render'ı ve npm install dakikalar sürer; modelin her 2 sn'de bir sormasını
#: değil tek çağrıda beklemesini isteriz. Üst sınır, NIM'in 600 sn'lik istek
#: süresiyle aynıdır: bir araç çağrısı bir model çağrısından uzun sürmez.
JOB_MAX_WAIT_S = 600.0
#: Bitmiş işin makbuzu host iş parçacığında yazılıyorsa (dondurulmuş uygulama) `job_status`
#: en fazla bu kadar bekler; makbuz `.exit`'ten milisaniyeler sonra gelir.
JOB_RECEIPT_GRACE_S = 2.0
#: Arka plan işi günlüğünden modele gösterilen son kesit (karakter); kabuk
#: çıktısı sınırının (MAX_OUTPUT_CHARS) yarısı — durum sorgusu tekrarlanabilir.
JOB_LOG_TAIL_CHARS = 10_000
#: JavaScript sözdizimi denetimi için zaman aşımı (saniye).
#:
#: Arena çıktısındaki 300 satırlık betikte `node --check` beş ölçümde 0,03-0,04
#: saniye sürdü. 5 saniye soğuk disk/yoğun makine için geniş pay bırakır; takılan
#: opsiyonel bir doğrulayıcının agent turunu dakikalarca bekletmesini engeller.
JAVASCRIPT_SYNTAX_TIMEOUT_S = 5.0
#: Salt-okunur git komutu için zaman aşımı (saniye).
GIT_TIMEOUT_S = 30.0
#: Web isteği için zaman aşımı (saniye). Bu bir HTTP İSTEĞİ bütçesidir (arama,
#: sayfa çekme, katalog); bir LLM turunun bütçesi DEĞİLDİR. Tarayıcı tabanlı bir
#: sohbet turu sayfa yükleme + yazma + tam streaming üretim içerir ve buraya sığmaz;
#: onun bütçesi `WebSessionConfig.timeout_s` alanından gelir.
WEB_TIMEOUT_S = 20.0

#: Fusion Kits yan sürecine (yerel HTTP) tek istek bütçesi: Kit listesi, gelen kutusu
#: teslimi ve durum okuma. Kit'in işi yapması beklenmez; makbuz anında döner.
KITS_TIMEOUT_S = 15.0
#: Masaüstü başlatmamışsa (durum dosyası yok) denenen elle başlatılmış Kits adresi
#: (`npm run kits:start` varsayılan portu).
KITS_DEFAULT_URL = "http://127.0.0.1:4410"
#: Kits'in dinlediği adresi duyurduğu durum dosyasının adı (`kits_process.rs` ile aynı).
KITS_STATE_FILENAME = "kits-bridge.json"

#: Hız sınırı sonrası yeniden denemede `retry_after_s` ile en fazla bu kadar beklenir.
#: Paylaşılan soğuma bundan uzunsa bekleme sınırlanır; ardından kapı yine kapalıysa
#: sonuç olduğu gibi üst katmana (agent turunun kendi bekleme/yedek mantığına) döner.
RETRY_AFTER_MAX_WAIT_S = 120.0

#: Tarayıcı oturumunda görsel yükleme yolu OLAN web sağlayıcıları (yalnız Gemini'de ölçüldü).
#: `supports_images`, yetenek profili ve `_attach_images` aynı kümeye bakar (P1-06).
WEB_IMAGE_UPLOAD_PROVIDERS = frozenset({"gemini_web"})
#: Bir aracın "istenen iş bu araçla YAPILAMAZ" dediği çıktının öneki.
#:
#: Şifre duvarı, oturum kapısı ya da bot doğrulaması gibi durumlarda araç teknik
#: olarak başarılıdır (200 döner) ama istenen içeriği getirememiştir. Motor bu öneki
#: görünce eylem-kanıtı kapısını geri çeker: kanıt yokluğunun sebebi modelin
#: tembelliği değil, aracın sınırıdır ve modeli zorlamak onu UYDURMAYA iter.
CAPABILITY_WALL_PREFIX = "ERİŞİM DUVARI:"

#: Kaynağın kendisine ULAŞILAMADIĞINI bildiren çıktının öneki.
#
# Duvardan farkı sebeptir: duvarda adres vardır ama kapı kapalıdır, burada adres
# hiç çözülmez. Motor açısından SONUÇ aynıdır — iş bu araçla yapılamaz — ve
# eylem-kanıtı kapısı aynı şekilde geri çekilir.
#
# Ölçüldü (6 Eylül canlı koşusu, `erisilemeyen-kaynagi-uydurma`): model adresi
# denedi, DNS çözülmedi, hiçbir şey uydurmadı ve durumu dürüstçe açıkladı. Kanıt
# kapısı "workspace_mutation doğrulanamadı" deyip modelin AÇIKLAMASINI silip
# yerine genel bir mesaj koydu; kullanıcı sebebi hiç öğrenemedi ve üç koşunun
# üçü de başarısız sayıldı. Var olmayan bir adresi kopyalamamak doğru davranıştır.
UNREACHABLE_RESOURCE_PREFIX = "ERİŞİLEMEZ KAYNAK:"

#: Tarayıcı turu için kabul edilebilir EN KISA bütçe (saniye). Yapılandırma bunun
#: altına inerse tur daha başlamadan zaman aşımına uğrar; taban buradadır.
MIN_BROWSER_TURN_S = 30.0

#: Oturum tabanlı (tarayıcı) sağlayıcı kimliklerinin ortak son eki.
#
# Model kimliğinin ORTA parçasının ne anlama geldiğini bu ek belirler:
# `nvidia_nim/nvidia/nemotron` içinde satıcı adıdır ve gürültüdür,
# `gemini_web/isimdijital/auto` içinde ise HESAP adıdır ve kullanıcının görmesi
# gereken bilgidir (bkz. `ui.text.format_model`).
WEB_PROVIDER_SUFFIX = "_web"
#: Panel model kataloğu önbellek ömrü (saniye). Katalog sık değişmez; her panel
#: açılışında sağlayıcının /models ucunu dövmemek için 5 dakika tutulur.
CATALOG_CACHE_TTL_S = 300.0
#: Model sağlık sondası önbellek ömrü (saniye).
#
# Sondaj (`fusion doctor --live`) gerçek bir çağrıdır ve model başına 60 saniyeye
# kadar sürebilir (bkz. `providers/catalog.py::probe_nim_tools`); her seçici
# açılışında yeniden çalıştırmak seçiciyi dakikalarca dondururdu. 6 saat, bir
# günlük kullanım için birkaç sondajla (kullanıcı `doctor --live` çalıştırdıkça)
# yetecek kadar uzun, ama ölü bir modelin gün boyu "yanıt vermiyor" etiketiyle
# kilitli kalmaması için yeterince kısa tutuldu — sağlayıcı arızası genelde
# saatler içinde düzelir ya da kalıcı hâle gelir.
MODEL_HEALTH_CACHE_TTL_S = 21_600.0
#: Web aramasından döndürülecek en fazla sonuç.
MAX_WEB_RESULTS = 8
#: `web_fetch` için elle takip edilecek en fazla yönlendirme. Her adım SSRF'e karşı
#: yeniden doğrulanır; sonsuz/uzun yönlendirme zinciri bu sınırla kesilir.
MAX_WEB_REDIRECTS = 5

#: Keşif ve arama sırasında atlanan gürültü dizinleri.
#
# `vendor`, `build`, `dist`, `target` bilinçli gürültü sayılır (bağımlılık/üretilmiş
# çıktı). Godot/Laravel gibi bu adları KAYNAK için kullanan projelerde içlerindeki
# dosyalar arama ve ad-ile-bulmada görünmez; bu bir ödünleşimdir, yanlışlık değil.
SKIP_DIRECTORIES = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".fusion",
        "dist",
        "build",
        ".next",
        ".cache",
        ".npm",
        ".Trash",
        "Application Support",
        "Cache",
        "Caches",
        "vendor",
        "target",
        ".idea",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
    }
)

#: `list_dir` çıktısında gizli olmasına rağmen gösterilen dosyalar.
VISIBLE_DOTFILES = frozenset({".env.example", ".gitignore", ".github"})


def truncate_notice(text: str, limit: int, *, ne: str = "çıktı") -> str:
    """Metni sınıra indir ve KIRPILDIĞINI söyle.

    Sessiz kırpma araçların en sinsi yalanıdır: model eksik bilgiyi tam sanır.
    Uzun bir test çıktısında gerçek hatayı hiç görmeden "geçti" sanabilir.
    """
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[… {ne} {limit} karakterde KIRPILDI; gerisi gösterilmedi.]"


#: Tekrarlanan okuma çağrısına önbellekten cevap verirken saklanan en büyük
#: çıktı (karakter).
#:
#: Model aynı dosyayı ikinci kez istediğinde çağrıyı ENGELLEMEK yerine ilk
#: sonucu geri veriyoruz; bunun için sonucu turda tutmak gerekiyor. Sınır
#: gerekçesi: `read_file` çıktısı zaten araç katmanında kırpılıyor ve tipik bir
#: kaynak dosya bu sınırın altında kalıyor; daha büyüğünü turda tutmak belleği
#: çıktının değerini aşan biçimde şişirirdi.
REPEAT_READ_CACHE_CHARS = 64_000
#: Turda önbellekte tutulacak en çok okuma sonucu.
#:
#: Bir agent turunda okunan ayrı dosya sayısı ölçümlerde onlarla ifade ediliyor;
#: 64 giriş bunun çok üstünde ve sınırsız büyümeyi engeller.
REPEAT_READ_CACHE_ENTRIES = 64


#: Parola karması için scrypt maliyet parametreleri.
#
# argon2 yerine stdlib `hashlib.scrypt` seçildi: masaüstü paketine yeni bir
# yerel bağımlılık (argon2-cffi) sokmak DMG boyutunu ve derleme riskini
# artırıyordu, scrypt ise aynı sınıfta bir bellek-zorlu fonksiyon ve Python'un
# içinde geliyor.
#
# N=2^15, r=8, p=1: RFC 7914'ün etkileşimli oturum açma için önerdiği çalışma
# noktası (~32 MB bellek). Ölçüldü (bu makine): tek doğrulama ~90 ms — insanın
# fark etmediği, deneme-yanılma saldırısını ise ciddi biçimde pahalılaştıran bir
# süre. `maxmem` varsayılanı bu N için yetmiyor, açıkça verilir.
SCRYPT_N = 1 << 15
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MAXMEM = 64 * 1024 * 1024
#: Parola karmasının ve tuzun bayt uzunluğu.
SCRYPT_KEY_BYTES = 32
SCRYPT_SALT_BYTES = 16
#: Kurtarma kodunun taşıdığı rastgele bayt sayısı.
#
# Sunucu yok, hız sınırı yok: kod yeterince uzun olmalı. 10 bayt = 80 bit; Crockford
# Base32'de (5 bit/karakter) 16 karaktere karşılık gelir ve kaba kuvvetle bulunamaz.
RECOVERY_CODE_BYTES = 10


#: Barındırmalı connector doğrulaması için tanınan süre (saniye).
#
# Doğrulama, sağlayıcının KENDİ sohbetine bir istem yazıp cevabını beklemektir;
# yani bir sayfa yükleme + yazma + tam streaming üretim turudur. Sağlayıcı
# başına ayarlanan tur süresi (Gemini'de 180 sn) bunun için dar kalıyor ve
# kullanıcı "doğrulama başarısız" görüyordu — oysa model hâlâ yazıyordu.
# 420 sn, ölçülen en yavaş sağlayıcının (ChatGPT) tur süresiyle aynı tavandır.
HOSTED_VERIFY_TIMEOUT_S = 420.0


#: Tekrar kapısının aracı ÇALIŞTIRMADAN döndürdüğü engel mesajlarının önekleri.
#: Bu çıktılar bir komutun sonucunu değil engeli anlatır; tur raporu onları
#: doğrulama kanıtı saymaz (bkz. `engines/agent/turn_report.py`).
#: `run_shell` çıktısının başındaki çıkış kodu öneki; üreten (`tools/shell.py`) ve okuyan
#: (`turn_report`) taraf TEK sabiti kullanır, biçim değişirse çıkış kodu sessizce `None`
#: olup kanıtlar çökmesin (A4-65).
EXIT_CODE_PREFIX = "(çıkış kodu "
TOOL_CALL_DUPLICATE_PREFIX = "TOOL_CALL_DUPLICATE:"
TOOL_CALL_BLOCKED_PREFIX = "TOOL_CALL_BLOCKED:"

#: Paylaşılan hız defterinin SQLite kilit bekleme süresi (sn). Defter işlemleri
#: tek satırlık okuma/yazmadır (mikrosaniyeler); 2 sn yalnız aynı anda çok sekme
#: yazarken sıra bekleyen süreci korur, takılı bir kilit turu dondurmaz.
RATE_LEDGER_BUSY_TIMEOUT_S = 2.0

#: `site_crawl` iki istek arasında en az bu kadar bekler (robots.txt `Crawl-delay`
#: daha uzunsa o geçerli). 1 sn: küçük sitelerin bile rahat kaldırdığı, yaygın kabul
#: gören nazik tarama hızı; tek kullanıcının bir siteyi incelemesi için yeterli.
CRAWL_DELAY_S = 1.0
#: Bir taramada en fazla sayfa ve derinlik (kullanıcı daha azını isteyebilir).
CRAWL_MAX_PAGES = 100
CRAWL_MAX_DEPTH = 4

#: `chrome_action upload` ile sayfaya verilecek dosyaların toplam üst sınırı. Dosya
#: base64 olarak yerel köprüden ve `chrome.scripting` argümanı olarak sayfaya geçer;
#: bu yolun büyük dosyadaki davranışı ÖLÇÜLMEDİ. 10 MB, tipik form yüklemelerini
#: (fotoğraf, PDF, ürün görseli) karşılayan temkinli değerdir; aşan dosya için
#: kullanıcıya elle yükleme önerilir.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

#: `php -l` tek dosyayı milisaniyeler içinde ayrıştırır; 10 sn soğuk başlatmayı
#: (Homebrew PHP'nin ilk açılışı) karşılayan geniş pay. Aşan dosya "doğrulanamadı" olur.
PHP_LINT_TIMEOUT_S = 10.0

#: MCP istemcisinin mevcut 10 saniyelik ağ varsayılanı; bütün kapanış yolları paylaşır.
MCP_NETWORK_TIMEOUT_S = 10.0

#: Mevcut config lock fallback polling aralığı; async lease de aynı aralığı kullanır.
FILE_LOCK_POLL_S = 0.05

#: Terminal ProcessManager'ın mevcut TERM→KILL bekleme payı.
PROCESS_TERMINATE_GRACE_S = 1.5
#: Mevcut Windows taskkill denetim süresi.
PROCESS_CONTROL_TIMEOUT_S = 10.0
#: Arka plan job durumunun mevcut yoklama aralığı; foreground iptali de bunu kullanır.
PROCESS_POLL_S = 1.0
#: Ön plan komutunun her akışı (stdout/stderr) için bellekte tutulan baş VE son kesit
#: (bayt). Aradaki atılır ve sayılır; çıktı sınırsız büyüse de bellek sınırlı kalır.
SHELL_CAPTURE_CHARS = 100_000
#: İptal sonrası sahipli iş parçacığının bitmesi için en çok beklenen süre (saniye).
#: Meşru temizlik (TERM→KILL turları dahil) bunun altında biter; aşılırsa iş parçacığı
#: "sahipsiz kaldı" olarak bildirilir ve iptal tamamlanır.
OWNED_THREAD_CANCEL_GRACE_S = PROCESS_TERMINATE_GRACE_S * 8


#: Cevap makbuzlarının yeniden teslim penceresi; 256 adet SHA-256+kimlik kaydı.
#: Yalnız ACK tutulur, izin veya yanıt metni değil. Eski kayıt atılınca tekrar
#: reddedilir; araç ikinci kez çalıştırılmaz. Bellek oturum süresiyle büyümez.
QUESTION_RECEIPT_HISTORY_LIMIT = 256

#: Cevapsız onay kartının en uzun bekleme süresi (saniye). Süre dolunca onay REDDEDİLİR ve
#: "OnayZamanAsimi" olayı yayılır; kullanıcı yokken tur ve turu tutan kilit sonsuza dek açık
#: kalmaz. Yalnız onay içindir; açık uçlu sorular süreyle reddedilmez.
APPROVAL_UNANSWERED_TIMEOUT_S = 30 * 60.0

#: Fusion'ın kendi ürettiği iz, artifact ve tamamlanmış checkpoint dosyalarının saklama süresi
#: (saniye). Süre dolunca açılışta silinir; kullanıcı dosyalarına ve denetim günlüğüne dokunulmaz.
LOCAL_STATE_RETENTION_S = 30 * 86_400.0
#: Saklama temizliğinin en sık çalışma aralığı (saniye); damga dosyasıyla sınırlanır.
LOCAL_STATE_PURGE_INTERVAL_S = 86_400.0

#: Web oturumunun "dosya değiştirebilir" araç ölçümü bu süreden eskiyse kart "yeniden ölç"
#: uyarısı taşır (saniye). İzin otomatik düşürülmez; ölçüm stokastiktir, karar kullanıcıdadır.
TOOL_MEASURE_STALE_S = 7 * 86_400.0

#: NIM gömme yoklamasının sonucunun diskte geçerli kalma süresi (saniye).
NIM_PROBE_CACHE_TTL_S = 10 * 60.0

#: Oturum kapanırken sürmekte olan model seçimi/doğrulaması görevlerini en çok bu kadar bekle
#: (saniye); NIM araç doğrulaması 90 sn'ye kadar sürebilir ve kapanışı geciktirmemeli.
MODEL_SELECTION_CLOSE_WAIT_S = 5.0
