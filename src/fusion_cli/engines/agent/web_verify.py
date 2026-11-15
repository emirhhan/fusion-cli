"""Web çıktısını mekanik olarak denetleyen kapı.

Neden var: ölçtük ki model, prompt'ta AÇIKÇA yasaklanan şeyleri yapıyor. Gerçek bir
koşuda kullanıcının isteğinde "bozuk görsel, boş bağlantı bulunmasın" yazmasına rağmen
model 12 kırık görsel ve 18 boş bağlantı üretti, sonra da "boş bağlantı yok" dedi.
Buna karşılık araç bir hata döndürdüğünde davranışını değiştirip düzeltti.

Sonuç: bu hataların yakalanacağı yer prompt değil, üretilen dosyayı gerçekten okuyup
somut ihlali geri veren deterministik bir kapıdır.

Kurallar dar tutulur. Her kural "nesnel olarak bozuk" olmalıdır — gürültülü bir kapı
hiç kapı olmamasından kötüdür, çünkü agent her turda boşuna düzeltme turu açar. Görsel
tasarım yargısı (hizalama, boşluk, renk uyumu) buraya GİRMEZ; o modelin işidir.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from html.parser import HTMLParser
from urllib.parse import unquote

from .web_images import empty_images
from .web_interactions import empty_form_actions, inert_buttons
from .web_motion import layout_animations, size_animations

#: Kapanmış ya da güvenilmez placeholder görsel servisleri. Model bunların öldüğünü
#: bilemez; eğitim verisinde çalışıyorlardı. Ağa çıkmadan, liste ile yakalanır.
DEAD_IMAGE_HOSTS = (
    "via.placeholder.com",
    "placeholder.com",
    "placehold.it",
    "lorempixel.com",
    "placeimg.com",
)

#: Stilsiz sınıf oranı bunun üstündeyse CSS, HTML'i takip etmemiş demektir.
#: Gerçek koşuda %70 ölçüldü; %30 sağlam bir eşik, küçük eksikleri kovalamaz.
UNSTYLED_RATIO_LIMIT = 30
#: Oran hesabının anlamlı olması için gereken en az sınıf sayısı.
MIN_CLASSES_FOR_RATIO = 5

_HTML_SUFFIXES = (".html", ".htm")


def inspect_web_output_by_severity(
    files: Mapping[str, str],
    context: Mapping[str, str] | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Web bulgularını blocking / warning / advisory olarak ayır.

    `files` bu turda dokunulan dosyalardır (anahtar: köke göreli yol); içerik
    kuralları yalnız onlara uygulanır. `context` DOKUNULMAYAN proje dosyalarıdır ve
    yalnız dosyalar-arası kurallar (bağlanmamış dosya, stilsiz sınıf) için okunur:
    tur `other.html` + `app.js` değiştirdiyse `app.js`'i bağlayan `index.html`
    dokunulmadığı için görünmüyor ve yanlış BLOCKING üretiliyordu (A4-07).

    Genel verifier kullanıcı prompt'unun tasarım niyetini bilmez. Bu yüzden yalnız
    tartışmasız çalışan-ürün hataları blocking'dir. Semantic ve tasarım tercihleri
    aynı düzeltici agent bütçesini tüketmez.
    """
    html = _birlestir(files, _HTML_SUFFIXES)
    if not html:
        return (), (), ()

    css = _birlestir(files, (".css",))
    # `.mjs`/`.cjs` de betiktir; yoksa bu dosyalara dayalı kurallar atlanıyordu (A4-64).
    js = _birlestir(files, (".js", ".mjs", ".cjs"))
    proje = {**(context or {}), **files}

    blocking: list[str] = []
    warnings: list[str] = []
    advisories: list[str] = []
    image_errors, image_warnings = empty_images(html, js)
    blocking.extend(image_errors)
    warnings.extend(image_warnings)

    # Kullanıcıya gerçekten bozuk/yanlış davranış teslim edenler.
    blocking.extend(_olu_gorseller(html))
    blocking.extend(_bos_baglantilar(html))
    blocking.extend(inert_buttons(html, js))
    blocking.extend(empty_form_actions(html, js))
    blocking.extend(
        _stilsiz_siniflar(html, _birlestir(proje, (".css",)), _birlestir(proje, _HTML_SUFFIXES))
    )
    blocking.extend(_tutarsiz_tutarlar(html, js))
    blocking.extend(
        _baglanmamis_dosyalar(
            files, _birlestir(proje, _HTML_SUFFIXES), _birlestir(proje, (".js", ".mjs", ".cjs"))
        )
    )
    blocking.extend(_kapanmayan_ham_metin_etiketleri(html))
    blocking.extend(_erisilemez_hp_dali(f"{html}\n{js}"))
    blocking.extend(layout_animations(f"{css}\n{html}"))

    # Semantic kalite: değerlidir ama proje bunun yüzünden "kırık" değildir.
    advisories.extend(_eksik_main(html))
    warnings.extend(size_animations(f"{css}\n{html}"))

    # Görsel/tasarım sistemi önerileri genel kapıda blocking olamaz.
    advisories.extend(_palet_baypasi(css, js, html))
    advisories.extend(_olcek_disi_bosluklar(css))

    return tuple(blocking), tuple(warnings), tuple(advisories)


def inspect_web_output(files: Mapping[str, str]) -> tuple[str, ...]:
    """Geriye uyumlu flat bulgu listesi.

    Eski testler ve dış çağıranlar bütün bulguları görmeye devam eder. Runtime karar
    vermek için `inspect_web_output_by_severity` kullanır.
    """
    blocking, warnings, advisories = inspect_web_output_by_severity(files)
    return (*blocking, *warnings, *advisories)


def _birlestir(files: Mapping[str, str], suffixes: tuple[str, ...]) -> str:
    return "\n".join(icerik for ad, icerik in files.items() if ad.lower().endswith(suffixes))


def _tam_belge(html: str) -> bool:
    """Bu bir tam sayfa mı, yoksa şablon parçası mı?

    `<body>` de sayfa göstergesidir: `<main>` sorgusu için yeterli.
    """
    return bool(re.search(r"<(?:html|head|body)[\s>]", html, re.I))


def _head_var(html: str) -> bool:
    """Belgede <head> var mı? `<script>`/`<link>` etiketleri oraya konur."""
    return bool(re.search(r"<(?:html|head)[\s>]", html, re.I))


def _olu_gorseller(html: str) -> list[str]:
    kaynaklar = re.findall(r"""<img[^>]*\ssrc=["']([^"']*)["']""", html, re.I)
    for host in DEAD_IMAGE_HOSTS:
        eslesen = [src for src in kaynaklar if host in src]
        if eslesen:
            return [
                f"{len(eslesen)} <img> etiketi kapanmış bir servise ({host}) işaret ediyor; "
                "sayfa kırık görsellerle açılır. Bunları inline SVG data URI ile değiştir "
                '(src="data:image/svg+xml;utf8,<svg …>").'
            ]
    return []


#: Bir `href="#"` bağlantısını meşru kılan öznitelikler: JS ile bağlanmış açılır menü, rol
#: verilmiş düğme, atla bağlantısı (A4-44).
_BAGLANTI_MESRULASTIRAN = ("onclick", "role", "data-", "aria-", "@click", "v-on", "x-on")


class _BosBaglantiSayaci(HTMLParser):
    """Gerçek `<a href="#">` etiketlerini sayar; yorum, `<pre>`, dize içindekilere bakmaz."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sayi = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        nitelikler = {ad.lower(): (deger or "") for ad, deger in attrs}
        if nitelikler.get("href", "").strip() != "#":
            return
        if any(ad.startswith(_BAGLANTI_MESRULASTIRAN) for ad in nitelikler):
            return
        self.sayi += 1


def _bos_baglantilar(html: str) -> list[str]:
    # Yalnızca href="#": href="#bolum" sayfa içi çapadır ve bozuk değildir.
    sayac = _BosBaglantiSayaci()
    sayac.feed(html)
    sayac.close()
    sayi = sayac.sayi
    if not sayi:
        return []
    return [
        f'{sayi} boş bağlantı var (href="#"): hiçbir yere gitmiyorlar. Gerçek bir hedef '
        "ver ya da bağlantı değil <button> kullan."
    ]


class _MainLandmarkParser(HTMLParser):
    """Narrow static landmark hint, not a CSS/ARIA accessibility-tree engine."""

    _NONRENDERED = frozenset(
        {"head", "script", "style", "template", "title", "meta", "link", "base"}
    )
    _VOID = frozenset(
        {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.found = False
        self._ancestors: list[tuple[str, bool]] = []
        self._open_positions: dict[str, list[int]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        style = attributes.get("style") or ""
        excluded = (
            (bool(self._ancestors) and self._ancestors[-1][1])
            or tag in self._NONRENDERED
            or "hidden" in attributes
            or "inert" in attributes
            or (attributes.get("aria-hidden") or "").strip().lower() == "true"
            or bool(
                re.search(
                    r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)\b", style, re.I
                )
            )
        )
        # Only unambiguous role markers: override roles remove implicit main.
        role = (attributes.get("role") or "").strip()
        if not excluded and (role == "main" or (tag == "main" and not role)):
            self.found = True
        if tag not in self._VOID:
            self._open_positions.setdefault(tag, []).append(len(self._ancestors))
            self._ancestors.append((tag, excluded))

    def handle_endtag(self, tag: str) -> None:
        positions = self._open_positions.get(tag)
        if not positions:
            return
        # Unknown closers are O(1); matching closers pop each open ancestor once
        # over the entire parse, including descendants closed by an ancestor tag.
        boundary = positions[-1]
        while len(self._ancestors) > boundary:
            closed_tag, _ = self._ancestors.pop()
            closed_positions = self._open_positions[closed_tag]
            closed_positions.pop()
            if not closed_positions:
                del self._open_positions[closed_tag]

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)


def _eksik_main(html: str) -> list[str]:
    if not _tam_belge(html):
        return []
    parser = _MainLandmarkParser()
    parser.feed(html)
    parser.close()
    if parser.found:
        return []
    return [
        "Ana içerik için <main> veya role=main landmark'ı eklemeyi değerlendirin; "
        "bu bir semantik gezinme önerisidir, tek başına WCAG ihlali değildir."
    ]


#: Sınıfları yerel CSS dışında bir yerden getiren çerçeveler: harici stylesheet
#: (Bootstrap/Bulma CDN) ve Tailwind (CDN betiği ya da derleme yönergeleri).
_HARICI_STYLESHEET = re.compile(
    r"<link\b(?=[^>]*\bstylesheet\b)[^>]*\bhref\s*=\s*[\"']?(?:https?:)?//", re.I
)
_CERCEVE_BETIGI = re.compile(
    r"<script\b[^>]*\bsrc\s*=\s*[\"']?(?:https?:)?//[^\"'>\s]*(?:tailwind|unocss|windi)", re.I
)
_CERCEVE_YONERGESI = re.compile(r"@tailwind\b|@apply\b|@import\s+[\"']tailwindcss", re.I)


def _siniflari_baska_yerden_gelir(html: str, css: str) -> bool:
    """Sınıflar yerel CSS'te değil CDN/derleme çerçevesinde tanımlı olabilir mi.

    Ölçüldü (29 Ekim): Bootstrap/Tailwind CDN + yerel `custom.css` olan sayfada
    çerçeve sınıfları 'stilsiz' sayılıp BLOCKING veriliyordu (A4-07c).
    """
    return bool(
        _HARICI_STYLESHEET.search(html)
        or _CERCEVE_BETIGI.search(html)
        or _CERCEVE_YONERGESI.search(css)
    )


def _stilsiz_siniflar(html: str, css: str, sayfalar: str = "") -> list[str]:
    # CSS dosyası hiç yoksa kontrol anlamsızdır: tek dosyalık sayfa ya da inline stil.
    if not css.strip() or _siniflari_baska_yerden_gelir(f"{html}\n{sayfalar}", css):
        return []
    kullanilan: set[str] = set()
    for oznitelik in re.findall(r'class="([^"]+)"', html):
        kullanilan.update(oznitelik.split())
    if len(kullanilan) < MIN_CLASSES_FOR_RATIO:
        return []

    tanimli = set(re.findall(r"\.([a-zA-Z][\w-]*)", css))
    stilsiz = sorted(kullanilan - tanimli)
    oran = 100 * len(stilsiz) // len(kullanilan)
    if oran <= UNSTYLED_RATIO_LIMIT:
        return []
    return [
        f"HTML'de kullanılan {len(kullanilan)} sınıfın {len(stilsiz)} tanesinin (%{oran}) "
        f"CSS'te hiç karşılığı yok; sayfa büyük ölçüde stilsiz görünür. Eksikler: "
        f"{', '.join(stilsiz[:8])}"
    ]


#: Sayfada vaat edilen para tutarı: "2.000 TL", "1.500 ₺". Binlik ayracı ZORUNLU —
#: "14 gün" gibi para olmayan sayılar ve tek haneli tutarlar elenir.
_AMOUNT = re.compile(r"\b(\d{1,3}(?:\.\d{3})+)\s*(?:TL|₺)", re.I)

#: Tutarın bir EŞİK/vaat olduğunu gösteren bağlam: "2.000 TL üzeri ücretsiz kargo".
#: Ürün fiyatı ("Kask 2.499 TL") kodda sabit olarak bulunmak zorunda değildir; ölçüldü
#: (29 Ekim): her ≥1.000 TL fiyat BLOCKING veriyordu (A4-06).
_ESIK_BAGLAMI = re.compile(
    r"üzeri|üstü|üzerindeki|ve\s+üzer|ücretsiz|bedava|kargo|eşik|esik|limit|en\s+az|minimum|sınır",
    re.I,
)


def _tutarsiz_tutarlar(html: str, js: str) -> list[str]:
    """Sayfanın metinde verdiği sözü kod tutuyor mu?

    Gerçek hata: üst çubukta "2.000 TL üzeri ücretsiz kargo" yazarken kod eşiği 200
    kullanıyordu. Kullanıcıya görünen vaat ile davranış çelişiyordu.

    Yalnızca eşik/vaat bağlamında (üzeri, ücretsiz kargo, limit…) geçen ve kodda HİÇ
    bulunmayan tutar bildirilir; ürün fiyatları kodda aranmaz.
    """
    if not js.strip():
        return []
    # Etiket sınırları satır sonu olur: bağlam komşu öğeye (ürün fiyatının yanındaki
    # kargo bandına) taşmasın, tutarın KENDİ öğesindeki metne bakılsın.
    satirlar = re.sub(r"<[^>]+>", "\n", html).splitlines()
    bulgular: list[str] = []
    gorulen: set[str] = set()
    for satir in satirlar:
        if not _ESIK_BAGLAMI.search(satir):
            continue
        for ham in _AMOUNT.findall(satir):
            if ham in gorulen:
                continue
            gorulen.add(ham)
            sayi = ham.replace(".", "")
            if re.search(rf"\b{sayi}\b", js):
                continue
            bulgular.append(
                f'Sayfada "{ham} TL" yazıyor ama bu tutar JavaScript kodunda hiç geçmiyor; '
                "kullanıcıya verilen söz ile kodun davranışı çelişiyor olabilir."
            )
    return bulgular


_HP_ZERO_GUARD = re.compile(r"\b(?P<receiver>[\w$]+(?:\.[\w$]+)*)\.hp\s*<=\s*0\b", re.I)


def _hp_azaltiliyor_mu(code: str, receiver: str) -> bool:
    """Aynı state alıcısının HP'sinde gerçek bir azaltma var mı?"""
    target = rf"\b{re.escape(receiver)}\.hp\b"
    if bool(
        re.search(rf"{target}\s*(?:-=|--)", code, re.I)
        or re.search(rf"--\s*{target}", code, re.I)
        or re.search(rf"{target}\s*\+=\s*-", code, re.I)
        or re.search(rf"{target}\s*=\s*[^;\n]*{target}\s*-", code, re.I)
    ):
        return True
    # Takma ad (`const p = state.player; p.hp -= 1`) ve hasar fonksiyonları (`takeDamage()`)
    # azaltmadır; yoksa BLOCKING yanlış pozitif üretiyordu (A4-45).
    for alias in re.findall(rf"\b([\w$]+)\s*=\s*{re.escape(receiver)}\s*[;,\n]", code):
        if alias != receiver and _hp_azaltiliyor_mu(code, alias):
            return True
    return bool(re.search(r"\b(?:take|apply|deal|inflict)Damage\s*\(|\bhurt\s*\(", code, re.I))


def _erisilemez_hp_dali(code: str) -> list[str]:
    """Her HP sıfır dalını aynı state alıcısının azaltmasıyla eşleştir.

    Küresel bir ``.hp -=`` kanıtı yeterli değildir: oyuncu hasarı çalışırken
    düşman hasarı tamamen eksik olabilir. Alıcıyı (``player``, ``enemy`` veya
    ``gameState.player``) korumak, bir entity'nin mutasyonunun ötekini gizlemesini
    engeller ve farklı adlarla yazılmış bağımsız state'leri karıştırmaz.
    """
    receivers = tuple(
        dict.fromkeys(match.group("receiver") for match in _HP_ZERO_GUARD.finditer(code))
    )
    missing = [receiver for receiver in receivers if not _hp_azaltiliyor_mu(code, receiver)]
    if not missing:
        return []
    targets = ", ".join(f"{receiver}.hp" for receiver in missing[:5])
    return [
        f"Kodda HP<=0 ölüm/bitiş kontrolü var ama {targets} değerini azaltan aynı-state "
        "mutasyonu yok; bu dal erişilemez. İlgili hasar olayında normal oyun "
        "state'indeki bu HP değerini gerçekten azalt."
    ]


def _kapanmayan_ham_metin_etiketleri(html: str) -> list[str]:
    """Kapanmayan ``style``/``script`` belgenin geri kalanını sessizce yutar."""
    bulgular: list[str] = []
    # HTML yorumundaki örnek kod "kapanmıyor" bulgusu üretmesin (A4-64).
    html = re.sub(r"<!--.*?-->", "", html, flags=re.DOTALL)
    baslangic = re.compile(r"<(style|script)\b[^>]*>", re.I)
    konum = 0
    while acilis := baslangic.search(html, konum):
        tag = acilis.group(1).lower()
        kapanis = re.search(rf"</{tag}\s*>", html[acilis.end() :], re.I)
        if kapanis is not None:
            # Ham metin içindeki '<script>' benzeri JavaScript/CSS stringlerini
            # yeni HTML etiketi sanma; gerçek kapanışın sonrasından devam et.
            konum = acilis.end() + kapanis.end()
            continue
        bulgular.append(
            f"<{tag}> etiketi kapanmıyor; tarayıcı belgenin kalanını ham metin "
            "sayabilir ve uygulama hiç başlamaz. "
            f"Eksik </{tag}> etiketini ekle."
        )
        break
    return bulgular


def _palet_baypasi(css: str, js: str, html: str) -> list[str]:
    """CSS'te palet tanımlıyken başka renklerin elle yazılması.

    Gerçek hata: `:root` içinde lacivert/turuncu palet duruyordu ama ürün kartlarını
    üreten JavaScript `#2563eb` kullanıyordu. Model "belirtilen paletle" diyordu;
    palet dosyadaydı ama arayüzde değildi.

    Yalnızca `:root` gerçekten bir palet tanımlıyorsa çalışır — yoksa neyin ihlal
    olduğu bilinemez. Nötr renkler (gri, siyah, beyaz) muaftır: gölge ve kenarlık
    renkleri marka paletiyle çelişmez.
    """
    kok = re.search(r":root\s*\{([^}]*)\}", css, re.I)
    if not kok:
        return []
    palet = {renk.lower() for renk in re.findall(r"#[0-9a-fA-F]{3,8}", kok.group(1))}
    if len(palet) < 2:
        return []

    disaridakiler: list[str] = []
    for kaynak in (js, html, css[kok.end() :]):
        for renk in re.findall(r"#[0-9a-fA-F]{6}\b", kaynak):
            dusuk = renk.lower()
            if dusuk in palet or _notr_mu(dusuk) or dusuk in disaridakiler:
                continue
            disaridakiler.append(dusuk)
    if not disaridakiler:
        return []
    return [
        f"CSS'te palet tanımlı ama {len(disaridakiler)} farklı renk paletin dışından "
        f"elle yazılmış: {', '.join(disaridakiler[:6])}. Bunları :root'taki değişkenlere "
        "bağla; aksi halde sayfa bildirilen paletle görünmez."
    ]


def _notr_mu(renk: str) -> bool:
    """Gri/siyah/beyaz mı? R, G ve B birbirine çok yakınsa nötr sayılır."""
    r, g, b = (int(renk[i : i + 2], 16) for i in (1, 3, 5))
    return max(r, g, b) - min(r, g, b) <= 24


_REFERANS = re.compile(r"""(?:src|href)\s*=\s*["']?([^"'\s>]+)""", re.I)
_MODUL_BELIRTECI = re.compile(r"""(?:import|require)\s*\(?[^;\n]*?["']([^"']+)["']""", re.I)


def _referans_yolu(ham: str) -> str:
    """Referansı karşılaştırılabilir biçime getir: sorgu/çapa ve başındaki ./ ../ / atılır."""
    yol = unquote(ham.split("#", 1)[0].split("?", 1)[0]).replace("\\", "/").lower()
    return yol.lstrip("./").removeprefix("/") if yol.startswith((".", "/")) else yol


def _yol_eslesir(dosya: str, referans: str) -> bool:
    """Köke göreli `dosya` yolu, HTML/JS'teki `referans` ile yol SONEKİ olarak eşleşir mi.

    Ad değil yol sonekine bakılır (A4-08): `a/app.js` referansı `b/app.js`'i bağlamaz.
    Referans daha uzunsa (`js/app.js` ya da CDN URL'si) dosya yolu onun soneki olmalıdır.
    """
    if not referans:
        return False
    return dosya == referans or dosya.endswith("/" + referans) or referans.endswith("/" + dosya)


def _baglanmamis_dosyalar(files: Mapping[str, str], html: str, js: str) -> list[str]:
    """Üretilen CSS/JS dosyası HTML'den referans ediliyor mu?

    Gerçek hata: düzeltici tur index.html'i yeniden yazarken <script src="script.js">
    etiketini düşürdü. JS hiç yüklenmedi, dinamik bölümlerin hepsi boş kaldı ve konsol
    TERTEMİZDİ — çalışan kod yoktu. Sayfa teknik olarak geçerliydi ve tamamen boştu.

    `html`/`js` PROJENİN tüm sayfaları/betikleridir (dokunulmayanlar dahil). Eşleme yol
    sonekiyledir: `./js/script.js` de geçerli bir referanstır.
    """
    if not _head_var(html):
        return []

    html_referanslari = [_referans_yolu(ham) for ham in _REFERANS.findall(html)]
    js_referanslari = [_referans_yolu(ham) for ham in _MODUL_BELIRTECI.findall(js)]
    bulgular: list[str] = []
    for ad in files:
        kucuk = ad.lower().replace("\\", "/")
        if not kucuk.endswith((".css", ".js")):
            continue
        if any(_yol_eslesir(kucuk, ref) for ref in html_referanslari):
            continue
        # Bir JS dosyası başka bir JS'ten import ediliyorsa BAĞLIDIR; modül grafiği
        # HTML'den geçmek zorunda değil (ES modülleri, yardımcı dosyalar).
        if kucuk.endswith(".js") and any(_yol_eslesir(kucuk, ref) for ref in js_referanslari):
            continue
        etiket = "<script src=…>" if kucuk.endswith(".js") else "<link rel=stylesheet>"
        bulgular.append(
            f"{ad} üretilmiş ama HTML'den hiç bağlanmamış: tarayıcı bu dosyayı hiç "
            f"yüklemiyor. HTML'e {etiket} etiketini ekle."
        )
    return bulgular


#: Boşluk taşıyan CSS özellikleri. Yalnızca bunlara bakılır: `border`, `outline`,
#: `font-size` gibi değerler ölçeğe uymak zorunda değildir.
_SPACING_PROPS = re.compile(
    r"\b(padding|margin|gap|row-gap|column-gap)(?:-(?:top|right|bottom|left|block|inline))?"
    r"\s*:\s*([^;}]+)",
    re.I,
)
#: 1-2px hairline/kenarlık payı boşluk sayılmaz.
_MIN_SPACING_PX = 3


def _ekle(bozuk: list[str], piksel: float, etiket: str) -> None:
    """4'ün katı değilse listeye ekle. 1-2px hairline payı boşluk sayılmaz."""
    if piksel < _MIN_SPACING_PX or piksel % 4 == 0 or etiket in bozuk:
        return
    bozuk.append(etiket)


def _olcek_disi_bosluklar(css: str) -> list[str]:
    """4'ün katı olmayan piksel boşlukları bildir.

    Model boşlukları göz kararı veriyor (13px, 17px, 42px) ve sayfa ritmi bozuluyor.
    Referanstaki ölçek tavsiyedir; ölçülebilir olduğu için zorunlu kılınabilir.

    `var()`, `rem`, `%`, `clamp()` gibi değerler ölçek dışı SAYILMAZ — zaten doğru
    yaklaşımdır ve piksel kuralına tabi değildir.
    """
    if not css.strip():
        return []
    bozuk: list[str] = []
    for _, deger in _SPACING_PROPS.findall(css):
        if "var(" in deger or "calc(" in deger or "clamp(" in deger:
            continue
        for sayi in re.findall(r"([\d.]+)px", deger):
            _ekle(bozuk, float(sayi), f"{sayi}px")
        # rem de piksel ölçeğine düşer: referans yokken model rem kullanıyor.
        for sayi in re.findall(r"([\d.]+)rem", deger):
            _ekle(bozuk, float(sayi) * 16, f"{sayi}rem")
    if not bozuk:
        return []
    return [
        f"{len(bozuk)} boşluk değeri 4'lük ölçeğin dışında: {', '.join(bozuk[:8])}. "
        "Boşlukları ölçeğe oturt (4, 8, 12, 16, 24, 32, 48, 64, 96) ya da "
        ":root'taki --space-* değişkenlerini kullan; göz kararı boşluk ritmi bozar."
    ]
