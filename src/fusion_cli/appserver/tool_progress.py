"""Bir araç BAŞLARKEN kullanıcıya gösterilecek şimdiki-zamanlı, tek cümlelik Türkçe metin.

Claude'daki gibi: model düşünürken ve araç çalışırken sohbette soluk, tek satırlık
bir durum yazısı görünür ("read_file ile src/app.py okunuyor", "web_search ile
'x' aranıyor"). Motor `ToolStarted` olayını araç çalışmadan hemen önce yayınlar
(bkz. `engines/agent/loop.py::_execute`); bu modül o olayın (`name`, `args`)
alanlarını TEK bir insan cümlesine çevirir. Arayüz kendi kalıbını uydurmaz — tek
kaynak burasıdır (RULES: "aynı işi yapan ikinci bir yol açılmaz").

`chrome_feed.py::step_text` ile KARIŞTIRILMAZ: o modül yalnız `chrome_*`
araçlarını, BİTMİŞ zamanda ("tıklandı") Chrome yan paneli için anlatır. Burası
TÜM araçları, ŞİMDİKİ zamanda ("tıklanıyor") ana sohbet akışı için anlatır.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from urllib.parse import urlsplit

#: Argümandan alınan metinlerin üst sınırı; durum satırı tek satırda kalmalı.
_MAX_QUOTE = 60


def _text(args: Mapping[str, object], *keys: str) -> str | None:
    """Verilen anahtarlardan ilk dolu metin değerini döndür."""
    for key in keys:
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _quote(value: str | None) -> str:
    if not value:
        return ""
    kirpik = value if len(value) <= _MAX_QUOTE else f"{value[: _MAX_QUOTE - 1]}…"
    return f"'{kirpik}'"


def _host(url: str | None) -> str:
    if not url:
        return "sayfa"
    try:
        parsed = urlsplit(url if "://" in url else f"https://{url}")
    except ValueError:
        return url
    return parsed.netloc or url


def _path_metni(args: Mapping[str, object]) -> str:
    yol = _text(args, "path", "yol")
    return yol or "dosya"


def _read_file(args: Mapping[str, object]) -> str:
    return f"{_path_metni(args)} okunuyor"


def _write_file(args: Mapping[str, object]) -> str:
    return f"{_path_metni(args)} yazılıyor"


def _edit_file(args: Mapping[str, object]) -> str:
    return f"{_path_metni(args)} düzenleniyor"


def _list_dir(args: Mapping[str, object]) -> str:
    yol = _text(args, "path", "yol")
    return f"{yol} listeleniyor" if yol else "dizin listeleniyor"


def _search_code(args: Mapping[str, object]) -> str:
    sorgu = _text(args, "query", "pattern", "sorgu")
    return f"{_quote(sorgu)} kod içinde aranıyor" if sorgu else "kod içinde arama yapılıyor"


def _glob(args: Mapping[str, object]) -> str:
    desen = _text(args, "pattern", "desen")
    return f"{_quote(desen)} desenine uyan dosyalar bulunuyor" if desen else "dosyalar bulunuyor"


def _git(args: Mapping[str, object]) -> str:
    # Araç şeması alanı `subcommand`dır (bkz. `tools/builtin.py`, ör: "status").
    alt_komut = _text(args, "subcommand", "komut")
    return f"git {alt_komut} çalıştırılıyor" if alt_komut else "git komutu çalıştırılıyor"


def _run_shell(args: Mapping[str, object]) -> str:
    komut = _text(args, "command", "komut")
    if not komut:
        return "kabuk komutu çalıştırılıyor"
    return f"kabuk komutu {_quote(komut)} çalıştırılıyor"


def _todo_write(_args: Mapping[str, object]) -> str:
    return "görev listesi güncelleniyor"


def _web_search(args: Mapping[str, object]) -> str:
    sorgu = _text(args, "query", "sorgu")
    return f"{_quote(sorgu)} web'de aranıyor" if sorgu else "web'de arama yapılıyor"


def _web_fetch(args: Mapping[str, object]) -> str:
    url = _text(args, "url")
    return f"{_host(url)} getiriliyor" if url else "sayfa getiriliyor"


def _download_file(args: Mapping[str, object]) -> str:
    url = _text(args, "url")
    return f"{_host(url)} indiriliyor" if url else "dosya indiriliyor"


def _site_crawl(args: Mapping[str, object]) -> str:
    url = _text(args, "url")
    return f"{_host(url)} taranıyor" if url else "site taranıyor"


def _generate_image(args: Mapping[str, object]) -> str:
    genislik, yukseklik = args.get("width"), args.get("height")
    olcu = f" ({genislik}×{yukseklik})" if genislik and yukseklik else ""
    return f"{_path_metni(args)} görseli üretiliyor{olcu}"


def _optimize_image(args: Mapping[str, object]) -> str:
    return f"{_path_metni(args)} web için hazırlanıyor"


def _spawn_agents(args: Mapping[str, object]) -> str:
    gorevler = args.get("gorevler")
    adet = len(gorevler) if isinstance(gorevler, list) else 0
    return f"{adet} ajan görevlendiriliyor" if adet else "ekip görevlendiriliyor"


def _extract_archive(args: Mapping[str, object]) -> str:
    return f"{_path_metni(args)} açılıyor"


def _scaffold_web(_args: Mapping[str, object]) -> str:
    return "web iskeleti oluşturuluyor"


def _chrome_navigate(args: Mapping[str, object]) -> str:
    return f"chrome ile {_host(_text(args, 'url'))} açılıyor"


def _chrome_click(_args: Mapping[str, object]) -> str:
    return "chrome ile bir öğeye tıklanıyor"


def _chrome_type(args: Mapping[str, object]) -> str:
    metin = _text(args, "text")
    return f"chrome ile {_quote(metin)} yazılıyor" if metin else "chrome ile yazı yazılıyor"


def _chrome_page(_args: Mapping[str, object]) -> str:
    return "chrome ile sayfa okunuyor"


def _chrome_action(args: Mapping[str, object]) -> str:
    action = args.get("action")
    if action == "scroll":
        return "chrome ile sayfa kaydırılıyor"
    if action == "wait":
        return "chrome ile bekleniyor"
    if action == "key":
        return "chrome ile tuşa basılıyor"
    if action == "screenshot":
        return "chrome ile ekran görüntüsü alınıyor"
    return "chrome ile sayfa etkileşimi yapılıyor"


def _browser_generic(fiil: str) -> Callable[[Mapping[str, object]], str]:
    def _metin(_args: Mapping[str, object]) -> str:
        return f"tarayıcı ile {fiil}"

    return _metin


def _browser_open(args: Mapping[str, object]) -> str:
    url = _text(args, "url")
    return f"tarayıcı ile {_host(url)} açılıyor" if url else "tarayıcı açılıyor"


def _desktop_open(args: Mapping[str, object]) -> str:
    hedef = _text(args, "path", "uygulama", "app")
    return f"masaüstünde {hedef} açılıyor" if hedef else "masaüstünde uygulama açılıyor"


def _desktop_generic(fiil: str) -> Callable[[Mapping[str, object]], str]:
    def _metin(_args: Mapping[str, object]) -> str:
        return f"masaüstünde {fiil}"

    return _metin


#: Araç adından şimdiki-zamanlı Türkçe cümleye eşleme. Yeni bir araç eklemek
#: burada bir satır demektir; eşlenmemiş araç `_varsayilan` ile karşılanır.
_METINLER: dict[str, Callable[[Mapping[str, object]], str]] = {
    "read_file": _read_file,
    "write_file": _write_file,
    "edit_file": _edit_file,
    "multi_edit": _edit_file,
    "list_dir": _list_dir,
    "search_code": _search_code,
    "glob": _glob,
    "git": _git,
    "run_shell": _run_shell,
    "todo_write": _todo_write,
    "web_search": _web_search,
    "web_fetch": _web_fetch,
    "download_file": _download_file,
    "site_crawl": _site_crawl,
    "generate_image": _generate_image,
    "optimize_image": _optimize_image,
    "spawn_agents": _spawn_agents,
    "extract_archive": _extract_archive,
    "scaffold_web": _scaffold_web,
    "chrome_navigate": _chrome_navigate,
    "chrome_click": _chrome_click,
    "chrome_type": _chrome_type,
    "chrome_page": _chrome_page,
    "chrome_action": _chrome_action,
    "browser_open": _browser_open,
    "browser_read": _browser_generic("sayfa okunuyor"),
    "browser_tabs_list": _browser_generic("sekmeler listeleniyor"),
    "browser_tab_select": _browser_generic("sekme seçiliyor"),
    "browser_tab_open": _browser_generic("yeni sekme açılıyor"),
    "browser_type": _browser_generic("yazı yazılıyor"),
    "browser_click": _browser_generic("bir öğeye tıklanıyor"),
    "browser_screenshot": _browser_generic("ekran görüntüsü alınıyor"),
    "browser_mirror": _browser_generic("ekran yansıtılıyor"),
    "browser_close": _browser_generic("tarayıcı kapatılıyor"),
    "desktop_windows": _desktop_generic("pencereler listeleniyor"),
    "desktop_window_focus": _desktop_generic("pencereye geçiliyor"),
    "desktop_accessibility": _desktop_generic("erişilebilirlik ağacı okunuyor"),
    "desktop_apps": _desktop_generic("uygulamalar listeleniyor"),
    "desktop_open": _desktop_open,
    "desktop_screenshot": _desktop_generic("ekran görüntüsü alınıyor"),
    "desktop_click": _desktop_generic("bir öğeye tıklanıyor"),
    "desktop_type": _desktop_generic("yazı yazılıyor"),
    "desktop_key": _desktop_generic("tuşa basılıyor"),
    "desktop_scroll": _desktop_generic("sayfa kaydırılıyor"),
}


def progress_text(name: str, args: Mapping[str, object]) -> str:
    """`ToolStarted` olayı için şimdiki-zamanlı, tek satırlık Türkçe cümle.

    Eşlenmemiş (örn. bir MCP sunucusunun aracı) bir isim için jenerik ama yine
    de anlaşılır bir varsayılana düşer: ham İngilizce araç adını kullanıcıya
    hiç göstermemek yerine, en azından "ne yapıldığı" belli bir cümle kurar.
    """
    olustur = _METINLER.get(name)
    if olustur is not None:
        return olustur(args)
    okunabilir_ad = name.replace("_", " ").strip() or "araç"
    return f"{okunabilir_ad} çalıştırılıyor"
