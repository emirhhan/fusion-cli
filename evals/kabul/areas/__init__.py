"""Kabul alanlarının kayıt defteri: alan adı → tanımını taşıyan modül.

Modüller tembel yüklenir; bir alanın bağımlılığı (ör. Playwright) eksikse diğer
alanlar yine çalışır.
"""

from __future__ import annotations

import importlib

from evals.kabul.model import Area

AREA_MODULES: dict[str, str] = {
    "site_kopyasi": "evals.kabul.areas.site_clone",
    "animasyon": "evals.kabul.areas.animation",
    "remotion": "evals.kabul.areas.remotion",
    "html_oyun": "evals.kabul.areas.html_game",
    "kendini_gelistirme": "evals.kabul.areas.self_improve",
    "tarayici": "evals.kabul.areas.browser",
}


def load_area(name: str) -> Area:
    """Alan tanımını yükle; bilinmeyen adda anlaşılır hata ver."""
    if name not in AREA_MODULES:
        raise KeyError(f"bilinmeyen alan: {name} (seçenekler: {', '.join(AREA_MODULES)})")
    area = importlib.import_module(AREA_MODULES[name]).AREA
    if not isinstance(area, Area):
        raise TypeError(f"{AREA_MODULES[name]}.AREA bir Area değil")
    return area
