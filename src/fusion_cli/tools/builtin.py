"""Yerleşik araçların kayıt defteri — şemaların tanımlandığı TEK yer.

Yeni bir araç eklemek: executor'ı ilgili modüle yaz, buraya bir `Tool` kaydı ekle.
Motor kodu, onay akışı ve render katmanı değişmez.

Açıklama metinleri modele yazılmıştır: aracın ne yaptığını değil, NE ZAMAN
seçileceğini anlatır. Model doğru aracı seçemezse en iyi executor bile işe yaramaz.
"""

from __future__ import annotations

from ..core.tools import Tool
from . import archive, browser, download, files, planning, scaffold_tool, search, shell, web
from .registry import ToolRegistry

#: JSON Schema parçası. İç içe geçtiği için değer tipi serbest bırakılır; bu yapı
#: modele olduğu gibi gönderilen bir sözlüktür, iş mantığı taşımaz.
SchemaFragment = dict[str, object]


def _schema(properties: dict[str, SchemaFragment], required: list[str]) -> SchemaFragment:
    return {"type": "object", "properties": properties, "required": required}


_STRING: SchemaFragment = {"type": "string"}
_INTEGER: SchemaFragment = {"type": "integer"}


def build_registry() -> ToolRegistry:
    """Yerleşik araçların tamamını içeren yeni bir kayıt defteri üret."""
    registry = ToolRegistry()
    for tool in _TOOLS:
        registry.register(tool)
    for alias, target in _ALIASES.items():
        registry.register_alias(alias, target)
    return registry


_TOOLS: tuple[Tool, ...] = (
    Tool(
        name="read_file",
        description="Bir dosyanın içeriğini satır numaralarıyla oku. Bir dosyayı "
        "değiştirmeden ÖNCE mutlaka oku; kör düzenleme yapma. Uzun dosya parça "
        "parça okunur: sonuç kesildiğini söylerse 'offset' ile DEVAM ET, aynı "
        "çağrıyı tekrarlama.",
        parameters=_schema(
            {
                "path": {**_STRING, "description": "Dosya yolu"},
                "offset": {
                    **_INTEGER,
                    "description": "Kaçıncı satırdan başlanacağı (1 tabanlı). "
                    "Kesilen bir okumaya devam etmek için kullanılır.",
                },
                "limit": {**_INTEGER, "description": "En fazla kaç satır okunacağı."},
            },
            ["path"],
        ),
        run=files.read_file,
    ),
    Tool(
        name="write_file",
        description="Bir dosyayı verilen içerikle oluştur ya da TAMAMEN üzerine yaz. "
        "Var olan dosyanın bir kısmını değiştireceksen bunu değil edit_file kullan. "
        "Var olan dosyada sonuç, eski içerikle farkı (diff) gösterir.",
        parameters=_schema(
            {
                # Açıklamada sıra vurgulanır: içerik büyükse model küçük alanı sona
                # bırakıp bazen hiç üretmiyor ve tur boşa gidiyor.
                "path": {
                    **_STRING,
                    "description": (
                        "Dosya yolu. Kısıtlı çalışma alanında proje köküne göreli yaz "
                        "(ör. index.html veya src/app.py); /index.html gibi / ile "
                        "başlayan yol işletim sisteminin köküdür ve reddedilir. "
                        "İLK bu alanı yaz."
                    ),
                },
                "content": {
                    **_STRING,
                    "description": "Dosyanın yeni tam içeriği. 'path' YAZILDIKTAN SONRA gelir.",
                },
            },
            ["path", "content"],
        ),
        run=files.write_file,
        mutating=True,
    ),
    Tool(
        name="edit_file",
        description="TERCİH EDİLEN kısmi düzenleme aracı. Önce read_file ile oku; "
        "sonra dosyadaki 'old' metnini 'new' ile değiştir. 'old' dosyadakiyle BİREBİR "
        "(girinti dahil) ve BENZERSİZ olmalı; değilse düzenleme reddedilir ve dosya "
        "değişmez. EKLEME yapıyorsan eklemenin yapılacağı yerdeki mevcut satırı 'old' "
        "olarak ver ve 'new' içinde o satırı AYNEN tekrar edip yeni kodu ekle. Tekrar "
        "eden bir metnin HEPSİNİ değiştireceksen replace_all: true kullan. Sonuç "
        "değişikliğin diff'ini döner: silinmesini istemediğin bir '-' satırı görürsen "
        "hemen geri ekle.",
        parameters=_schema(
            {
                "path": _STRING,
                "old": {**_STRING, "description": "Değiştirilecek mevcut metin"},
                "new": {**_STRING, "description": "Yeni metin"},
                "replace_all": {
                    "type": "boolean",
                    "description": "true ise tüm eşleşmeler değişir ve benzersizlik "
                    "aranmaz. Aynı metin dosyada çok kez geçiyorsa bunu kullanın.",
                },
            },
            ["path", "old", "new"],
        ),
        run=files.edit_file,
        mutating=True,
    ),
    Tool(
        name="multi_edit",
        description="Tek dosyada birden çok old→new değişikliğini SIRAYLA ve ATOMİK uygula "
        "(biri tutmazsa hiçbiri uygulanmaz). Aynı dosyada çok yer değişecekse bunu kullan.",
        parameters=_schema(
            {
                "path": _STRING,
                "edits": {
                    "type": "array",
                    "description": "[{'old': 'metin', 'new': 'yeni', 'replace_all': false}, …]",
                    "items": _schema(
                        {
                            "old": _STRING,
                            "new": _STRING,
                            "replace_all": {
                                "type": "boolean",
                                "description": "true ise bu düzenlemenin tüm "
                                "eşleşmeleri değişir ve benzersizlik aranmaz.",
                            },
                        },
                        ["old", "new"],
                    ),
                },
            },
            ["path", "edits"],
        ),
        run=files.multi_edit,
        mutating=True,
    ),
    Tool(
        name="scaffold_web",
        description="SIFIRDAN yeni bir web arayüzü kurarken kullan: hazır tasarım "
        "token'ları (tokens.css), test edilmiş biçimlendiriciler (format.js) ve doğru "
        "sıralı sayfa iskeletini (index.html) diske yazar. Var olan dosyayı EZMEZ; "
        "sonra bu dosyaları doldurursun. Dizinde zaten bir site varsa, var olan bir "
        "sayfayı düzeltiyorsan ya da belirli bir kaynağı (URL, tasarım) taklit "
        "ediyorsan bunu ÇAĞIRMA — önce list_dir/read_file ile ne olduğunu gör.",
        parameters=_schema({"path": {**_STRING, "description": "Hedef dizin (varsayılan: .)"}}, []),
        run=scaffold_tool.scaffold_web,
        mutating=True,
    ),
    Tool(
        name="list_dir",
        description="Bir dizindeki dosya ve klasörleri listele. Projeyi tanımak için "
        "önce bunu kullan, körlemesine dosya okuma.",
        parameters=_schema({"path": {**_STRING, "description": "Dizin yolu (varsayılan: .)"}}, []),
        run=files.list_dir,
    ),
    Tool(
        name="search_code",
        description="Bir dizinde metin/regex ara (grep gibi). KESİN bir metni ya da "
        "deseni ararken kullan.",
        parameters=_schema(
            {
                "pattern": {**_STRING, "description": "Aranacak metin veya regex"},
                "path": {**_STRING, "description": "Dizin/dosya (varsayılan: .)"},
            },
            ["pattern"],
        ),
        run=search.search_code,
    ),
    Tool(
        name="glob",
        description="Dosya adı deseniyle dosya bul (ör. '**/*.py'). Belirli tipteki "
        "dosyaları toplarken search_code'dan hızlıdır.",
        parameters=_schema(
            {
                "pattern": {**_STRING, "description": "glob deseni, ör. '**/*.py'"},
                "path": {**_STRING, "description": "kök dizin (varsayılan: .)"},
            },
            ["pattern"],
        ),
        run=search.glob_files,
    ),
    Tool(
        name="git",
        description="Salt-okunur git komutu çalıştır (status, diff, log, branch, show…). "
        "Onay gerektirmez. Commit/push gibi değiştirici git için run_shell kullan.",
        parameters=_schema(
            {
                "subcommand": {
                    **_STRING,
                    "description": "ör: 'status', 'diff', 'log --oneline -5'",
                }
            },
            ["subcommand"],
        ),
        run=shell.git,
    ),
    Tool(
        name="run_shell",
        description="Bir kabuk komutu çalıştır ve çıktısını al. Kod değiştirdiysen "
        "test/lint/build çalıştırarak işini DOĞRULA. Sürekli çalışan sunucuyu veya "
        "izleyiciyi ön planda başlatma; doğrulama için bitecek komut kullan. "
        "Değiştirici — onay gerekir.",
        parameters=_schema({"command": _STRING}, ["command"]),
        run=shell.run_shell,
        mutating=True,
    ),
    Tool(
        name="todo_write",
        description="Görev listesini TAMAMEN güncelle. Çok adımlı işlerde plan çıkar ve "
        "ilerledikçe güncelle (bir maddeyi in_progress yap, bitince completed). "
        "Basit tek adımlı işlerde kullanma.",
        parameters=_schema(
            {
                "todos": {
                    "type": "array",
                    "items": _schema(
                        {
                            "content": _STRING,
                            "status": {
                                **_STRING,
                                "enum": ["pending", "in_progress", "completed"],
                            },
                        },
                        ["content", "status"],
                    ),
                }
            },
            ["todos"],
        ),
        run=planning.todo_write,
    ),
    Tool(
        name="web_search",
        description="Web'de ara (ücretsiz, anahtarsız). Güncel bilgi, sürüm değişikliği "
        "ya da hata mesajı çözümü gerektiğinde kullan; ezberden emin konuşma.",
        parameters=_schema({"query": {**_STRING, "description": "arama sorgusu"}}, ["query"]),
        run=web.web_search,
    ),
    Tool(
        name="download_file",
        description="Kamuya açık bir URL'den gerçek dosyayı proje içine indir (en fazla 256 MiB). "
        "PNG/JPEG, ses, font ve ZIP assetleri için kullan; web_fetch ikili dosya kaydetmez. "
        "Mevcut dosyanın üzerine yazmaz. İndirmeden önce lisansı kaynak sayfasından doğrula; "
        "sonrasında ASSETS.json kaydını oluştur. Arşivleri kendiliğinden açmaz.",
        parameters=_schema({"url": _STRING, "path": _STRING}, ["url", "path"]),
        run=download.download_file,
        mutating=True,
    ),
    Tool(
        name="extract_archive",
        description="İndirilen ZIP/TAR arşivini proje içine aç. Asset paketleri sıkıştırılmış "
        "gelir; açmadan içindeki PNG/ses dosyalarına referans veremezsin. Arşiv dışına çıkan "
        "yol ve bağlantı içeren üyeler açılmaz. `dest` verilmezse arşivin bulunduğu dizine açar.",
        parameters=_schema(
            {
                "path": {**_STRING, "description": "Açılacak arşiv (proje içi yol)"},
                "dest": {**_STRING, "description": "Hedef dizin (varsayılan: arşivin dizini)"},
            },
            ["path"],
        ),
        run=archive.extract_archive,
        mutating=True,
    ),
    Tool(
        name="web_fetch",
        description="Bir URL'nin içeriğini çek ve metnini oku (HTML temizlenir). "
        "web_search sonucundaki bir sayfayı okumak için kullan. Form dolduramaz ve "
        "oturum açamaz; sayfa şifre/giriş arkasındaysa browser_open kullan.",
        parameters=_schema({"url": _STRING}, ["url"]),
        run=web.web_fetch,
    ),
    Tool(
        name="browser_open",
        description="Bir adresi GERÇEK tarayıcıda aç ve sayfanın görünür metnini oku. "
        "web_fetch'in yetmediği yerde kullan: şifre/giriş arkasındaki sayfa, "
        "JavaScript ile dolan içerik, tıklama gerektiren akış. Sayfa tur boyunca "
        "AÇIK kalır; sonraki browser_* çağrıları aynı sayfada çalışır. "
        "Bu araç dış adresler içindir; file://, localhost ve 127.0.0.1 adresleri "
        "güvenlik nedeniyle reddedilir. Yerel uygulamayı doğrulamak için projenin "
        "test/acceptance komutunu run_shell ile çalıştır.",
        parameters=_schema({"url": {**_STRING, "description": "Açılacak adres"}}, ["url"]),
        run=browser.browser_open,
    ),
    Tool(
        name="browser_read",
        description="Açık tarayıcı sayfasının GÜNCEL adresini, başlığını ve metnini oku. "
        "Bir tıklama/yazma sonrası sayfanın ne olduğunu görmek ve seçici doğrulamak "
        "için kullan.",
        parameters=_schema({}, []),
        run=browser.browser_read,
    ),
    Tool(
        name="browser_type",
        description="Açık sayfada bir alana metin yaz (CSS seçici ile). Şifre kutusu, "
        "arama alanı, form girdisi. submit: true verirsen ardından Enter'a basar. "
        "Değiştirici — gerçek dünyada etki yaratır, onay gerekir.",
        parameters=_schema(
            {
                "selector": {
                    **_STRING,
                    "description": "CSS seçici, ör. 'input[type=password]' veya '#Password'",
                },
                "text": {**_STRING, "description": "Alana yazılacak metin"},
                "submit": {
                    "type": "boolean",
                    "description": "true ise yazdıktan sonra Enter'a basar ve sayfayı bekler",
                },
            },
            ["selector", "text"],
        ),
        run=browser.browser_type,
        mutating=True,
    ),
    Tool(
        name="browser_click",
        description="Açık sayfada bir öğeye tıkla (CSS seçici ile). Değiştirici — "
        "tıklama geri alınamaz bir işlem başlatabilir, onay gerekir.",
        parameters=_schema(
            {
                "selector": {
                    **_STRING,
                    "description": "CSS seçici, ör. 'button[type=submit]' veya 'a.logo'",
                }
            },
            ["selector"],
        ),
        run=browser.browser_click,
        mutating=True,
    ),
    Tool(
        name="browser_screenshot",
        description="Açık sayfanın ekran görüntüsünü diske yaz. Bir siteyi taklit "
        "ederken yerleşimi metinden değil GÖRÜNTÜDEN anlarsın. Değiştirici (dosya yazar).",
        parameters=_schema(
            {
                "path": {**_STRING, "description": "Hedef dosya (varsayılan: ekran-goruntusu.png)"},
                "full_page": {
                    "type": "boolean",
                    "description": "false ise yalnızca görünen ekran alınır (varsayılan true)",
                },
            },
            [],
        ),
        run=browser.browser_screenshot,
        mutating=True,
    ),
    Tool(
        name="browser_mirror",
        description="Açık tarayıcı sayfasını YÜKLEDİĞİ kaynaklarla (CSS/JS/görsel/font) "
        "birlikte diske indir. Bir siteyi 'kopyalama' isteğinin karşılığı budur; "
        "şifre kapısını browser_type ile geçtiysen ayna da o oturumu görür. "
        "url verilmezse ETKİN sayfa aynalanır. Tek sayfa iner ve JavaScript ile "
        "çekilen veri yerelde çalışmaz — sonucu 'eksiksiz kopya' diye sunma. "
        "Değiştirici (çok sayıda dosya yazar).",
        parameters=_schema(
            {
                "path": {**_STRING, "description": "Hedef dizin (varsayılan: ayna)"},
                "url": {
                    **_STRING,
                    "description": "Aynalanacak adres. Boş bırakılırsa etkin sayfa.",
                },
            },
            [],
        ),
        run=browser.browser_mirror,
        mutating=True,
    ),
    Tool(
        name="browser_close",
        description="Tarayıcıyı kapat. İşin bittiyse çağır; tur sonunda motor da kapatır.",
        parameters=_schema({}, []),
        run=browser.browser_close,
    ),
)

#: Bazı modeller bu adları tercih eder; farklı isimlendirme alışkanlığı hataya dönüşmesin.
#
# Ölçüldü (6 Eylül canlı koşusu, `mevcut-projeye-uy`): model üç koşunun ikisinde
# `shell` çağırdı, "bilinmeyen araç" cevabını aldı ve o tur boşa gitti. Adın
# doğrusunu bilmemek bir yetenek eksikliği değil, isimlendirme tercihidir; kayıt
# defteri bunu kendi çözebiliyorken tura mal etmenin gerekçesi yok.
_ALIASES = {
    "view_file": "read_file",
    "grep_search": "search_code",
    "read_url_content": "web_fetch",
    "shell": "run_shell",
    "bash": "run_shell",
    "execute_command": "run_shell",
    "list_files": "list_dir",
    "create_file": "write_file",
}
