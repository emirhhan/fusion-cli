"""`fusion update` ve `fusion uninstall` — bakım yönlendirmesi.

Fusion kendi kendini kaldırmaz: çalışan bir sürecin kendi dosyalarını silmesi
platforma göre farklı biçimlerde başarısız olur ve yarım kaldığında kullanıcı elinde
bozuk bir kurulumla kalır. Bunun yerine kurulum YÖNTEMİ tespit edilir ve doğru komut
gösterilir. Güncelleme ise Claude Code gibi gerçekten yapılır: iş paket yöneticisinin
ayrı sürecine devredilir (bkz. `self_update`).

Kullanıcı verisi (anahtarlar, yapılandırma, öğrenilen dersler) kaldırmayla
SİLİNMEZ. Aracı kaldırmak "verilerimi de sil" demek değildir; silmek ayrı ve
AÇIK bir karardır (`--purge`).
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path, PurePath

from ..config.paths import memory_dir, user_config_dir
from ..install import InstallMethod, detect_method, uninstall_command, update_command


def current_method() -> InstallMethod:
    """Bu Fusion'ın nasıl kurulduğu."""
    return detect_method(PurePath(sys.executable))


def update_instructions() -> str:
    """Güncelleme için gösterilecek metin."""
    return update_command(current_method())


def uninstall_instructions() -> str:
    """Kaldırma için gösterilecek metin."""
    return uninstall_command(current_method())


@dataclass(frozen=True, slots=True)
class PurgeResult:
    """Silme sonucu: silinenler ve silinemeyenler (sebebiyle) AYRI raporlanır."""

    removed: tuple[Path, ...] = ()
    failed: tuple[tuple[Path, str], ...] = ()


def purge_targets() -> tuple[Path, ...]:
    """Silinecek (var olan) kullanıcı dizinleri. Hiçbir şey silmez; onay ekranı bunu gösterir."""
    return tuple(yol for yol in (user_config_dir(), memory_dir()) if yol.exists())


def purge_user_data_report(*, dry_run: bool) -> PurgeResult:
    """Kullanıcı verisini sil; silinenleri VE silinemeyenleri döndür.

    Var olmayan dizin sorun değildir: kullanıcı zaten temizlemiş olabilir ve
    kaldırma bu yüzden hata vermemelidir. Silinemeyen dizin ise SESSİZCE
    atlanmaz (L1-10): Ölçüldü (30 Ekim) `OSError` yutuluyor, hepsi başarısız olunca
    kullanıcı "silinecek veri yok" mesajını görüyordu.
    """
    if dry_run:
        return PurgeResult()
    silinen: list[Path] = []
    basarisiz: list[tuple[Path, str]] = []
    for yol in purge_targets():
        try:
            shutil.rmtree(yol)
        except OSError as error:
            basarisiz.append((yol, str(error)))
            continue
        silinen.append(yol)
    return PurgeResult(removed=tuple(silinen), failed=tuple(basarisiz))


def purge_user_data(*, dry_run: bool) -> tuple[Path, ...]:
    """`purge_user_data_report`un yalnız silinenleri döndüren hâli. `dry_run` iken silmez."""
    return purge_user_data_report(dry_run=dry_run).removed
