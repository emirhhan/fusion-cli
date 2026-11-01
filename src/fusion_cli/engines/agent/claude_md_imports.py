"""CLAUDE.md `@yol` içe aktarma ve dış import onayı (Claude Code #145).

Claude Code:
- `@yol` göreli (içeren dosyaya göre) ya da mutlak/`~/` olabilir; uzantı kısıtı yoktur
  (`@README`, `@package.json`). Boşluklu yol `\\ ` ile kaçırılır (`@Design\\ Docs/api.md`).
- İçe aktarılan dosya da import yapabilir; en çok dört adım.
- Kod bloklarındaki ve satır içi koddaki `@yol` import değildir.
- Proje düzeyindeki bir talimat dosyasında çalışma dizini dışına çıkan import "dış"tır;
  projede ilk kez görüldüğünde onay sorulur, reddedilirse kapalı kalır ve bir daha sorulmaz.

Fusion onayı proje başına `dis_import_onaylari.json` dosyasında saklar (kullanıcı yapılandırma
dizini). Karar verilmemişse dış import yüklenmez, notta "onay bekliyor" görünür.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

#: `@yol` zincirinin en fazla derinliği (Claude Code: dört adım).
MAX_IMPORT_DEPTH = 4

#: Satır başı ya da boşluk sonrası `@`, ardından `\ ` kaçışlı boşluk içerebilen yol.
_IMPORT_PATTERN = re.compile(r"(?:^|(?<=\s))@((?:\\ |[^\s`'\"()\[\]<>,;])+)")
_FENCE_PATTERN = re.compile(r"```.*?```|~~~.*?~~~", re.DOTALL)
_INLINE_CODE_PATTERN = re.compile(r"`[^`\n]*`")
_APPROVALS_NAME = "dis_import_onaylari.json"
#: İkili dosya denetimi için okunan bayt sayısı.
_BINARY_SNIFF = 8_192


def strip_code(content: str) -> str:
    """Çitli ve satır içi kod maskelenir: oradaki `@yol` bir örnektir, import değil."""
    return _INLINE_CODE_PATTERN.sub(" ", _FENCE_PATTERN.sub(" ", content))


def import_targets(content: str) -> list[str]:
    """Metindeki `@yol` hedefleri (kaçışlar çözülmüş, sondaki noktalama atılmış)."""
    found: list[str] = []
    for raw in _IMPORT_PATTERN.findall(strip_code(content)):
        target = raw.replace("\\ ", " ").rstrip(".:")
        if target and "://" not in target and "@" not in target:
            found.append(target)
    return found


def resolve_target(target: str, *, origin: Path, home: Path | None) -> Path | None:
    """Hedefi gerçek bir dosyaya çöz; yoksa, dizinse ya da ikiliyse `None`."""
    if target.startswith("~/"):
        if home is None:
            return None
        candidate = home / target[2:]
    elif target.startswith("/"):
        candidate = Path(target)
    else:
        candidate = origin.parent / target
    try:
        resolved = candidate.resolve()
        if not resolved.is_file():
            return None
        with resolved.open("rb") as handle:
            if b"\x00" in handle.read(_BINARY_SNIFF):
                return None
    except (OSError, ValueError):
        return None
    return resolved


def _approvals_file() -> Path:
    from ...config.paths import user_config_dir

    return user_config_dir() / _APPROVALS_NAME


def _read_approvals() -> dict[str, object]:
    try:
        data = json.loads(_approvals_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def external_import_decision(root: Path) -> bool | None:
    """Projenin dış import kararı: `True` onaylı, `False` reddedildi, `None` sorulmadı."""
    value = _read_approvals().get(str(root.resolve()))
    return value if isinstance(value, bool) else None


def set_external_import_decision(root: Path, approved: bool) -> None:
    """Kararı sakla (kullanıcı onay penceresinde seçince çağrılır)."""
    data = {**_read_approvals(), str(root.resolve()): approved}
    path = _approvals_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
