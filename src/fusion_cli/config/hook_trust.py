"""Kancalar ve çalışma alanı güveni (#108) — Claude Code `hooks#workspace-trust`.

Claude Code: etkileşimli oturumda kullanıcı ayarı dahil HER ayar dosyasının kancası çalışma
alanı güven iletişimi kabul edilene dek çalışmaz; `-p`/SDK'da klasör güvenilir sayılır.

Fusion'da güven klasör kaydıdır (`fusion trust`, açılış sorusu, masaüstü güven şeridi).
Proje dosyalarının (`.claude/settings*.json`) kendi güven denetimi ayrıca sürer; bu modül
proje DIŞINDAKİ katmanları (Fusion ve Claude kullanıcı dosyası, eklenti kancaları) klasör
güvenine bağlar. Yönetilen (managed) ayar yöneticinin dağıttığı politikadır; güven
reddedilip oturum sürerse politika kancaları kapanmasın diye bekletilmez (Claude'da güven
reddedilince oturum hiç açılmaz).

Klasör güveni, varsa izinler alanının klasör modeliyle (`workspace_trust.is_folder_trusted`:
git kökü ve üst klasör güveni) okunur; yoksa kökün ya da bir üst klasörün güven kaydına
bakılır (`--worktree` ağacı `.fusion/worktrees/` altında olduğundan depo güvenini alır).
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from pathlib import Path

from . import trust

#: `trust` kaydındaki "hiç güvenilmedi" işareti (yalnız izin dosyası karması yazılmış kayıt).
_NEVER_TRUSTED = ""
REASON_WORKSPACE_UNTRUSTED = "klasöre güvenilmedi (çalışma alanı güveni; fusion trust)"


def is_workspace_trusted(root: Path) -> bool:
    """Klasöre güven verildi mi? (Etkileşimli oturumda bütün kancaların ön koşulu.)"""
    folder_check = _folder_model()
    if folder_check is not None:
        return folder_check(root)
    store = trust._load()
    return any(
        (record := store.get(trust._key(candidate))) is not None
        and record.get("config_sha256") != _NEVER_TRUSTED
        for candidate in _candidates(root)
    )


def _candidates(root: Path) -> tuple[Path, ...]:
    """Kök ve üst klasörleri (ev dizini ve dosya sistemi kökü hariç): üst klasör güveni geçer."""
    try:
        current = root.resolve()
        home = Path.home().resolve()
    except (OSError, RuntimeError):
        return (root,)
    parents = (p for p in current.parents if p != home and p != Path(p.anchor))
    return (current, *parents)


def _folder_model() -> Callable[[Path], bool] | None:
    try:
        module = importlib.import_module(f"{__package__}.workspace_trust")
    except ImportError:
        return None
    check = getattr(module, "is_folder_trusted", None)
    return check if callable(check) else None


def display_path(path: Path, home: Path | None = None) -> str:
    """Kullanıcı dosyasının gösterimi (`~/.claude/settings.json`)."""
    base = home if home is not None else Path.home()
    try:
        return "~/" + path.relative_to(base).as_posix()
    except ValueError:
        return str(path)
