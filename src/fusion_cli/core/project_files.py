"""Projedeki dosyaların listesi — git biliyorsa ondan, yoksa budamalı yürüyüşten.

İki ayrı yer aynı soruyu soruyor: depo haritası ("hangi kaynak dosyalar var?")
ve `@` ile dosya anma ("kullanıcı hangi dosyayı kastediyor?"). Mantık burada
tek yerde durur; çağıranlar yalnız süzgeçleriyle ayrılır.

Neden git önce — ölçüldü (22 Eylül, fusion-cli deposu): elle yürüyüş 4.373
dosya buluyordu, `git ls-files` 811. Aradaki 3.562 dosya `.gitignore`'daki
paketli runtime kopyasıydı ve depo haritasının İLK SIRALARINI yiyordu. `@`
listesinde de aynı gürültü olurdu: kullanıcı kendi dosyasını ararken
`node_modules` altındaki yüzlerce eşleşmeyi elemek zorunda kalırdı.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

__all__ = ["MAX_PROJECT_FILES", "project_files"]

#: Taranmayan dizinler: üretilmiş çıktı ve bağımlılık ağaçları listeyi boğar.
#
# Nokta ile başlayan dizinlerin TAMAMI ayrıca atlanır (`_is_skipped`); bu,
# `.git`, `.venv`, `.mypy_cache` gibi adları tek tek saymaya gerek bırakmaz ve
# ölçülen gerçek maliyeti de alır (bu depoda `.worktrees` 3,0 GB).
_SKIP = frozenset(
    {
        "node_modules",
        "__pycache__",
        "dist",
        "build",
        "target",
        "vendor",
        "site-packages",
    }
)

#: Listeye alınacak en fazla dosya. Patolojik bir ağaç turu askıda bırakmasın.
MAX_PROJECT_FILES = 20_000

#: `git ls-files` için üst süre. Ölçüldü: bu depoda 0,014 sn. Takılı bir git
# (ağ dosya sistemi, kilitli index) çağıranı askıda bırakmasın diye yine sınırlı.
_GIT_TIMEOUT_SECONDS = 5.0


def _is_skipped(ad: str) -> bool:
    """Bu dizin adına hiç girilmez mi?"""
    return ad in _SKIP or ad.startswith(".")


def project_files(root: Path, *, limit: int = MAX_PROJECT_FILES) -> tuple[list[Path], bool]:
    """Projedeki dosyalar ve tavanın aşılıp aşılmadığı.

    Dönen yollar `root` altında MUTLAKTIR. Sıralama kararlıdır: aynı ağaç aynı
    listeyi verir, böylece çağıranın önbelleği ve sıralaması oynamaz.
    """
    izlenen = _git_files(root)
    if izlenen is not None:
        if len(izlenen) > limit:
            return izlenen[:limit], True
        return izlenen, False
    return _walk_files(root, limit=limit)


def _git_files(root: Path) -> list[Path] | None:
    """Git'in bildiği dosyalar; burası depo değilse ya da git yoksa None.

    `--cached --others --exclude-standard`: izlenen dosyalar ARTI yeni yazılmış
    ama yok sayılmamış dosyalar. İkincisi şart — agent'ın az önce oluşturduğu
    dosya listede görünmezse liste turun gerisinde kalır.
    """
    try:
        sonuc = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            capture_output=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if sonuc.returncode != 0:
        return None
    yollar: list[Path] = []
    for ham in sonuc.stdout.decode("utf-8", "replace").split("\0"):
        if not ham:
            continue
        aday = root / ham
        if aday.is_file():
            yollar.append(aday)
    return sorted(yollar)


def _walk_files(root: Path, *, limit: int) -> tuple[list[Path], bool]:
    """Budamalı elle yürüyüş: git yoksa ya da burası depo değilse.

    Budama YÜRÜYÜŞ SIRASINDA yapılır. `rglob` gürültü ağacının içine girip her
    yolu üretiyor, sonra atıyordu; bu depoda fark ölçüldü.
    """
    yollar: list[Path] = []
    for klasor, dizinler, dosyalar in os.walk(root, topdown=True):
        dizinler[:] = sorted(ad for ad in dizinler if not _is_skipped(ad))
        taban = Path(klasor)
        for ad in sorted(dosyalar):
            # Nokta ile başlayan DOSYA atlanmaz; git yolu onları döndürüyor
            # (`.gitignore`, `.claude/launch.json`) ve iki yolun aynı listeyi
            # vermesi gerekiyor. Atlanan yalnız nokta ile başlayan DİZİNLERdir.
            yollar.append(taban / ad)
            if len(yollar) >= limit:
                return yollar, True
    return yollar, False
