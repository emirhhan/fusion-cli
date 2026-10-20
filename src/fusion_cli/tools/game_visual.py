"""Oyunun ekran görüntülerinden ölçülen görsel kusurlar.

Ölçüldü (6 Ekim 2026, dalga24 "zor oyun"): denetçi 8'de 7 verdi, kullanıcı oyunu açınca
"rezalet" dedi. Ekran görüntüsünde oyun alanı yalnız sol üst çeyrekti (gerisi açık bir
ızgara), oyuncu silinmeyen iz bırakıyordu, 6 sn'de hiç düşman çıkmadı ve skor yazısı
açık zeminde okunmuyordu. Kod ölçümü (konsol, rAF, durum kancası) bunların hiçbirini
görmez; bir insan ekrana bakınca hemen görür. Bu modül o bakışın ölçülebilen kısmıdır.

Eşikler bilerek kaba: amaç güzelliği puanlamak değil, apaçık bozuk görüntüyü yakalamak.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from itertools import pairwise

from PIL import Image, ImageChops, ImageStat

#: Analiz genişliği (px): küçültme gürültüyü sönümler ve ölçümü hızlandırır.
ANALYSIS_WIDTH = 240
#: Bir pikselin "değişti" sayılması için en büyük kanal farkı (0-255).
PIXEL_DELTA = 30
#: Düz renk sayılan bölgenin en büyük parlaklık sapması.
FLAT_STDDEV = 4.0
#: Düz bölgenin geri kalan ekrandan ayrılması için gereken parlaklık farkı.
FILL_MISMATCH = 70.0
#: İz: son karede değişen alan ilk adımdakinin en az bu katı ve değişenlerin bu oranı kalıcı.
TRAIL_GROWTH = 3.0
TRAIL_PERSISTENCE = 0.85
#: Hareketsizlik: tuşa basılmadan değişen piksel oranı bunun altında. Küçük ama gerçek
#: hareket (yavaş düşman, küçük sprite) ~0,0005 ölçüldü; bozuk oyunda tam sıfırdır.
IDLE_MIN_CHANGE = 0.0002
#: Okunur yazı için en düşük kontrast oranı (WCAG büyük metin eşiği).
MIN_HUD_CONTRAST = 3.0


def _decode(png: bytes) -> Image.Image:
    with Image.open(io.BytesIO(png)) as source:
        image = source.convert("RGB")
    if image.width > ANALYSIS_WIDTH:
        height = max(1, round(image.height * ANALYSIS_WIDTH / image.width))
        image = image.resize((ANALYSIS_WIDTH, height), Image.Resampling.BILINEAR)
    return image


def _changed_mask(first: Image.Image, second: Image.Image) -> Image.Image:
    red, green, blue = ImageChops.difference(first, second).split()
    strongest = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    return strongest.point(lambda value: 255 if value > PIXEL_DELTA else 0)


def _count(mask: Image.Image) -> int:
    return mask.histogram()[255]


def partial_fill_problem(png: bytes) -> str | None:
    """Ekranın bir çeyreği düz renk ve geri kalanından keskin biçimde ayrı mı?

    Canvas boyutu/ölçeği yanlışsa oyun alanı ekranın bir köşesine sıkışır, kalan alan
    başka bir zemin (ya da sayfa arka planı) gösterir.
    """
    image = _decode(png).convert("L")
    w, h = image.size
    # Kenarlardan pay bırakılır: küçültme sınırda iki zemini karıştırır.
    px, py = w // 20, h // 20
    ceyrekler = [
        image.crop((x + px, y + py, x + w // 2 - px, y + h // 2 - py))
        for y in (0, h // 2)
        for x in (0, w // 2)
    ]
    istatistik = [ImageStat.Stat(c) for c in ceyrekler]
    ortalamalar = [s.mean[0] for s in istatistik]
    for indeks, stat in enumerate(istatistik):
        digerleri = [m for i, m in enumerate(ortalamalar) if i != indeks]
        if stat.stddev[0] < FLAT_STDDEV and all(
            abs(stat.mean[0] - m) > FILL_MISMATCH for m in digerleri
        ):
            return (
                "oyun alanı ekranın tamamını kaplamıyor: bir çeyrek düz renkte ve ekranın "
                "geri kalanından tamamen farklı (canvas genişlik/yükseklik ya da "
                "devicePixelRatio ölçeği yanlış; çizim alanı pencereyle aynı boyda olmalı)"
            )
    return None


def trail_problem(frames: Sequence[bytes]) -> str | None:
    """Hareket sırasında değişen pikseller kalıcı mı ve alan sürekli büyüyor mu?

    Her karede ekran temizlenmezse hareket eden nesne arkasında iz bırakır: ilk kareye
    göre değişen alan adım adım büyür ve bir kez değişen piksel bir daha geri dönmez.
    """
    if len(frames) < 3:
        return None
    images = [_decode(frame) for frame in frames]
    if any(image.size != images[0].size for image in images):
        return None
    masks = [_changed_mask(images[0], image) for image in images[1:]]
    alanlar = [_count(mask) for mask in masks]
    if alanlar[0] == 0 or alanlar[-1] < TRAIL_GROWTH * alanlar[0]:
        return None
    kalici = [
        _count(ImageChops.multiply(onceki, sonraki)) / max(1, _count(onceki))
        for onceki, sonraki in pairwise(masks)
    ]
    if min(kalici) < TRAIL_PERSISTENCE:
        return None
    return (
        "hareket eden nesneler iz bırakıyor: ekran her karede temizlenmiyor "
        "(her karenin başında ctx.clearRect/fillRect ile tüm canvas'ı boya)"
    )


def idle_motion_problem(frames: Sequence[bytes]) -> str | None:
    """Tuşa basılmadan hiçbir şey kıpırdamıyor mu (düşman, mermi, efekt yok)?"""
    if len(frames) < 2:
        return None
    images = [_decode(frame) for frame in frames]
    if any(image.size != images[0].size for image in images):
        return None
    toplam = images[0].width * images[0].height
    en_cok = max(_count(_changed_mask(images[0], image)) for image in images[1:]) / toplam
    if en_cok >= IDLE_MIN_CHANGE:
        return None
    return (
        "oyunda kendiliğinden hareket eden hiçbir şey yok: tuşa basılmadan birkaç saniye "
        "boyunca ekran hiç değişmedi (düşman doğmuyor ya da çizilmiyor)"
    )


def _relative_luminance(rgb: Sequence[float]) -> float:
    def kanal(value: float) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (kanal(v) for v in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(first: Sequence[float], second: Sequence[float]) -> float:
    """WCAG kontrast oranı (1-21)."""
    a, b = sorted((_relative_luminance(first), _relative_luminance(second)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def background_under(png: bytes, box: tuple[float, float, float, float]) -> tuple[float, ...]:
    """Kutunun hemen çevresindeki zeminin ortanca rengi (yazının kendisi hariç)."""
    with Image.open(io.BytesIO(png)) as source:
        image = source.convert("RGB")
    x, y, w, h = box
    pay = max(4.0, h / 2)
    cerceve = image.crop(
        (
            max(0, int(x - pay)),
            max(0, int(y - pay)),
            min(image.width, int(x + w + pay)),
            min(image.height, int(y + h + pay)),
        )
    )
    return tuple(ImageStat.Stat(cerceve).median)
