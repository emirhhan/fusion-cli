"""Kendini geliştirme döngüsünün ölçüm izi — tek, eklemeli JSONL dosyası.

Döngünün işe yarayıp yaramadığı sayılarla sorulabilsin diye her halka buraya bir satır
bırakır: kaç taslak üretildi, hangi öneri hangi optimizasyon/ayrı küme skoruyla çıktı.
Satırlar yalnız sayı, kimlik ve küme adı taşır; istek ya da istem metni YAZILMAZ.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

_LOG = logging.getLogger(__name__)

#: Olay adları (kayıt dosyasını okuyan araçlar bunlara bakar).
OLAY_TASLAK_URETILDI = "taslak_uretildi"
OLAY_TASLAK_KABUL = "taslak_kabul"
OLAY_TASLAK_SILINDI = "taslak_silindi"
OLAY_ONERI = "oneri"
OLAY_ONERI_UYGULANDI = "oneri_uygulandi"
OLAY_ONERI_GERI_ALINDI = "oneri_geri_alindi"


def kayit_ekle(yol: Path, olay: str, alanlar: Mapping[str, object], *, simdi: float) -> None:
    """Kayıt dosyasına bir satır ekle. Yazılamazsa akış düşmez; uyarı log'lanır."""

    satir = {
        "zaman": datetime.fromtimestamp(simdi, tz=UTC).isoformat(timespec="seconds"),
        "olay": olay,
        **alanlar,
    }
    try:
        yol.parent.mkdir(parents=True, exist_ok=True)
        with yol.open("a", encoding="utf-8") as akim:
            akim.write(json.dumps(satir, ensure_ascii=False) + "\n")
    except OSError as hata:
        _LOG.warning("döngü kaydı yazılamadı", extra={"yol": str(yol), "hata": str(hata)})


def kayitlari_oku(yol: Path) -> list[dict[str, object]]:
    """Kayıt dosyasının satırları (eskiden yeniye); bozuk satır atlanır."""

    try:
        satirlar = yol.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    kayitlar: list[dict[str, object]] = []
    for satir in satirlar:
        try:
            nesne = json.loads(satir)
        except json.JSONDecodeError:
            continue
        if isinstance(nesne, dict):
            kayitlar.append(nesne)
    return kayitlar
