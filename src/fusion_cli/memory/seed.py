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

SEED_LESSONS: tuple[Lesson, ...] = tuple(
    Lesson(text=text, kind=kind, task=task, source=LessonSource.SEED)
    for task, kind, text in (
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
)


def seed(memory: LessonMemory) -> int:
    """Küratörlü dersleri belleğe ekle (tekilleştirmeli). Eklenen YENİ ders sayısını döner."""
    return sum(1 for lesson in SEED_LESSONS if memory.add(lesson))
