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
#: ve `venv`den ÖNCE denenir (ikisinin içinde de bir sanal ortam vardır).
_MARKERS: tuple[tuple[tuple[str, ...], InstallMethod], ...] = (
    (("uv", "tools"), InstallMethod.UV),
    (("pipx", "venvs"), InstallMethod.PIPX),
    ((".venv",), InstallMethod.VENV),
    (("venv",), InstallMethod.VENV),
)


def detect_method(executable: PurePath) -> InstallMethod:
    """Çalıştırılan yorumlayıcının yolundan kurulum yöntemini çıkar.

    Yol parçaları küçük harfe indirilerek karşılaştırılır: Windows yolları
    büyük/küçük harf duyarsızdır ve `AppData\\Roaming\\uv` de `uv` sayılmalıdır.
    """
    parcalar = {part.lower() for part in executable.parts}
    for isaretler, yontem in _MARKERS:
        if all(isaret in parcalar for isaret in isaretler):
            return yontem
    return InstallMethod.UNKNOWN


def update_command(method: InstallMethod) -> str:
    """Bu kurulum için güncelleme komutu (çalıştırılmaz, gösterilir)."""
    return {
        InstallMethod.UV: f"uv tool upgrade {PACKAGE}",
        InstallMethod.PIPX: f"pipx upgrade {PACKAGE}",
        InstallMethod.VENV: "git pull && ./setup.sh",
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
