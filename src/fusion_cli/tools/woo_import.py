"""`urunler.json` kataloğunu WooCommerce ürünlerine aktar (model yazmaz).

Ölçüldü (17. kabul koşusu): model katalog dosyasını elle yeniden yazdı, yanlış
kategori ve boş görsel alanı bıraktı, sonra 27 ardışık düzenlemeyle onarmaya
çalıştı; mağazada yine 4 ürün göründü. Aktarma test edilmiş bir PHP betiğiyle
yapılır: basit ürün, fiyat, kategori ve yerel görsel. Aynı adlı ürün atlanır.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .wordpress_setup import run_wp

IMPORT_SCRIPT = Path(__file__).with_name("assets") / "woo_import.php"


@dataclass(frozen=True, slots=True)
class ImportResult:
    added: int
    skipped: int
    without_image: int
    error: str = ""


def parse_import_output(output: str) -> ImportResult:
    """Betiğin son satırındaki JSON'u oku; okunamıyorsa hata metniyle döner."""
    for satir in reversed(output.splitlines()):
        try:
            veri = json.loads(satir)
        except ValueError:
            continue
        if isinstance(veri, dict):
            return ImportResult(
                added=int(veri.get("eklenen", 0)),
                skipped=int(veri.get("atlanan", 0)),
                without_image=int(veri.get("gorselsiz", 0)),
                error=str(veri.get("hata", "")),
            )
    return ImportResult(0, 0, 0, error=output[-400:] or "betik çıktı vermedi")


async def import_products(root: Path, catalog: Path, wp_cli: str) -> ImportResult:
    """Kataloğu `wp eval-file` ile içe aktar."""
    code, output = await run_wp(
        wp_cli, root, "eval-file", str(IMPORT_SCRIPT), str(catalog), str(root)
    )
    sonuc = parse_import_output(output)
    if code != 0 and not sonuc.error:
        return ImportResult(sonuc.added, sonuc.skipped, sonuc.without_image, output[-400:])
    return sonuc
