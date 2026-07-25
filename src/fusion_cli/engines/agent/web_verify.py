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


def inspect_web_output(files: Mapping[str, str]) -> tuple[str, ...]:
    """Üretilen web dosyalarını denetle ve somut ihlalleri döndür.

    Saf fonksiyon: dosya adı → içerik girer, bulgu satırları çıkar. Ağ yok, disk yok.
    Her bulgu tek satırdır ve NE YAPILACAĞINI söyler; modele talimat olarak gider.
    """
    html = _birlestir(files, _HTML_SUFFIXES)
    if not html:
        return ()

    css = _birlestir(files, (".css",))
    js = _birlestir(files, (".js",))

    bulgular: list[str] = []
    bulgular.extend(_olu_gorseller(html))
    bulgular.extend(_bos_baglantilar(html))
    bulgular.extend(_eksik_main(html))
    bulgular.extend(_stilsiz_siniflar(html, css))
    bulgular.extend(_tutarsiz_tutarlar(html, js))
    bulgular.extend(_palet_baypasi(css, js, html))
    return tuple(bulgular)


def _birlestir(files: Mapping[str, str], suffixes: tuple[str, ...]) -> str:
    return "\n".join(
        icerik for ad, icerik in files.items() if ad.lower().endswith(suffixes)
    )


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
