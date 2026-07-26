"""`fusion update` ve `fusion uninstall` — bakım yönlendirmesi.

Fusion kendi kendini kaldırmaz ya da güncellemez: çalışan bir sürecin kendi
dosyalarını silmesi platforma göre farklı biçimlerde başarısız olur ve yarım
kaldığında kullanıcı elinde bozuk bir kurulumla kalır. Bunun yerine kurulum
YÖNTEMİ tespit edilir ve doğru komut gösterilir.

Kullanıcı verisi (anahtarlar, yapılandırma, öğrenilen dersler) kaldırmayla
SİLİNMEZ. Aracı kaldırmak "verilerimi de sil" demek değildir; silmek ayrı ve
AÇIK bir karardır (`--purge`).
"""

from __future__ import annotations

import shutil
import sys
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


def purge_user_data(*, dry_run: bool) -> tuple[Path, ...]:
    """Kullanıcı verisini sil ve silinenleri döndür. `dry_run` iken hiçbir şey silinmez.

    Var olmayan dizin sorun değildir: kullanıcı zaten temizlemiş olabilir ve
    kaldırma bu yüzden hata vermemelidir.
    """
    hedefler = tuple(yol for yol in (user_config_dir(), memory_dir()) if yol.exists())
    if dry_run:
        return ()
    silinen: list[Path] = []
    for yol in hedefler:
        try:
            shutil.rmtree(yol)
        except OSError:
            # Silinemeyen dizin turu durdurmaz; hangilerinin gittiği çağırana bildirilir.
            continue
        silinen.append(yol)
    return tuple(silinen)
