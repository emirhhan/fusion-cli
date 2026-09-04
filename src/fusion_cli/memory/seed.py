"""Önceden öğretilmiş dersler — agent sıfırdan değil, hazır disiplinle başlar.

Ders belleği normalde her oturumdan tek tek öğrenir; bu yavaş bir yoldur. Burada
küratörlü, yüksek kaliteli bir başlangıç bilgisi tohumlanır: araç kullanım disiplini,
doğrulama alışkanlığı, güvenlik ve sık yapılan agent hataları.

Dersler KISA ve göreve-özgü tutulur: geri çağırma anlamsal benzerliğe dayanır, genel
geçer nasihatler hiçbir göreve yeterince benzemez ve boşuna yer kaplar.
"""

from __future__ import annotations

from ..core.memory import Lesson, LessonKind, LessonMemory, LessonSource

_M = LessonKind.MISTAKE
_S = LessonKind.SUCCESS

#: Ölçülerek doğrulanmış dersler. Her biri gerçek bir koşuda görülmüş bir
#: kırılmadan çıktı; tam güvenle başlarlar.
_MEASURED: tuple[tuple[str, LessonKind, str], ...] = (
    # --- Dosya düzenleme --------------------------------------------------
    (
        "dosya düzenleme",
        _S,
        "Bir dosyayı değiştirmeden önce read_file ile oku; kör düzenleme yapma. "
        "edit_file için 'old' metni birebir ve dosyada BENZERSİZ olmalı.",
    ),
    (
        "dosya düzenleme",
        _M,
        "Aynı dosyada birden çok yeri değiştirirken tek tek edit_file yerine multi_edit "
        "kullan; biri tutmazsa hiçbiri uygulanmaz, yarım kalmış dosya riski olmaz.",
    ),
    (
        "tekrar eden metni düzeltme",
        _S,
        "Aynı metin dosyada çok kez geçiyorsa edit_file'a replace_all: true ver; "
        "tek çağrıda biter. Benzersizlik hatasını tek tek çözmeye çalışma.",
    ),
    (
        "dosyayı baştan yazma riski",
        _M,
        "Var olan bir sayfayı write_file ile baştan yazarken <script> ve <link> "
        "etiketleri düşüyor; sayfa sessizce boşalır, konsolda hata bile çıkmaz. "
        "Küçük düzeltmelerde edit_file kullan; baştan yazdıysan etiketleri doğrula.",
    ),
    (
        "web sayfası için görsel seçme",
        _M,
        "via.placeholder.com, placehold.it ve lorempixel.com KAPANDI; kullanan sayfa "
        "kırık görselle açılır. Yer tutucu gerekiyorsa inline SVG data URI kullan.",
    ),
    (
        "büyük dosya yazma",
        _M,
        "write_file çağrısında 'path' alanını HER ZAMAN içerikten önce yaz. İçerik "
        "büyük olduğunda sona bırakılan 'path' düşüyor ve tüm içerik boşa gidiyor.",
    ),
    (
        "yeni dosya oluşturma",
        _S,
        "write_file dosyanın TAMAMINI yazar. Var olan bir dosyayı kısmen değiştireceksen "
        "write_file değil edit_file/multi_edit kullan; içeriği kaybetme.",
    ),
    # --- Keşif ------------------------------------------------------------
    (
        "kod tabanında arama",
        _S,
        "Kesin metin/regex için search_code, dosya deseni için glob, 'X nerede yapılıyor?' "
        "gibi kavramsal sorular için search_codebase kullan. Doğru aracı seç.",
    ),
    (
        "büyük projeyi tanıma",
        _M,
        "Çok sayıda dosyayı körlemesine okumak yerine önce list_dir/glob ile yapıyı "
        "belirle, sonra yalnızca öncelikli dosyaları oku; bağlamı gereksiz şişirme.",
    ),
    # --- Doğrulama --------------------------------------------------------
    (
        "kod değişikliğini doğrulama",
        _S,
        "Kod değiştirdikten sonra test/lint/build çalıştırarak (run_shell) DOĞRULA. "
        "Testler kırılırsa çıktıyı oku ve düzelt; 'çalışıyordur' varsayma.",
    ),
    (
        "bağımlılık eksik",
        _S,
        "'command not found' ya da import hatasında önce aracın/paketin varlığını "
        "kontrol et (which/command -v); gerekiyorsa kur, sonra tekrar dene.",
    ),
    # --- Platform ---------------------------------------------------------
    (
        "platform farkları",
        _M,
        "Linux'a özgü komutları (acpi, /sys/...) macOS'ta çalıştırma; macOS karşılıkları "
        "pmset, ioreg, sw_vers'tir. Önce işletim sistemini teyit et.",
    ),
    (
        "kabuk komutu yazma",
        _S,
        "run_shell komutlarını basit ve tek amaçlı tut; uzun boru zincirleri yerine sade "
        "alternatif ara. Çıkış kodunu ve stderr'i kontrol et.",
    ),
    # --- Güvenlik ---------------------------------------------------------
    (
        "tehlikeli komutlar",
        _M,
        "rm -rf, git push --force, git reset --hard, dd, 'curl | sh' gibi geri-alınamaz "
        "komutlarını çalıştırmadan önce DUR, ne olacağını açıkla ve teyit al.",
    ),
    (
        "sırlar ve anahtarlar",
        _M,
        "API anahtarı, parola, token gibi sırları koda gömme, log'a yazma ya da commit'leme; "
        ".env ve ortam değişkeni kullan, .gitignore'da olduğundan emin ol.",
    ),
    # --- Görev yönetimi ---------------------------------------------------
    (
        "çok adımlı görev",
        _S,
        "Karmaşık işlerde todo_write ile plan çıkar, ilerledikçe güncelle "
        "(in_progress → completed). Basit tek adımlı işlerde todo kullanma.",
    ),
    (
        "belirsiz istek",
        _S,
        "Görev belirsizse ya da birden çok yorumu varsa körlemesine ilerleme; ask_user ile "
        "kısa ve net bir soru sorup netleştir.",
    ),
    (
        "zor karar",
        _S,
        "Mimari seçim ya da karmaşık hata teşhisi gibi tek modelin yanılabileceği kritik "
        "kararlarda council ile birden çok modele danış. Basit adımlarda kullanma.",
    ),
    # --- Güncel bilgi -----------------------------------------------------
    (
        "güncel bilgi gerekli",
        _S,
        "Sürüm, API değişikliği ya da güncel hata çözümü gibi bilgi tarihinin ötesindeki "
        "konularda web_search + web_fetch ile teyit et; ezberden emin konuşma.",
    ),
    # --- Hata teşhisi -----------------------------------------------------
    (
        "hata teşhisi",
        _S,
        "Hatayı tahminle düzeltme; önce KÖK NEDENİ bul. Hata mesajının tamamını oku, "
        "ilgili dosya:satırı aç, hipotez kur, en küçük değişiklikle test et.",
    ),
    (
        "araç hatası tekrarı",
        _M,
        "Bir araç çağrısı HATA döndürdüyse aynı çağrıyı birebir tekrarlama. Neyin yanlış "
        "olduğunu anla (yol mu yanlış, 'old' mu eşleşmedi), sonra DÜZELTİLMİŞ çağrıyı yap.",
    ),
    (
        "test kırılması",
        _S,
        "Test kırılınca (test yanlış olmadıkça) IMPLEMENTASYONU düzelt. Önce kırılan tek "
        "testi izole çalıştır, çıktısını oku, sonra en dar düzeltmeyi uygula.",
    ),
    # --- Git --------------------------------------------------------------
    (
        "git commit",
        _S,
        "Kullanıcı istemeden commit/push yapma. İstenince git status + git diff ile "
        "değişikliği anla, conventional commit formatında net mesaj yaz.",
    ),
    (
        "git güvenliği",
        _M,
        "git reset --hard, git push --force, git clean -fd gibi geri-alınamaz komutlardan "
        "önce dur ve teyit al; kullanıcının commit'lenmemiş emeğini yok edebilirsin.",
    ),
    # --- Kapsam disiplini -------------------------------------------------
    (
        "kapsam disiplini",
        _M,
        "Sadece istenen işi yap. İstenmeyen refactor, biçim değişikliği ya da 'yol üstü "
        "iyileştirme' ekleme; diff'i küçük ve gözden geçirilebilir tut.",
    ),
    (
        "mevcut kod stili",
        _S,
        "Yeni kod yazarken çevredeki koda bak ve taklit et: isimlendirme, girinti, import "
        "düzeni, hata yönetimi deseni. Kod tek elden yazılmış gibi görünsün.",
    ),
    (
        "varsayılan yol uydurma",
        _M,
        "Dosya yolu, fonksiyon adı ya da import yolu UYDURMA. Emin değilsen glob/search_code "
        "ile var olduğunu doğrula; hayali yola yazmak sessiz hataya yol açar.",
    ),
    # --- Dil / ortam ------------------------------------------------------
    (
        "python ortamı",
        _S,
        "Python'da paket/komut çalışmıyorsa doğru sanal ortamı (venv) kontrol et; 'python' "
        "yoksa 'python3' dene. Sistem geneline kurmadan önce venv aktif mi bak.",
    ),
    (
        "node bağımlılıkları",
        _S,
        "JS/TS projesinde 'module not found' ise node_modules var mı ve doğru paket "
        "yöneticisi hangisi (lockfile'a bak) teyit et; yanlış yöneticiyle kurma.",
    ),
    (
        "karakter kodlaması",
        _M,
        "Dosya okuma/yazmada encoding varsayma; UTF-8 kullan. Türkçe karakterlerde bozulma "
        "olursa errors='ignore' ile örtme, nedeni araştır.",
    ),
    # --- Verimlilik -------------------------------------------------------
    (
        "verimli keşif",
        _S,
        "Bağımsız birden çok okumayı/aramayı tek turda topluca iste; her biri için ayrı tur "
        "harcayıp gereksiz gecikme yaratma.",
    ),
    (
        "büyük çıktı",
        _S,
        "run_shell ya da arama çok uzun çıktı üretecekse daralt (head, grep, --oneline, -n). "
        "Binlerce satırı bağlama boca etme.",
    ),
    # --- Frontend: mimari ------------------------------------------------
    (
        "website oluşturma",
        _S,
        "Kod yazmadan önce net bir stil yönü seç (editorial, brutalism, glassmorphism, "
        "bento, swiss...). 'temiz minimal' bir yön değildir; şablon görünümlü çıktı üretir.",
    ),
    (
        "website oluşturma",
        _M,
        "Varsayılan şablon üretme: ortalanmış başlık + gradyan blob + jenerik CTA, tek "
        "vurgu rengiyle gri-beyaz kart ızgarası. Hiyerarşi, katman, ritim ve karakter kat.",
    ),
    (
        "react bileşen mimarisi",
        _S,
        "Bileşeni sorumluluklara böl: UI, veri erişimi ve state ayrı. Tekrarlanan bloğu "
        "reusable component yap, sayfa dosyasını orchestration katmanı olarak kullan. "
        "~250 satır sınır.",
    ),
    (
        "next.js app router",
        _S,
        "Server/client ayrımına dikkat: 'use client' yalnızca etkileşim/state gereken "
        "yaprak bileşende. Veri çekmeyi server component'te yap; client'a veri prop olarak in.",
    ),
    (
        "react hook kuralları",
        _M,
        "Hook'ları koşul/döngü içinde çağırma; üst seviyede sabit sırada olmalı. useEffect "
        "bağımlılık dizisini eksik bırakma; her okunan değer diziye girmeli, "
        "yoksa stale closure.",
    ),
    (
        "react performans",
        _S,
        "Gereksiz render'ı ölç sonra çöz: React DevTools Profiler. Erken memo/useCallback "
        "serpiştirme; asıl maliyet büyük liste ve pahalı hesap. Liste öğelerine kararlı "
        "key ver (index değil).",
    ),
    (
        "state yönetimi",
        _S,
        "Sunucu state'ini (TanStack Query/SWR) client store'a (Zustand/Jotai) kopyalama. "
        "Türetilebilen değeri saklama, hesapla. Paylaşılabilir state'i (filtre/sekme/arama) "
        "URL'de tut.",
    ),
    # --- Frontend: CSS / stil --------------------------------------------
    (
        "css tasarım token",
        _S,
        "Renk/tipografi/boşluğu CSS custom property olarak tanımla, tekrar tekrar hardcode "
        "etme. clamp() ile akışkan ölçek, oklch() ile renk. Tek yerden değiştirilebilir olsun.",
    ),
    (
        "css animasyon",
        _M,
        "Yalnızca compositor-dostu özellikleri animasyonla: transform, opacity, clip-path. "
        "width/height/top/left/margin/font-size animasyonlama; layout tetikler, kasar.",
    ),
    (
        "responsive tasarım",
        _S,
        "320/375/768/1024/1440/1920'de test et; yatay taşma olmamalı. Geniş içeriği (tablo, "
        "kod bloğu) overflow-x:auto ile kendi kutusunda kaydır, sayfa gövdesi yatay kaymamalı.",
    ),
    (
        "erişilebilirlik",
        _S,
        "Semantik HTML önce: header/nav/main/section/footer, div yığını değil. Etkileşimli "
        "öğede klavye erişimi + görünür focus. Renk kontrastı ve prefers-reduced-motion'a uy.",
    ),
    (
        "web tipografi",
        _S,
        "En çok iki font ailesi. font-display:swap, yalnızca kritik ağırlığı preload et. "
        "Ölçek kontrastıyla hiyerarşi kur; her şeyi aynı boyutta verme.",
    ),
    # --- Backend / API ---------------------------------------------------
    (
        "api tasarımı",
        _S,
        "Tutarlı zarf kullan: success bayrağı + data (hata varsa null) + error mesajı. "
        "Sayfalı yanıtta meta (total/page/limit). Hata durumunda anlamlı HTTP kodu döndür.",
    ),
    (
        "api güvenliği",
        _M,
        "Tüm girdiyi sistem sınırında doğrula (şema tabanlı). Dış veriye (API yanıtı, "
        "kullanıcı girdisi, dosya) güvenme. State değiştiren endpoint'te CSRF + rate "
        "limit olsun.",
    ),
    (
        "kimlik doğrulama",
        _M,
        "Parolayı düz saklama; bcrypt/argon2 ile hash'le. Token'ı log'a yazma. Yetki "
        "kontrolünü her istekte sunucuda yap, client'taki gizlemeye güvenme (yetki atlatma).",
    ),
    (
        "veri doğrulama",
        _S,
        "Girdiyi işlemeden önce şema ile doğrula (pydantic/zod). Hızlı ve net hata ver. "
        "Client tarafı doğrulama UX içindir; asıl güvenlik sunucu tarafı doğrulamadır.",
    ),
    # --- Veritabanı ------------------------------------------------------
    (
        "sql sorgu",
        _M,
        "SQL'i string birleştirmeyle kurma; parametreli sorgu kullan (injection). Sorguya "
        "LIMIT koy, sınırsız çekme. N+1 sorgudan kaçın: JOIN ya da toplu (batch) yükle.",
    ),
    (
        "veritabanı şeması",
        _S,
        "Migration geri-alınabilir yaz; production'da tabloyu doğrudan elle değiştirme. "
        "Sık sorgulanan kolona index ekle; ama her kolona değil (yazma maliyeti).",
    ),
    (
        "veritabanı migrasyonu",
        _M,
        "Yıkıcı migration (kolon silme, tip değişimi) tek adımda deploy etme: önce ekle, "
        "geç, sonra sil (expand-contract). Veri kaybı geri alınamaz.",
    ),
    # --- Test ------------------------------------------------------------
    (
        "test yazma",
        _S,
        "Önce testi yaz ve KIRILDIĞINI gör (RED), sonra en az kodla geçir (GREEN), sonra "
        "iyileştir. AAA deseni: Arrange-Act-Assert. Test adı davranışı anlatsın.",
    ),
    (
        "test kapsamı",
        _S,
        "Mutlu yolu değil kenar durumları test et: boş girdi, null, sınır değer, hata yolu. "
        "%80 kapsam hedefle ama kapsam yüzdesi değil, gerçek davranış güvencesi asıl amaç.",
    ),
    (
        "test izolasyonu",
        _M,
        "Testler birbirine sızmasın: paylaşılan global state, sıralama bağımlılığı, gerçek ağ/"
        "saat kullanma. Dış bağımlılığı mock'la; testi deterministik tut, timeout'a dayanma.",
    ),
    (
        "flaky test",
        _M,
        "Ara sıra kırılan testi 'tekrar çalıştır'la geçme. Nedeni bul: yarış durumu, sabit "
        "bekleme (sleep), sıra bağımlılığı ya da gerçek zaman/rastgelelik. "
        "Deterministik hale getir.",
    ),
    # --- Hata teşhisi / debug --------------------------------------------
    (
        "sistematik hata ayıklama",
        _S,
        "Düzeltme önermeden önce hatayı ÜRET ve izole et. Hipotez kur, en küçük değişiklikle "
        "test et, doğrula. Tahmine dayalı 'shotgun' düzeltme yapma; kök nedeni bul.",
    ),
    (
        "sessiz hata",
        _M,
        "Hatayı sessizce yutma (boş except, yutulan promise, kör fallback). Açıkça yakala, "
        "bağlamıyla logla, yukarı ilet. Yanlış fallback gerçek sorunu gizler.",
    ),
    (
        "regresyon",
        _S,
        "Bir bug'ı düzeltmeden önce onu YAKALAYAN başarısız bir test yaz, sonra düzelt "
        "(yeşile çevir). Böylece hata bir daha döndüğünde test yakalar.",
    ),
    # --- Kod kalitesi / refactor -----------------------------------------
    (
        "refactor",
        _S,
        "Davranış koruyan refactor'da önce testlerin yeşil olduğunu gör, değiştir, tekrar "
        "yeşil olduğunu gör. Refactor ile davranış değişikliğini aynı commit'te karıştırma.",
    ),
    (
        "dead code temizliği",
        _M,
        "Kullanılmayan kodu 'belki lazım olur' diye tutma (YAGNI). Ama silmeden önce gerçekten "
        "kullanılmadığını araçla doğrula (grep/knip/ts-prune); dinamik çağrı olabilir.",
    ),
    (
        "fonksiyon boyutu",
        _S,
        "Fonksiyonu küçük ve tek sorumluluklu tut (<50 satır). Derin içe geçmeyi (>4 seviye) "
        "erken return ile düzleştir. Sihirli sayıyı adlandırılmış sabite çıkar.",
    ),
    (
        "değişmezlik",
        _S,
        "Var olan nesneyi yerinde değiştirme; değiştirilmiş yeni kopya döndür. Gizli yan "
        "etkiyi önler, hata ayıklamayı kolaylaştırır. Python'da frozen dataclass/tuple "
        "tercih et.",
    ),
    (
        "erken soyutlama",
        _M,
        "İki kez tekrar görmeden soyutlama üretme (YAGNI). Spekülatif genellik, yanlış "
        "soyutlamaya kilitler. Tekrar gerçekleşince, spekülatifken değil, refactor et.",
    ),
    # --- Güvenlik (genel) ------------------------------------------------
    (
        "xss önleme",
        _M,
        "Kullanıcı girdisini sanitize etmeden HTML'e enjekte etme. innerHTML / "
        "dangerouslySetInnerHTML'den kaçın; mecbursan vetted bir sanitizer'dan geçir. "
        "Şablon değerlerini escape et.",
    ),
    (
        "yol gezinme",
        _M,
        "Kullanıcıdan gelen dosya yolunu doğrulamadan kullanma (../ ile üst dizine çıkabilir). "
        "Kökten sonra normalize et, kök dışına çıkanı reddet.",
    ),
    (
        "bağımlılık güvenliği",
        _S,
        "Yeni paket eklemeden önce bakımlı ve güvenilir mi bak. CDN'den yüklerken SRI kullan. "
        "Bilinen açıkları tara (pip-audit/npm audit). Kritik bağımlılığı mümkünse "
        "kendin barındır.",
    ),
    # --- Performans ------------------------------------------------------
    (
        "performans optimizasyonu",
        _M,
        "Ölçmeden optimize etme (erken optimizasyon). Önce profille, darboğazı bul, sonra "
        "düzelt. Okunabilirliği kurnazlığa feda etme; asıl kazanç genellikle algoritma/IO'da.",
    ),
    (
        "önbellekleme",
        _S,
        "Pahalı ve sık tekrarlanan hesabı/isteği önbellekle; ama geçersizleştirme stratejisini "
        "en baştan tasarla. Stale-while-revalidate: önbelleği hemen dön, arkada tazele.",
    ),
    (
        "paralel yükleme",
        _S,
        "Bağımsız veriyi paralel çek; parent-child istek şelalesinden kaçın. Bağımsız "
        "okumaları/aramaları tek turda topla, her biri için ayrı gecikme harcama.",
    ),
    # --- Python ----------------------------------------------------------
    (
        "python tip ipuçları",
        _S,
        "Tüm fonksiyon imzasına tip anotasyonu ver. Değişmez veri için frozen dataclass / "
        "NamedTuple. Protocol ile duck-typing arayüzü tanımla, somut sınıfa bağlanma.",
    ),
    (
        "python hata yönetimi",
        _M,
        "Çıplak 'except:' yazma; yakalayacağın istisnayı daralt. Kaynağı with "
        "(context manager) ile yönet, elle kapatma unutma. print yerine logging kullan.",
    ),
    (
        "python paketleme",
        _S,
        "Bağımlılığı üst VE alt sınırla sabitle; büyük sürüm atlaması kurulumu sessizce "
        "bozmasın. Sırları .env + ortam değişkeninden oku, koda gömme; gerekli sır "
        "başlangıçta yoksa hata ver.",
    ),
    # --- TypeScript / JS -------------------------------------------------
    (
        "typescript tip güvenliği",
        _M,
        "'any' ile tip sistemini susturma; unknown + daraltma kullan. Non-null '!' assertion'ı "
        "körlemesine serpme. strict modu aç; tsc --noEmit ile değişiklikten sonra "
        "tip kontrol et.",
    ),
    (
        "async doğruluğu",
        _M,
        "await'i unutma; floating promise sessiz hataya yol açar. Bağımsız promise'leri "
        "Promise.all ile paralelle, sırayla await'leme. try/catch ile reddi yakala.",
    ),
    # --- CLI / araç geliştirme -------------------------------------------
    (
        "cli tasarımı",
        _S,
        "Komut çıkış kodunu doğru döndür (başarı 0, hata !=0). Hata mesajını stderr'e, sonucu "
        "stdout'a yaz. Yıkıcı işlemde onay iste; --yes ile atlanabilsin.",
    ),
    (
        "dosya kodlaması",
        _M,
        "Dosya okuma/yazmada encoding varsayma; açıkça UTF-8 ver. errors='ignore' ile "
        "bozulmayı örtme, nedenini araştır. Yol birleştirmede os.path/pathlib kullan, "
        "string ekleme değil.",
    ),
    # --- Deployment / ortam ----------------------------------------------
    (
        "docker",
        _S,
        "Çok aşamalı (multi-stage) build ile imajı küçült; build araçlarını runtime imajına "
        "taşıma. .dockerignore ile gereksiz dosyayı dışla. Sırları imaja gömme, "
        "runtime'da ver.",
    ),
    (
        "ortam yapılandırması",
        _S,
        "Yapılandırmayı koddan ayır (12-factor): ortam değişkeni. Kod içi varsayılanla "
        "dosyadaki değeri ayrıştırma; tek kaynak olsun. Gerekli değişken eksikse "
        "başlangıçta net hata ver.",
    ),
    (
        "ci/cd",
        _S,
        "Merge öncesi tüm otomatik kontrol (lint/type/test) yeşil olmalı. Kalite kapısından "
        "geçmemiş kodu birleştirme. Çakışmayı çöz, dalı hedefle güncel tut.",
    ),
    # --- Dokümantasyon ---------------------------------------------------
    (
        "dokümantasyon",
        _S,
        "Ne yaptığını değil NEDEN yaptığını yorumla; kod zaten 'ne'yi gösterir. Yorumu kodla "
        "senkron tut, yoksa yanıltır (comment rot). README'yi çalışan minimal örnekle başlat.",
    ),
    # --- Genel mühendislik disiplini -------------------------------------
    (
        "araştırma önce",
        _S,
        "Sıfırdan yazmadan önce ara: benzer bir çözüm, kütüphane ya da örnek var mı. "
        "Battle-tested kütüphane, elle yazılan çözümden iyidir. Tekerleği yeniden icat etme.",
    ),
    (
        "planlama",
        _S,
        "Karmaşık işe kodla başlama; önce planla, fazlara böl, bağımlılık ve riski belirle. "
        "Bir fazı yarım bırakma; kapsam büyürse fazı böl, sessizce genişletme.",
    ),
    (
        "kod incelemesi",
        _S,
        "İş bitince gözden geçir: güvenlik önce (sır/injection/yetki), sonra kalite (boyut/"
        "isim/hata yönetimi). Hardcode edilmiş sır ya da debug print bırakma.",
    ),
)


#: Ölçülmeden, bilinen araç/servis davranışından YAZILMIŞ dersler.
#:
#: Görmeden yazmak yasak değil ama ölçülmüş dersle AYNI ağırlıkta olamaz. Düşük
#: güvenle başlarlar: doğruysa gerçek kullanım `reinforce` ile yukarı çeker,
#: yanlışsa aşağı iter ve eşiğin altına düşünce artık enjekte edilmez. Böylece
#: yanlış bir yazılı ders kalıcı zarar vermez.
#:
#: MCP sunucularına ait yordamsal dersler buraya girer; `tags` alanı hangi
#: teknoloji/sunucu için geçerli olduğunu söyler (bkz. `lesson_tags`).
UNMEASURED_CONFIDENCE = 0.6

_WRITTEN: tuple[tuple[str, LessonKind, str, tuple[str, ...]], ...] = (
    # --- Her MCP sunucusu için geçerli disiplin ---------------------------- #
    (
        "MCP aracı kullanma",
        _M,
        "MCP aracı hata döndürdüğünde AYNI çağrıyı aynı argümanlarla tekrarlama. "
        "Dönen hatadaki yol/biçim ipucunu uygula (önek ekle ya da kaldır, göreli "
        "yola geç). Aynı çağrı ikinci kez tekrar kapısına takılır ve tur ilerlemez.",
        (),
    ),
    (
        "MCP aracı kullanma",
        _M,
        "Bir MCP sunucusunun araç listesi SINIRLIDIR; listede olmayan bir işi o "
        "sunucudan bekleme. Yapamadığı bir iş için dosya/kabuk araçlarına geç. "
        "Israr etmek turu tüketir, yeteneği yaratmaz.",
        (),
    ),
    (
        "MCP aracı kullanma",
        _M,
        "MCP aracı 'başarılı' dediğinde işin gerçekten olduğunu VARSAYMA. Sonucu "
        "ayrı bir okuma çağrısıyla ya da dosya/kayıt kontrolüyle doğrula; uzak "
        "sunucular başarı raporlayıp hiçbir şey değiştirmemiş olabilir.",
        (),
    ),
    (
        "dış sistemde değişiklik",
        _M,
        "MCP ile dış sistemde değişiklik yapmadan ÖNCE mevcut durumu oku. "
        "Körlemesine yazma var olan kaydı sessizce ezer ve geri alınamaz.",
        (),
    ),
    (
        "dış sistemde değişiklik",
        _M,
        "Yıkıcı ya da geri alınamaz MCP işlemlerinde (silme, yayınlama, gönderme, "
        "ödeme) önce ask_user ile onay al. 'Muhtemelen bunu istiyordur' diye ilerleme.",
        (),
    ),
    (
        "MCP listeleme",
        _M,
        "Çok kayıt döndüren MCP listeleme araçlarında sayfa/limit ver. Sınırsız "
        "çekmek bağlamı doldurur ve asıl işe yer kalmaz.",
        (),
    ),
    (
        "MCP kimlik doğrulama",
        _M,
        "401/403 dönen MCP çağrısını farklı argümanlarla tekrar deneme: sorun "
        "yetki ya da token'dır ve kullanıcının müdahalesini gerektirir. Durumu "
        "bildir, denemeye devam etme.",
        (),
    ),
    (
        "hız sınırı",
        _M,
        "429 (rate limit) dönen çağrıyı hemen tekrarlama. İstenen işi küçült ya da "
        "bekle; peş peşe deneme sunucunun kilidini uzatır.",
        (),
    ),
    # --- Oyun ve 3B motorları ---------------------------------------------- #
    (
        "godot unity unreal blender roblox oyun sahnesi düzenleme",
        _M,
        "Sahne/proje dosyalarının biçimini motorun KENDİSİ üretir (Godot .tscn, "
        "Unity .unity/.prefab, Unreal .uasset, Blender .blend). Elle yazmak dosyayı "
        "sessizce bozar. Motorun ya da MCP'sinin aracını kullan; araç o değişikliği "
        "yapamıyorsa dosyayı BAŞTAN yazma, hedefli düzenle.",
        (),
    ),
    (
        "godot unity unreal blender roblox oyun sahnesi düzenleme",
        _M,
        "Yazılan oyun scripti bir düğüme/nesneye BAĞLANMADAN çalışmaz. Dosyayı "
        "oluşturmak işi bitirmez; bağlantıyı kur ve sahnede göründüğünü doğrula.",
        (),
    ),
    (
        "godot unity unreal oyun asseti import etme",
        _M,
        "Assetler motora import edilmeden yüklenmez ('No loader found for resource' "
        "gibi hatalar buradan gelir). Yeni asset ekledikten sonra projenin import "
        "adımını çalıştır.",
        (),
    ),
    (
        "godot unity unreal oyun projesini çalıştırıp doğrulama",
        _M,
        "Motorun projeyi AÇABİLMESİ oyunun ÇALIŞTIĞI anlamına gelmez. Headless "
        "açılış yalnız dosyaların iyi biçimli olduğunu gösterir; çıkış kodu 0 olsa "
        "bile çıktıdaki ERROR satırlarını oku.",
        (),
    ),
    (
        "görsel asset seçme ve içeriğini görme",
        _M,
        "Dosya ADI içeriği anlatmaz: 'player.png' bir logo, 'arka.jpg' bir ekran "
        "görüntüsü olabilir. Bir asseti kullanmadan önce view_image ile BAK.",
        (),
    ),
    (
        "blender freecad sketchup 3B modelleme",
        _M,
        "Blender ve benzeri araçlarda işlemler AKTİF SEÇİME uygulanır. Seçimi "
        "doğrulamadan işlem çalıştırmak yanlış nesneyi değiştirir ve geri alınamaz.",
        (),
    ),
    (
        "three.js playcanvas tarayıcı 3B sahnesi",
        _S,
        "Three.js/PlayCanvas sahnesinde konsol temiz olsa da ekran boş olabilir: "
        "kamera konumu, ışık ve nesne ölçeği ayrı ayrı kontrol edilmeli.",
        (),
    ),
    # --- CAD ---------------------------------------------------------------- #
    (
        "freecad fusion 360 sketchup CAD modeli değiştirme",
        _M,
        "Parametrik CAD modelinde (FreeCAD, Fusion 360) bir ölçüyü değiştirmeden "
        "önce kısıt ve bağımlılık zincirini oku. Tek ölçü, bağlı özelliklerin "
        "tamamını bozabilir.",
        (),
    ),
    (
        "freecad fusion 360 sketchup CAD modeli değiştirme",
        _M,
        "Birim sistemini (mm/inch) baştan doğrula. Yanlış birim, model doğru "
        "görünürken üretimde ölçek hatası olarak ortaya çıkar.",
        (),
    ),
    # --- Web, CMS, e-ticaret ------------------------------------------------ #
    (
        "shopify woocommerce magento prestashop bigcommerce mağaza ürün fiyat ve stok güncelleme",
        _M,
        "Canlı mağazada fiyat/stok değişikliği anında müşteriye yansır ve geri "
        "alınamaz. Önce mevcut değeri oku, tek kayıtta dene, sonucu doğrula; "
        "ancak sonra toplu uygula.",
        (),
    ),
    (
        "shopify woocommerce toplu ürün ve kayıt güncelleme",
        _M,
        "Toplu güncellemeden önce KAÇ kaydın etkileneceğini say ve kullanıcıya "
        "söyle. 'Hepsi' denen kümenin büyüklüğü çoğu zaman beklenenden farklıdır.",
        (),
    ),
    (
        "shopify woocommerce ürün eşleştirme ve SKU",
        _M,
        "Ürün/kayıt eşleştirmesini ADA göre değil KİMLİĞE (id, SKU, handle) göre "
        "yap. Benzer adlar yanlış kaydı günceller ve hata geç fark edilir.",
        (),
    ),
    (
        "wordpress shopify webflow tema ve eklenti düzenleme",
        _M,
        "CMS tema ve eklenti dosyalarını doğrudan düzenleme: ilk güncelleme "
        "değişikliği siler. Child theme, snippet ya da resmi genişletme noktasını "
        "kullan.",
        (),
    ),
    (
        "wordpress webflow wix squarespace içerik yayınlama",
        _M,
        "Taslak ile yayınlanmış içerik ayrıdır. Değişikliği taslakta hazırla, "
        "yayına almayı kullanıcıya onaylat.",
        (),
    ),
    # --- Google ekosistemi -------------------------------------------------- #
    (
        "google sheets e-tablo hücre ve aralık güncelleme",
        _M,
        "Sheets'te bir aralığa yazmadan önce mevcut içeriği oku: yazma formülleri, "
        "biçimlendirmeyi ve komşu sütunları sessizce ezebilir.",
        (),
    ),
    (
        "google drive docs dosya bulma ve kimlik",
        _M,
        "Drive/Docs'ta aynı adlı birden çok dosya olabilir. Adla değil dosya "
        "KİMLİĞİYLE çalış; ad araması yanlış belgeyi düzenletir.",
        (),
    ),
    (
        "gmail e-posta yazma ve gönderme",
        _M,
        "E-postayı TASLAK olarak oluştur ve göndermeyi kullanıcıya bırak. "
        "Gönderilen e-posta geri alınamaz ve alıcıya gerçek kişiler dahildir.",
        (),
    ),
    (
        "google calendar takvim etkinliği ve davetli",
        _M,
        "Takvim etkinliğine davetli eklemek onlara e-posta gönderir. Test veya "
        "taslak etkinlik oluştururken davetli ekleme.",
        (),
    ),
    (
        "google analytics 4 search console analitik veri okuma",
        _M,
        "GA4 ve Search Console verisi gecikmelidir; son 24-48 saat eksik olabilir. "
        "Taze aralığı kesin sonuç gibi raporlama, tarih aralığını açıkça yaz.",
        (),
    ),
    (
        "youtube video yükleme ve yayınlama",
        _M,
        "YouTube'a yükleme yaparken görünürlüğü önce 'unlisted/private' yap; "
        "yayına almayı kullanıcı onaylasın. Yayınlanan video abonelere bildirilir.",
        (),
    ),
    # --- Reklam platformları (PARA HARCAR) ---------------------------------- #
    (
        "meta ads google ads tiktok ads linkedin reklam kampanyası ve bütçe yönetme",
        _M,
        "Reklam API'lerinde kampanya, bütçe ve teklif değişiklikleri GERÇEK PARA "
        "harcar. Hiçbir değişikliği onay almadan uygulama; ne kadar harcanacağını "
        "açıkça söyle.",
        (),
    ),
    (
        "meta ads google ads tiktok ads linkedin reklam kampanyası ve bütçe yönetme",
        _M,
        "Yeni kampanyayı önce DURAKLATILMIŞ (paused) oluştur, yapısını ve hedef "
        "kitlesini doğrula, aktifleştirmeyi ayrı bir adımda kullanıcıya onaylat.",
        (),
    ),
    (
        "meta ads google ads reklam bütçesi ve para birimi",
        _M,
        "Reklam API'lerinde bütçe çoğu zaman para biriminin KÜÇÜK biriminde "
        "(kuruş/cent) verilir. Birimi karıştırmak 100 kat fazla harcamaya yol açar; "
        "değeri yazmadan önce birimi doğrula.",
        (),
    ),
    (
        "meta ads google ads reklam metni ve görseli",
        _M,
        "Yayınlanacak reklam metnini ve görselini kullanıcıya GÖSTER. Yayınlanan "
        "reklam markanın adına konuşur ve geri alınması yayından sonra olur.",
        (),
    ),
    (
        "meta pixel google ads dönüşüm ölçümü ve izleme",
        _M,
        "Piksel, dönüşüm olayı ve izleme ayarlarını değiştirmek geçmiş ölçümü "
        "bozar ve optimizasyonu sıfırlar. Mevcut yapıyı oku, değişikliği ve "
        "sonucunu açıkça bildir.",
        (),
    ),
    # --- Tasarım, içerik, video --------------------------------------------- #
    (
        "figma canva photoshop illustrator tasarım dosyası düzenleme",
        _M,
        "Tasarım aracında bir bileşeni ya da stili değiştirmek TÜM örneklerini "
        "değiştirir. Kapsamı ölç ve söyle; tek ekran sanıp kütüphaneyi bozma.",
        (),
    ),
    (
        "figma canva photoshop görsel dışa aktarma",
        _M,
        "Dışa aktarım ayarları (ölçek, format, renk profili, saydamlık) sonucu "
        "belirler. Varsayılana güvenme; hedefe göre açıkça seç.",
        (),
    ),
    (
        "premiere after effects davinci capcut video düzenleme ve render",
        _S,
        "Video render uzun sürer ve yanlış ayar tüm süreyi çöpe atar. Önce kısa "
        "bir aralığı düşük çözünürlükte render edip doğrula.",
        (),
    ),
    # --- Agent temel araçları ----------------------------------------------- #
    (
        "fetch web sayfası içeriği okuma",
        _M,
        "Fetch ile alınan sayfa ham HTML olabilir ve içerik JavaScript ile "
        "doluyorsa boş görünür. İçerik eksikse tarayıcı aracına geç, aynı adresi "
        "tekrar çekme.",
        (),
    ),
    (
        "playwright puppeteer browserbase tarayıcı otomasyonu",
        _M,
        "CSS seçicileri kırılgandır. Metin ve rol tabanlı seçici tercih et; sabit "
        "bekleme (sleep) yerine öğenin görünmesini bekle.",
        (),
    ),
    (
        "zaman damgası saat dilimi ve tarih",
        _M,
        "Zaman damgaları saat dilimi taşır. Yerel saat ile UTC karıştırmak "
        "raporlarda bir günlük kaymaya yol açar; hangi dilimde çalıştığını yaz.",
        (),
    ),
    (
        "context7 kütüphane dokümanı ve sürüm",
        _M,
        "Doküman ararken kütüphanenin SÜRÜMÜNÜ belirt. Sürümsüz doküman kaldırılmış "
        "ya da değişmiş API verir ve kod sessizce çalışmaz.",
        (),
    ),
    (
        "markitdown pdf office belge dönüştürme",
        _M,
        "Belge dönüştürme (PDF/Office to Markdown) biçim kaybeder: tablo, dipnot ve "
        "sütun düzeni bozulabilir. Dönüşen içeriği kullanmadan önce kritik "
        "bölümleri doğrula.",
        (),
    ),
    # --- Git, bulut, DevOps ------------------------------------------------- #
    (
        "github gitlab git deposu dal ve geçmiş değiştirme",
        _M,
        "force-push, dal silme ve geçmiş yeniden yazma GERİ ALINAMAZ ve başkalarının "
        "işini bozar. Bu işlemleri onay almadan yapma.",
        (),
    ),
    (
        "git commit hazırlama ve sır taraması",
        _M,
        "Commit'ten önce diff'i oku ve sır/anahtar taraması yap. Depoya giren bir "
        "anahtar, silinse bile geçmişte kalır ve iptal edilmesi gerekir.",
        (),
    ),
    (
        "docker konteyner ve imaj etiketi",
        _M,
        "İmaj etiketini sabitle; 'latest' bugün çalışan kurulumu yarın sessizce "
        "değiştirir ve hatayı üretimde bulursun.",
        (),
    ),
    (
        "kubernetes küme deployment ve namespace",
        _M,
        "Kubernetes'te apply/delete YANLIŞ context ya da namespace'te çalışırsa "
        "üretimi düşürür. Komuttan önce hangi kümede ve hangi namespace'te "
        "olduğunu doğrula.",
        (),
    ),
    (
        "aws google cloud azure bulut kaynağı silme",
        _M,
        "Bulut kaynağını silmek faturayı değil VERİYİ de siler ve çoğu geri "
        "alınamaz. Önce listele, neyin gideceğini yaz, sonra onay al.",
        (),
    ),
    (
        "vercel cloudflare production dağıtım",
        _M,
        "Production dağıtımı anında canlıya çıkar. Önce preview/staging dağıt, "
        "doğrula, production'ı ayrı bir adımda onaylat.",
        (),
    ),
    (
        "sentry hata kaydı takibi",
        _M,
        "Hata kaydını kapatmak hatayı ÇÖZMEZ. Kapatmadan önce düzeltmenin "
        "dağıtıldığını ve yeni olay gelmediğini doğrula.",
        (),
    ),
    # --- Veritabanı ---------------------------------------------------------- #
    (
        "postgresql mysql mongodb sqlite veritabanında kayıt güncelleme ve silme",
        _M,
        "UPDATE ve DELETE'i WHERE olmadan çalıştırma. Önce aynı koşulla SELECT "
        "count(*) çalıştır, kaç satırın etkileneceğini gör ve söyle.",
        (),
    ),
    (
        "postgresql mysql veritabanı şema değişikliği ve migration",
        _M,
        "Üretimde şema değişikliği tabloyu kilitleyebilir ve uygulamayı durdurur. "
        "Migration geri alınabilir olmalı ve büyük tabloda çevrimiçi yöntem "
        "kullanılmalı.",
        (),
    ),
    (
        "redis önbellek yönetimi",
        _M,
        "Redis'te FLUSHALL ve KEYS üretimde yasaktır: biri tüm veriyi siler, "
        "diğeri sunucuyu kilitler. Tarama gerekiyorsa SCAN kullan.",
        (),
    ),
    (
        "pinecone qdrant elasticsearch vektör index ve arama",
        _M,
        "Vektör index/collection silmek geri alınamaz ve yeniden gömme maliyetlidir. "
        "Ayrıca boyut ya da uzaklık metriği uyuşmazlığı hata vermeden YANLIŞ sonuç "
        "döndürür; ikisini de doğrula.",
        (),
    ),
    (
        "supabase firebase erişim kuralı ve RLS değiştirme",
        _M,
        "Satır düzeyi güvenlik (RLS) ya da veritabanı kurallarını gevşetmek veriyi "
        "herkese açabilir. Kural değişikliğini onay almadan uygulama ve etkisini yaz.",
        (),
    ),
    # --- İletişim ve proje yönetimi ----------------------------------------- #
    (
        "slack discord telegram whatsapp mesaj gönderme",
        _M,
        "Slack/Discord/Telegram/WhatsApp mesajı gönderildikten sonra geri alınamaz "
        "ve gerçek kişilere ulaşır. Metni önce göster, göndermeyi onaylat.",
        (),
    ),
    (
        "slack discord telegram whatsapp mesaj gönderme",
        _M,
        "Kanal ve kişi kimliğini gönderimden önce doğrula. Benzer adlı kanala "
        "gönderilen mesaj kurumsal bir hatadır ve silinse bile görülmüştür.",
        (),
    ),
    (
        "notion jira linear trello asana clickup monday görev yönetimi",
        _M,
        "Toplu durum/atama değişikliği herkese bildirim yağdırır. Kaç kaydı "
        "etkileyeceğini söyle ve gerekiyorsa parçalara böl.",
        (),
    ),
    (
        "jira linear trello görev kapatma",
        _M,
        "Bir işi 'tamamlandı' yapmadan önce gerçekten çözüldüğünü doğrula. "
        "Kapatılan kayıt gözden düşer ve sorun sessizce yaşamaya devam eder.",
        (),
    ),
    # --- Otomasyon, CRM, satış ---------------------------------------------- #
    (
        "stripe ödeme iade ve abonelik işlemi",
        _M,
        "Ödeme, iade ve abonelik işlemleri GERÇEK PARADIR ve geri alınamaz. Test "
        "anahtarıyla dene, gerçek işlemde açık onay al ve tekrarları önlemek için "
        "idempotency anahtarı kullan.",
        (),
    ),
    (
        "n8n make zapier otomasyon senaryosu",
        _M,
        "Bir otomasyon senaryosunu aktifleştirmek gerçek dünyada iş yapar "
        "(e-posta atar, kayıt oluşturur, ödeme başlatır). Önce tek seferlik "
        "çalıştırma ile dene, sonucu gör, sonra aktifleştir.",
        (),
    ),
    (
        "hubspot salesforce pipedrive CRM kaydı düzenleme",
        _M,
        "CRM'de kayıt birleştirme geri alınamaz ve ilişkili geçmişi taşır. "
        "Birleştirmeden önce iki kaydı da oku ve kullanıcıya doğrulat.",
        (),
    ),
    (
        "klaviyo mailchimp e-posta kampanyası gönderimi",
        _M,
        "Kampanya gönderimi geri alınamaz. Segment büyüklüğünü say, kime "
        "gideceğini yaz ve gönderimi kullanıcıya onaylat; test gönderimini kendi "
        "adresine yap.",
        (),
    ),
    (
        "twilio SMS ve sesli arama",
        _M,
        "SMS ve sesli arama ücretlidir ve gerçek numaralara ulaşır. Test ederken "
        "yalnız kullanıcının verdiği numarayı kullan, listeye gönderim yapma.",
        (),
    ),
    # --- Sosyal medyada organik paylaşım (reklamdan AYRI risk) ------------- #
    (
        "instagram facebook pinterest x twitter linkedin sosyal medya paylaşımı",
        _M,
        "Sosyal medya gönderisi yayınlandığı anda HERKESE açıktır ve markanın adına "
        "konuşur. Silmek geri almaz: bildirim gitmiş, ekran görüntüsü alınmış olur. "
        "Metni ve görseli önce kullanıcıya göster, yayınlamayı onaylat.",
        (),
    ),
    (
        "reddit topluluk paylaşımı",
        _M,
        "Reddit'te her topluluğun kendi kuralları vardır ve kendi içeriğini tanıtmak "
        "çoğunda yasaktır. Kural ihlali gönderiyi değil HESABI kaybettirir; "
        "paylaşmadan önce topluluğun kurallarını oku.",
        (),
    ),
    (
        "instagram facebook gönderi düzenleme",
        _M,
        "Yayınlanmış gönderiyi düzenlemek bildirimi geri almaz ve bazı alanlar "
        "(görsel, gönderi türü) hiç değiştirilemez. Yanlış yayın için düzenleme "
        "değil, kullanıcıya durumu bildirmek doğrudur.",
        (),
    ),
    # --- Ortak çalışma tuvalleri -------------------------------------------- #
    (
        "framer miro ortak tuval düzenleme",
        _M,
        "Ortak çalışma tuvalinde (Miro, Framer) yapılan değişiklik ANINDA herkese "
        "görünür ve başkasının işinin üstüne yazabilir. Var olan içeriği taşımadan "
        "ya da silmeden önce oku; kendi çalışman için ayrı bir alan/kopya aç.",
        (),
    ),
    # --- Agent temel sunucuları --------------------------------------------- #
    (
        "filesystem dosya sunucusu kullanma",
        _M,
        "Dosya sunucusu üzerinden silme ve üzerine yazma geri alınamaz ve izin "
        "verilen kökün dışına çıkma denemesi reddedilir. Yolu doğrula, silmeden "
        "önce listele, üzerine yazmadan önce oku.",
        (),
    ),
    (
        "memory kalıcı bellek yazma",
        _M,
        "Kalıcı belleğe yazılan bilgi sonraki oturumlarda DOĞRU KABUL EDİLİR. "
        "Doğrulanmamış varsayımı, geçici durumu ya da kişisel veriyi yazma; "
        "yanlış bir kayıt sessizce uzun süre yanlış yönlendirir.",
        (),
    ),
    (
        "time zaman sunucusu kullanma",
        _S,
        "Tarih/saat hesabını kendin uydurma; zaman sunucusundan al ve hangi saat "
        "diliminde çalıştığını açıkça yaz. 'Bugün' ve 'şimdi' kullanıcının "
        "diliminde farklı bir güne düşebilir.",
        (),
    ),
    # --- Kendi mağaza MCP'si ------------------------------------------------ #
    (
        "novamira wordpress woocommerce mağaza yönetimi",
        _M,
        "Kendi mağaza MCP'n üzerinden yapılan değişiklik CANLI mağazaya gider: "
        "fiyat, stok ve yayın durumu anında müşteriye görünür. Önce tek ürün "
        "üzerinde dene ve sonucu mağazadan okuyarak doğrula.",
        (),
    ),
    (
        "MCP aracında yol ve kimlik biçimi",
        _M,
        "Dosya/kaynak üreten MCP araçlarında yol biçimi (res:// gibi protokol öneki, "
        "göreli yol, mutlak yol) sunucudan sunucuya ve hatta AYNI sunucunun araçları "
        "arasında değişir. Ölçüldü: Godot MCP'de create_scene 'res://main.tscn' "
        "kabul ederken add_node aynı yolu 'dosya yok' diye reddetti. Hata alınca "
        "yolun DİĞER biçimini dene; aynı biçimde ısrar etme.",
        (),
    ),
    (
        "MCP aracında yol ve kimlik biçimi",
        _S,
        "Bir MCP aracı yolu/kimliği reddettiğinde sorun çoğu zaman YETENEK değil "
        "BİÇİMDİR. Aynı sunucuda işe yarayan başka bir çağrının kabul ettiği biçime "
        "bak ve onu kullan; aracın yapamadığına hükmetmeden önce biçimi ele.",
        (),
    ),
)

MEASURED_LESSONS: tuple[Lesson, ...] = tuple(
    Lesson(text=text, kind=kind, task=task, source=LessonSource.SEED)
    for task, kind, text in _MEASURED
)

WRITTEN_LESSONS: tuple[Lesson, ...] = tuple(
    Lesson(
        text=text,
        kind=kind,
        task=task,
        source=LessonSource.SEED,
        confidence=UNMEASURED_CONFIDENCE,
        tags=tags,
    )
    for task, kind, text, tags in _WRITTEN
)

SEED_LESSONS: tuple[Lesson, ...] = MEASURED_LESSONS + WRITTEN_LESSONS


def seed(memory: LessonMemory) -> int:
    """Küratörlü dersleri belleğe ekle (tekilleştirmeli). Eklenen YENİ ders sayısını döner."""
    return sum(1 for lesson in SEED_LESSONS if memory.add(lesson))
