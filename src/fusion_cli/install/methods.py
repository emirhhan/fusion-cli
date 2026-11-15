"""Fusion'ın NASIL kurulduğunu tespit et ve doğru bakım komutunu üret.

Yanlış komut önermek kullanıcıyı çalışmayan bir talimata yollar: `pipx` ile
kurulmuş bir aracı `uv tool upgrade` ile güncellemeye çalışmak hata verir ve
kullanıcı Fusion'ın bozuk olduğunu sanır.
"""

from __future__ import annotations

from enum import Enum
from pathlib import PurePath

#: PyPI/dağıtım adı. Bakım komutları bunu kullanır.
PACKAGE = "fusion-cli"


class InstallMethod(Enum):
    """Fusion'ın kurulum yöntemi."""

    UV = "uv"
    PIPX = "pipx"
    #: Repo içindeki `.venv` — geliştirici kurulumu.
    VENV = "venv"
    UNKNOWN = "unknown"


#: Yol parçasından yönteme eşleme. Sıra önemlidir: `uv` ve `pipx` daha spesifiktir
#: ve `venv`den ÖNCE denenir (ikisinin içinde de bir sanal ortam vardır). Parçalar
#: BİTİŞİK ve SIRALI aranır: `…/uv/tools/…`, `…/pipx/venvs/…`.
_MARKERS: tuple[tuple[tuple[str, ...], InstallMethod], ...] = (
    (("uv", "tools"), InstallMethod.UV),
    (("pipx", "venvs"), InstallMethod.PIPX),
)

#: Sanal ortam dizin adları. Yorumlayıcı `<ad>/bin/python` (Windows: `<ad>/Scripts/python.exe`)
#: biçiminde olmalı; üst klasörlerden birinin adı `venv` olması yetmez.
_VENV_NAMES = frozenset({".venv", "venv"})


def detect_method(executable: PurePath) -> InstallMethod:
    """Çalıştırılan yorumlayıcının yolundan kurulum yöntemini çıkar.

    Yol parçaları küçük harfe indirilerek karşılaştırılır: Windows yolları
    büyük/küçük harf duyarsızdır ve `AppData\\Roaming\\uv` de `uv` sayılmalıdır.

    Ölçüldü (30 Ekim): eski eşleme parçaları kümeye atıp "herhangi bir yerde var mı"
    diye soruyordu; `/Users/x/venv/…` ya da `uv` ve `tools` ayrı yerlerde geçen herhangi
    bir yol yanlış yönteme düşüyordu (E1-36).
    """
    parcalar = [part.lower() for part in executable.parts]
    for isaretler, yontem in _MARKERS:
        if _contains_run(parcalar, isaretler):
            return yontem
    if len(parcalar) >= 3 and parcalar[-3] in _VENV_NAMES:
        return InstallMethod.VENV
    return InstallMethod.UNKNOWN


def _contains_run(parcalar: list[str], dizi: tuple[str, ...]) -> bool:
    """`dizi` parçaları `parcalar` içinde ARDIŞIK ve aynı sırada geçiyor mu?"""
    uzunluk = len(dizi)
    return any(tuple(parcalar[i : i + uzunluk]) == dizi for i in range(len(parcalar) - uzunluk + 1))


def update_command(method: InstallMethod) -> str:
    """Bu kurulum için güncelleme komutu (çalıştırılmaz, gösterilir)."""
    return {
        InstallMethod.UV: f"uv tool upgrade {PACKAGE}",
        InstallMethod.PIPX: f"pipx upgrade {PACKAGE}",
        InstallMethod.VENV: "Fusion deposunun dizininde: git pull && ./setup.sh",
        InstallMethod.UNKNOWN: _bilinmiyor("güncellemek"),
    }[method]


def uninstall_command(method: InstallMethod) -> str:
    """Bu kurulum için kaldırma komutu (çalıştırılmaz, gösterilir).

    Kullanıcının yapılandırma ve bellek dizinleri bu komutlarla SİLİNMEZ; onlar
    yalnızca `--purge` ile kaldırılır (bkz. `cli.maintenance`).
    """
    return {
        InstallMethod.UV: f"uv tool uninstall {PACKAGE}",
        InstallMethod.PIPX: f"pipx uninstall {PACKAGE}",
        InstallMethod.VENV: "kurulum dizinindeki .venv klasörünü sil",
        InstallMethod.UNKNOWN: _bilinmiyor("kaldırmak"),
    }[method]


def _bilinmiyor(eylem: str) -> str:
    """Uydurma komut vermektense bilinmediğini söylemek doğrudur."""
    return (
        f"Kurulum yöntemi bilinmiyor; {eylem} için hangi araçla kurduysan onu kullan "
        f"(uv tool / pipx / pip)."
    )
