"""Ekran görüntüsü ve video karelerini piksel düzeyinde ölçen saf yardımcılar.

Denetçiler ajanın çıktısını Fusion'ın araçlarına bakmadan, yalnız piksellerden ölçer:
bir kare "boş" mu (varyans) ve iki kare birbirinden "farklı" mı (değişen piksel oranı).
Ağ ve tarayıcı yoktur; doğrudan test edilir.
"""

from __future__ import annotations

import io

from PIL import Image, ImageChops, ImageStat

#: Ölçüm öncesi görüntünün küçültüleceği genişlik. Büyük kareyi piksel piksel gezmek
#: yavaş; küçültme sprite boyutunu orantılı korur ve gürültüyü sönümler.
ANALYSIS_WIDTH = 200
#: Bir pikselin "değişti" sayılması için en büyük kanal farkı (0-255). Sıkıştırma
#: gürültüsünü (genelde <10) eler, gerçek hareketi (>50) yakalar.
PIXEL_DELTA = 24


def _decode(png: bytes) -> Image.Image:
    """PNG baytlarını küçültülmüş RGB görüntüye çevir."""
    with Image.open(io.BytesIO(png)) as source:
        image = source.convert("RGB")
    if image.width > ANALYSIS_WIDTH:
        height = max(1, round(image.height * ANALYSIS_WIDTH / image.width))
        image = image.resize((ANALYSIS_WIDTH, height), Image.Resampling.BILINEAR)
    return image


def luminance_variance(png: bytes) -> float:
    """Parlaklık varyansı; tek renkli (boş/siyah) karede sıfırdır."""
    gray = _decode(png).convert("L")
    return float(ImageStat.Stat(gray).var[0])


def changed_pixel_ratio(first_png: bytes, second_png: bytes) -> float:
    """İki kare arasında `PIXEL_DELTA`'dan çok değişen piksellerin oranı (0-1).

    Boyutlar farklıysa kareler farklı sayılır (1.0).
    """
    first = _decode(first_png)
    second = _decode(second_png)
    if first.size != second.size:
        return 1.0
    red, green, blue = ImageChops.difference(first, second).split()
    strongest = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    histogram = strongest.histogram()
    changed = sum(histogram[PIXEL_DELTA + 1 :])
    return changed / (first.width * first.height)
