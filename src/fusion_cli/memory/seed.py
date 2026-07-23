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
    )
)


def seed(memory: LessonMemory) -> int:
    """Küratörlü dersleri belleğe ekle (tekilleştirmeli). Eklenen YENİ ders sayısını döner."""
    return sum(1 for lesson in SEED_LESSONS if memory.add(lesson))
