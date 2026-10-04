"""İkinci kaynak mağaza: kopya kalitesinin tek siteye göre ayarlanmadığını sınar.

Kaynak sneaksup'tan farklı bir şablon, menü ve fiyat biçimi taşır ("9.290 TL",
kuruşsuz). Fusion'ın kendi ölçümü (site_design, 4 Ekim 2026) ana sayfada 24 ürün buldu;
eşik, ana sayfada görünmeyen ürünlerin kopyalanamayacağı düşünülerek yarısı alındı.
"""

from __future__ import annotations

from evals.kabul.areas.site_clone import make_area

SOURCE_URL = "https://www.desa.com.tr"
MIN_PRODUCTS = 12

AREA = make_area("site_kopyasi_2", SOURCE_URL, MIN_PRODUCTS)
