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
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    """Web bulgularını blocking / warning / advisory olarak ayır.

    Genel verifier kullanıcı prompt'unun tasarım niyetini bilmez. Bu yüzden yalnız
    tartışmasız çalışan-ürün hataları blocking'dir. Semantic ve tasarım tercihleri
    aynı düzeltici agent bütçesini tüketmez.
    """
    html = _birlestir(files, _HTML_SUFFIXES)
    if not html:
        return (), (), ()

    css = _birlestir(files, (".css",))
    js = _birlestir(files, (".js",))

    blocking: list[str] = []
    warnings: list[str] = []
    advisories: list[str] = []

    # Kullanıcıya gerçekten bozuk/yanlış davranış teslim edenler.
    blocking.extend(_olu_gorseller(html))
    blocking.extend(_bos_baglantilar(html))
    blocking.extend(_stilsiz_siniflar(html, css))
    blocking.extend(_tutarsiz_tutarlar(html, js))
    blocking.extend(_baglanmamis_dosyalar(files, html, js))
    blocking.extend(_kapanmayan_ham_metin_etiketleri(html))
    blocking.extend(_erisilemez_hp_dali(f"{html}\n{js}"))

    # Semantic kalite: değerlidir ama proje bunun yüzünden "kırık" değildir.
    warnings.extend(_eksik_main(html))

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
    kaynaklar = re.findall(r'<img[^>]*\ssrc="([^"]*)"', html, re.I)
    for host in DEAD_IMAGE_HOSTS:
        eslesen = [src for src in kaynaklar if host in src]
        if eslesen:
            return [
                f"{len(eslesen)} <img> etiketi kapanmış bir servise ({host}) işaret ediyor; "
                "sayfa kırık görsellerle açılır. Bunları inline SVG data URI ile değiştir "
                '(src="data:image/svg+xml;utf8,<svg …>").'
            ]
    return []


def _bos_baglantilar(html: str) -> list[str]:
    # Yalnızca href="#": href="#bolum" sayfa içi çapadır ve bozuk değildir.
    sayi = len(re.findall(r'href="#"', html, re.I))
    if not sayi:
        return []
    return [
        f'{sayi} boş bağlantı var (href="#"): hiçbir yere gitmiyorlar. Gerçek bir hedef '
        "ver ya da bağlantı değil <button> kullan."
    ]


def _eksik_main(html: str) -> list[str]:
    # Yalnızca TAM belgede anlamlı: bir şablon/bileşen parçasında <main> olmaz ve
    # orada aramak yanlış pozitif üretir (Django/Rails şablonları, e-posta parçaları).
    if not _tam_belge(html):
        return []
    if re.search(r"<main[\s>]", html, re.I):
        return []
    return ["Sayfanın ana içeriği <main> etiketiyle sarılmamış; semantic HTML eksik."]


def _stilsiz_siniflar(html: str, css: str) -> list[str]:
    # CSS dosyası hiç yoksa kontrol anlamsızdır: tek dosyalık sayfa ya da inline stil.
    if not css.strip():
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


def _tutarsiz_tutarlar(html: str, js: str) -> list[str]:
    """Sayfanın metinde verdiği sözü kod tutuyor mu?

    Gerçek hata: üst çubukta "2.000 TL üzeri ücretsiz kargo" yazarken kod eşiği 200
    kullanıyordu. Kullanıcıya görünen vaat ile davranış çelişiyordu.

    Yalnızca metinde geçen ve kodda HİÇ bulunmayan tutar bildirilir; bu güçlü bir
    sinyaldir, tahmin değil.
    """
    if not js.strip():
        return []
    metin = re.sub(r"<[^>]+>", " ", html)
    bulgular: list[str] = []
    for ham in dict.fromkeys(_AMOUNT.findall(metin)):
        sayi = ham.replace(".", "")
        if re.search(rf"\b{sayi}\b", js):
            continue
        bulgular.append(
            f'Sayfada "{ham} TL" yazıyor ama bu tutar JavaScript kodunda hiç geçmiyor; '
            "kullanıcıya verilen söz ile kodun davranışı çelişiyor olabilir."
        )
    return bulgular


_HP_ZERO_GUARD = re.compile(
    r"\b(?P<receiver>[\w$]+(?:\.[\w$]+)*)\.hp\s*<=\s*0\b", re.I
)


def _hp_azaltiliyor_mu(code: str, receiver: str) -> bool:
    """Aynı state alıcısının HP'sinde gerçek bir azaltma var mı?"""
    target = rf"\b{re.escape(receiver)}\.hp\b"
    return bool(
        re.search(rf"{target}\s*(?:-=|--)", code, re.I)
        or re.search(rf"--\s*{target}", code, re.I)
        or re.search(rf"{target}\s*=\s*[^;\n]*{target}\s*-", code, re.I)
    )


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


def _baglanmamis_dosyalar(files: Mapping[str, str], html: str, js: str) -> list[str]:
    """Üretilen CSS/JS dosyası HTML'den referans ediliyor mu?

    Gerçek hata: düzeltici tur index.html'i yeniden yazarken <script src="script.js">
    etiketini düşürdü. JS hiç yüklenmedi, dinamik bölümlerin hepsi boş kaldı ve konsol
    TERTEMİZDİ — çalışan kod yoktu. Sayfa teknik olarak geçerliydi ve tamamen boştu.

    Yol değil DOSYA ADI aranır: `./js/script.js` de geçerli bir referanstır.
    """
    if not _head_var(html):
        return []

    bulgular: list[str] = []
    for ad in files:
        if not ad.lower().endswith((".css", ".js")):
            continue
        if re.search(rf'(?:src|href)\s*=\s*["\'][^"\']*{re.escape(ad)}', html, re.I):
            continue
        # Bir JS dosyası başka bir JS'ten import ediliyorsa BAĞLIDIR; modül grafiği
        # HTML'den geçmek zorunda değil (ES modülleri, yardımcı dosyalar).
        if ad.lower().endswith(".js") and re.search(
            rf'(?:import|require)\s*\(?[^;\n]*["\'][^"\']*{re.escape(ad)}', js, re.I
        ):
            continue
        etiket = "<script src=…>" if ad.lower().endswith(".js") else "<link rel=stylesheet>"
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
