"""Kabuk sınırında host kit bütünlüğü; komut yazımlarını önlediği iddiası yok.

Ölçüldü (29 Ekim): bütünlük bozulunca `run_shell` onarım komutu dahil HER komutu
reddediyordu; model de kullanıcı da toparlayamıyordu. Kit değişmezdir ama kilit
mutlak olmamalı: kiti DEĞİŞTİREMEYECEK dar bir onarım kümesi bozuk durumda da
çalışır (bağımlılık kurulumu, pakette olmayan yabancı dosyanın sade `rm`'si).
"""

from __future__ import annotations

import re
import shlex
from dataclasses import replace

from ..core.remotion_contract import RegisteredKitContract
from ..core.tools import ToolContext, ToolResult
from .remotion_contract_check import check_packaged, project_root, stray_kit_files
from .safe_delete import expand_targets, simple_rm_targets

#: Kabuk üstdilini (zincir, boru, yönlendirme, ikame, satır sonu) içeren komut onarım sayılmaz.
_SHELL_META = re.compile(r"[;&|<>`$(){}\n\\]")

#: Paket yöneticisinin yalnız bağımlılık kuran alt komutları. `run`/`exec`/`dlx`
#: yoktur: onlar keyfî betik çalıştırır.
_INSTALLERS = {
    "npm": frozenset({"install", "i", "ci", "add"}),
    "pnpm": frozenset({"install", "i", "add"}),
    "yarn": frozenset({"install", "add"}),
    "bun": frozenset({"install", "i", "add"}),
}


def remotion_integrity_error(context: ToolContext) -> str | None:
    contract = context.remotion_contract.registered
    if contract is None:
        return None
    try:
        root = project_root(context.root, contract.project_dir)
        check_packaged(root, contract)
    except (OSError, ValueError) as error:
        return f"Host Remotion kaynak bütünlüğü doğrulanamadı: {error}"
    return None


def is_dependency_install(command: str) -> bool:
    """Düz `npm install [paket...]` türü komut mu (zincir, boru, betik yok)."""
    if _SHELL_META.search(command):
        return False
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if len(parts) < 2 or parts[0] not in _INSTALLERS:
        return False
    return parts[1] in _INSTALLERS[parts[0]]


def _is_stray_removal(context: ToolContext, contract: RegisteredKitContract, command: str) -> bool:
    """Sade `rm`, hedeflerin TAMAMI pakette olmayan yabancı kit dosyası mı?"""
    targets = simple_rm_targets(command)
    if targets is None:
        return False
    try:
        root = project_root(context.root, contract.project_dir)
        strays = set(stray_kit_files(root, contract))
        paths = expand_targets(targets, context.root)
    except (OSError, ValueError):
        return False
    return bool(paths) and all(path in strays for path in paths)


def is_repair_command(context: ToolContext, command: str) -> bool:
    """Bütünlük bozukken de çalışabilecek, kiti değiştiremeyen onarım komutu."""
    contract = context.remotion_contract.registered
    if contract is None:
        return False
    return is_dependency_install(command) or _is_stray_removal(context, contract, command)


def repair_hint(error: str) -> str:
    return (
        f"{error}\nOnarım yolu: bağımlılık komutları (`npm install`) ve pakette olmayan "
        "yabancı kit dosyasını silen sade `rm <dosya>` bu durumda da çalışır. Kit "
        "dosyalarının kendisi değişmişse özgün kit gerekir; değiştirme."
    )


def check_shell_result(
    context: ToolContext, result: ToolResult, *, baseline: str | None = None
) -> ToolResult:
    """Komut sonrası bütünlük. `baseline`: komuttan ÖNCEKİ (onarım komutunda bozuk) durum."""
    error = remotion_integrity_error(context)
    if error is None:
        return result
    if baseline is not None and error == baseline:
        # Onarım komutu kiti daha da bozmadı; çıkışı başarıyı belirler, ama kitin
        # hâlâ bozuk olduğu çıktıda açıkça yazar.
        return replace(result, output=f"{result.output}\n{repair_hint(error)}")
    # Gerçek exit çıktısı ve completion makbuzu değişmez; bütünlük başarı değildir.
    return replace(result, ok=False, output=f"{result.output}\n{error}")


__all__ = [
    "check_shell_result",
    "is_dependency_install",
    "is_repair_command",
    "remotion_integrity_error",
    "repair_hint",
]
